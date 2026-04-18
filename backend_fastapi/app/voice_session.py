"""Voice session management: browser <-> BidiAgent via Socket.IO.

Each connected client can have at most one active voice session.
Audio flow:
  Browser mic -> Socket.IO voice_audio_in -> BidiAgent (Nova Sonic)
  BidiAgent audio/transcript -> Socket.IO voice_audio_out / voice_transcript -> Browser
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import socketio

from strands.experimental.bidi import BidiAgent
from strands.experimental.bidi.models import BidiNovaSonicModel
from strands.experimental.bidi.tools import stop_conversation
from strands.experimental.bidi.types.events import (
    BidiAudioInputEvent,
    BidiAudioStreamEvent,
    BidiTranscriptStreamEvent,
    BidiInterruptionEvent,
    BidiOutputEvent,
    BidiErrorEvent,
)

from .calendar_auth import get_calendar_service
from .latency_tracker import LatencyTracker
from .orchestrator import get_orchestrator_tools, ORCHESTRATOR_SYSTEM_PROMPT

try:
    from bedrock_agentcore.memory.integrations.strands.config import (
        AgentCoreMemoryConfig,
    )
    from bedrock_agentcore.memory.integrations.strands.session_manager import (
        AgentCoreMemorySessionManager,
    )
    _MEMORY_AVAILABLE = True
except ImportError:
    _MEMORY_AVAILABLE = False

logger = logging.getLogger(__name__)


class VoiceSession:
    """Manages a single BidiAgent voice session for a Socket.IO client."""

    def __init__(self, sio: socketio.AsyncServer, sid: str, user_id: str | None = None) -> None:
        self._sio = sio
        self._sid = sid
        self._user_id = user_id
        self._agent: BidiAgent | None = None
        self._receive_task: asyncio.Task | None = None
        self._memory_session_manager = None
        self._latency = LatencyTracker()

    async def start(self) -> dict[str, Any]:
        """Create and start the BidiAgent. Returns audio config for the client."""
        if self._agent is not None:
            await self.stop()

        # Eagerly initialize the calendar service (and refresh the OAuth
        # token if expired) BEFORE starting the BidiAgent.  The token
        # refresh is a synchronous blocking HTTP call — doing it here
        # avoids blocking the event loop while the real-time audio
        # streams are active.
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, get_calendar_service)

        model = BidiNovaSonicModel(
            model_id="amazon.nova-sonic-v1:0",
            provider_config={"audio": {"voice": "tiffany"}},
            client_config={"region": "us-east-1"},
        )

        def _on_tool_invoke(name: str, phase: str) -> None:
            if phase == "start":
                self._latency.mark_tool_start(name)
            elif phase == "end":
                self._latency.mark_tool_end()

        orchestrator_tools = get_orchestrator_tools(
            get_calendar_service, on_tool_invoke=_on_tool_invoke
        )

        now = datetime.now().astimezone()
        today_str = now.strftime("%A %B %-d, %Y, %-I:%M %p")
        date_context = (
            f"\n## Current date and time\n"
            f"Right now it is **{today_str}**. The current year is **{now.year}**.\n"
            f'When the user says "today" they mean {now.strftime("%Y-%m-%d")}, '
            f'"tomorrow" means {(now + timedelta(days=1)).strftime("%Y-%m-%d")}.\n'
            f"IMPORTANT: Always use the year {now.year} when creating events. "
            f"Never use a past year."
        )

        session_manager = self._build_memory_session_manager()

        self._agent = BidiAgent(
            model=model,
            system_prompt=ORCHESTRATOR_SYSTEM_PROMPT + date_context,
            tools=[*orchestrator_tools, stop_conversation],
            **({"session_manager": session_manager} if session_manager else {}),
        )

        await self._agent.start()

        audio_cfg = self._agent.model.config.get("audio", {})
        self._input_rate = audio_cfg.get("input_rate", 16000)
        self._output_rate = audio_cfg.get("output_rate", 16000)
        self._channels = audio_cfg.get("channels", 1)
        self._audio_format = audio_cfg.get("format", "pcm")

        self._receive_task = asyncio.create_task(self._receive_loop())

        return {
            "inputSampleRate": self._input_rate,
            "outputSampleRate": self._output_rate,
            "channels": self._channels,
            "format": self._audio_format,
        }

    def _build_memory_session_manager(self):
        """Create an AgentCoreMemorySessionManager if memory is configured."""
        memory_id = os.environ.get("BEDROCK_MEMORY_ID")
        if not _MEMORY_AVAILABLE or not memory_id or not self._user_id:
            if not _MEMORY_AVAILABLE:
                logger.info("bedrock-agentcore not installed — memory disabled")
            elif not memory_id:
                logger.info("BEDROCK_MEMORY_ID not set — memory disabled")
            elif not self._user_id:
                logger.info("No user_id — memory disabled")
            return None

        region = os.environ.get("BEDROCK_MEMORY_REGION", "us-east-1")
        session_id = f"{self._user_id}_{uuid4().hex[:8]}"

        config = AgentCoreMemoryConfig(
            memory_id=memory_id,
            actor_id=self._user_id,
            session_id=session_id,
        )
        self._memory_session_manager = AgentCoreMemorySessionManager(
            agentcore_memory_config=config,
            region_name=region,
        )
        logger.info(
            "Memory enabled  memory=%s actor=%s session=%s",
            memory_id, self._user_id, session_id,
        )
        return self._memory_session_manager

    async def send_audio(self, audio_b64: str) -> None:
        """Forward a base64 audio chunk from the browser to the BidiAgent."""
        if self._agent is None or not self._agent._started:
            return
        self._latency.mark_audio_in()
        event = BidiAudioInputEvent(
            audio=audio_b64,
            format=self._audio_format,
            sample_rate=self._input_rate,
            channels=self._channels,
        )
        await self._agent.send(event)

    async def stop(self) -> None:
        """Stop the BidiAgent and clean up."""
        await self._emit_latency()

        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        self._receive_task = None

        agent = self._agent

        if self._memory_session_manager is not None and agent is not None:
            try:
                self._memory_session_manager.sync_bidi_agent(agent)
                logger.info("Memory session synced and released")
            except Exception as e:
                logger.warning("Error syncing memory session: %s", e)
            self._memory_session_manager = None

        if agent is not None:
            try:
                await agent.stop()
            except Exception as e:
                logger.warning("Error stopping BidiAgent: %s", e)
        self._agent = None

    async def _receive_loop(self) -> None:
        """Background task: read BidiAgent output events and emit via Socket.IO."""
        try:
            async for event in self._agent.receive():
                await self._handle_output(event)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Voice receive loop error: %s", e)
            try:
                await self._sio.emit("voice_error", {"error": str(e)}, to=self._sid)
            except Exception:
                pass

    async def _handle_output(self, event: BidiOutputEvent) -> None:
        if isinstance(event, BidiAudioStreamEvent):
            self._latency.mark_assistant_audio()
            await self._sio.emit(
                "voice_audio_out",
                {
                    "audio": event.audio,
                    "sampleRate": event.sample_rate,
                    "channels": event.channels,
                },
                to=self._sid,
            )
        elif isinstance(event, BidiTranscriptStreamEvent):
            if event.role == "user":
                self._latency.mark_user_transcript(event.is_final)
            elif event.role == "assistant":
                self._latency.mark_assistant_transcript(event.is_final)
                if event.is_final:
                    await self._emit_latency()
            await self._sio.emit(
                "voice_transcript",
                {
                    "text": event.text,
                    "role": event.role,
                    "isFinal": event.is_final,
                    "currentTranscript": event.current_transcript,
                },
                to=self._sid,
            )
        elif isinstance(event, BidiInterruptionEvent):
            await self._emit_latency()
            await self._sio.emit(
                "voice_interrupted",
                {"reason": event.reason},
                to=self._sid,
            )
        elif isinstance(event, BidiErrorEvent):
            await self._emit_latency()
            await self._sio.emit(
                "voice_error",
                {"error": event.message},
                to=self._sid,
            )

    async def _emit_latency(self) -> None:
        """Collect and emit per-turn latency metrics via Socket.IO."""
        metrics = self._latency.collect()
        if metrics:
            logger.info("Turn latency: %s", metrics)
            await self._sio.emit("voice_latency", metrics, to=self._sid)


# ---- Per-client session store ------------------------------------------------

_sessions: dict[str, VoiceSession] = {}


async def start_voice(sio: socketio.AsyncServer, sid: str, *, user_id: str | None = None) -> dict[str, Any]:
    session = VoiceSession(sio, sid, user_id=user_id)
    _sessions[sid] = session
    return await session.start()


async def send_audio(sid: str, audio_b64: str) -> None:
    session = _sessions.get(sid)
    if session:
        await session.send_audio(audio_b64)


async def stop_voice(sid: str) -> None:
    session = _sessions.pop(sid, None)
    if session:
        await session.stop()
