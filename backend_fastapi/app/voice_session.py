"""Voice session management: browser <-> BidiAgent via Socket.IO.

Each connected client can have at most one active voice session.
Audio flow:
  Browser mic -> Socket.IO voice_audio_in -> BidiAgent (Nova Sonic)
  BidiAgent audio/transcript -> Socket.IO voice_audio_out / voice_transcript -> Browser
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

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
from .orchestrator import get_orchestrator_tools, ORCHESTRATOR_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class VoiceSession:
    """Manages a single BidiAgent voice session for a Socket.IO client."""

    def __init__(self, sio: socketio.AsyncServer, sid: str) -> None:
        self._sio = sio
        self._sid = sid
        self._agent: BidiAgent | None = None
        self._receive_task: asyncio.Task | None = None

    async def start(self) -> dict[str, Any]:
        """Create and start the BidiAgent. Returns audio config for the client."""
        if self._agent is not None:
            await self.stop()

        model = BidiNovaSonicModel(
            model_id="amazon.nova-sonic-v1:0",
            provider_config={"audio": {"voice": "tiffany"}},
            client_config={"region": "us-east-1"},
        )

        orchestrator_tools = get_orchestrator_tools(get_calendar_service)

        now = datetime.now().astimezone()
        today_str = now.strftime("%A %B %-d, %Y, %-I:%M %p")
        date_context = (
            f"\nThe current date and time is {today_str}. "
            f'When the user says "today" they mean {now.strftime("%Y-%m-%d")}, '
            f'"tomorrow" means {(now + timedelta(days=1)).strftime("%Y-%m-%d")}.'
        )

        self._agent = BidiAgent(
            model=model,
            system_prompt=ORCHESTRATOR_SYSTEM_PROMPT + date_context,
            tools=[*orchestrator_tools, stop_conversation],
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

    async def send_audio(self, audio_b64: str) -> None:
        """Forward a base64 audio chunk from the browser to the BidiAgent."""
        if self._agent is None or not self._agent._started:
            return
        event = BidiAudioInputEvent(
            audio=audio_b64,
            format=self._audio_format,
            sample_rate=self._input_rate,
            channels=self._channels,
        )
        await self._agent.send(event)

    async def stop(self) -> None:
        """Stop the BidiAgent and clean up."""
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        self._receive_task = None

        if self._agent is not None:
            try:
                await self._agent.stop()
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
            await self._sio.emit(
                "voice_interrupted",
                {"reason": event.reason},
                to=self._sid,
            )
        elif isinstance(event, BidiErrorEvent):
            await self._sio.emit(
                "voice_error",
                {"error": event.message},
                to=self._sid,
            )


# ---- Per-client session store ------------------------------------------------

_sessions: dict[str, VoiceSession] = {}


async def start_voice(sio: socketio.AsyncServer, sid: str) -> dict[str, Any]:
    session = VoiceSession(sio, sid)
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
