"""Per-turn latency tracker for the voice-to-action pipeline.

Captures timestamps at each stage of a voice turn:

  Audio In → ASR Transcript → Agent Response → Tool Execution → TTS Audio Out

Used by VoiceSession to emit per-turn latency metrics via the
``voice_latency`` Socket.IO event.

Metrics produced
----------------
- **voice_to_transcript_ms**: first audio chunk → first user transcript
- **transcript_to_response_ms**: final user transcript → first assistant event
- **voice_to_voice_ms**: first audio chunk → first assistant TTS audio
- **tool_execution_ms**: tool call start → tool call end
- **voice_to_action_ms**: first audio chunk → tool call end (calendar API executed)
- **total_round_trip_ms**: first audio chunk → final assistant transcript
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class LatencyTracker:
    """Tracks latency for one voice turn at a time.

    Thread-safety: relies on CPython's GIL for atomic float assignments.
    All ``mark_*`` methods are safe to call from any thread.
    """

    def __init__(self) -> None:
        self._turn_active = False
        self._collected = False
        self._reset()

    # ── Internal ─────────────────────────────────────────────────────

    def _reset(self) -> None:
        self._t_audio_in: float | None = None
        self._t_user_transcript: float | None = None
        self._t_user_final: float | None = None
        self._t_assistant_event: float | None = None
        self._t_assistant_audio: float | None = None
        self._t_assistant_final: float | None = None
        self._t_tool_start: float | None = None
        self._t_tool_end: float | None = None
        self._tool_name: str | None = None
        self._collected = False

    def _ensure_turn(self) -> None:
        if not self._turn_active:
            self._reset()
            self._turn_active = True

    @staticmethod
    def _ms(start: float | None, end: float | None) -> float | None:
        if start is not None and end is not None:
            return round((end - start) * 1000, 1)
        return None

    # ── Mark pipeline stages ─────────────────────────────────────────

    def mark_audio_in(self) -> None:
        """Record receipt of the first audio chunk for a new turn."""
        self._ensure_turn()
        if self._t_audio_in is None:
            self._t_audio_in = time.perf_counter()

    def mark_user_transcript(self, is_final: bool) -> None:
        """Record a user speech transcript event from ASR."""
        now = time.perf_counter()
        if self._t_user_transcript is None:
            self._t_user_transcript = now
        if is_final:
            self._t_user_final = now

    def mark_assistant_audio(self) -> None:
        """Record the first assistant TTS audio chunk."""
        now = time.perf_counter()
        if self._t_assistant_audio is None:
            self._t_assistant_audio = now
        if self._t_assistant_event is None:
            self._t_assistant_event = now

    def mark_assistant_transcript(self, is_final: bool) -> None:
        """Record an assistant response transcript event."""
        now = time.perf_counter()
        if self._t_assistant_event is None:
            self._t_assistant_event = now
        if is_final:
            self._t_assistant_final = now

    def mark_tool_start(self, tool_name: str) -> None:
        """Record the start of a sub-agent tool call."""
        self._t_tool_start = time.perf_counter()
        self._tool_name = tool_name

    def mark_tool_end(self) -> None:
        """Record the completion of a sub-agent tool call."""
        self._t_tool_end = time.perf_counter()

    # ── Collect ──────────────────────────────────────────────────────

    def collect(self) -> dict[str, Any] | None:
        """Collect turn metrics and deactivate the tracker.

        Returns a dict of non-None latency metrics, or ``None`` if no data
        was recorded or metrics were already collected for this turn.
        """
        if self._collected or self._t_audio_in is None:
            return None

        self._collected = True
        self._turn_active = False

        ms = self._ms
        metrics: dict[str, Any] = {}

        v2t = ms(self._t_audio_in, self._t_user_transcript)
        if v2t is not None:
            metrics["voice_to_transcript_ms"] = v2t

        t2r = ms(self._t_user_final, self._t_assistant_event)
        if t2r is not None:
            metrics["transcript_to_response_ms"] = t2r

        v2v = ms(self._t_audio_in, self._t_assistant_audio)
        if v2v is not None:
            metrics["voice_to_voice_ms"] = v2v

        tool_ms = ms(self._t_tool_start, self._t_tool_end)
        if tool_ms is not None:
            metrics["tool_execution_ms"] = tool_ms

        if self._tool_name is not None:
            metrics["tool_name"] = self._tool_name

        v2a = ms(self._t_audio_in, self._t_tool_end)
        if v2a is not None:
            metrics["voice_to_action_ms"] = v2a

        last = (
            self._t_assistant_final
            or self._t_assistant_audio
            or self._t_assistant_event
        )
        total = ms(self._t_audio_in, last)
        if total is not None:
            metrics["total_round_trip_ms"] = total

        return metrics if metrics else None

    # ── Status ───────────────────────────────────────────────────────

    @property
    def turn_complete(self) -> bool:
        """True when the assistant's final transcript has been received."""
        return self._t_assistant_final is not None

    @property
    def has_data(self) -> bool:
        """True when at least one audio chunk has been recorded."""
        return self._t_audio_in is not None
