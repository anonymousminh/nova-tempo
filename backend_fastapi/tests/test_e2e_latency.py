"""
End-to-End Voice-to-Action latency evaluation.

Measures the complete Socket.IO pipeline latency for each voice turn:

  1. Voice-to-Transcript   — first audio chunk → first user transcript
  2. Transcript-to-Response — final user transcript → first assistant event
  3. Total Round-Trip       — first audio chunk → calendar API call executed
                              (or final assistant transcript for non-tool turns)

Audio is synthesized via Amazon Polly so tests use realistic speech input
through the full Nova Sonic pipeline.

Run standalone:
    cd backend_fastapi
    python -m tests.test_e2e_latency                          # all scenarios
    python -m tests.test_e2e_latency --quick                  # 2 quick scenarios
    python -m tests.test_e2e_latency --server-url URL         # custom server

Run with pytest:
    cd backend_fastapi
    pytest tests/test_e2e_latency.py -v

Requires:
    - A running Nova Tempo server (default: http://localhost:8000)
    - AWS credentials (Bedrock for Nova Sonic, Polly for speech synthesis)
    - Google Calendar credentials (for tool-call scenarios)
    - aiohttp (pip install aiohttp)
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

RESULTS_DIR = Path(__file__).resolve().parent / "results"

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 512
BYTES_PER_SAMPLE = 2
CHUNK_SIZE_BYTES = CHUNK_SAMPLES * BYTES_PER_SAMPLE
CHUNK_DURATION_S = CHUNK_SAMPLES / SAMPLE_RATE  # ~0.032 s

SILENCE_CHUNK_B64 = base64.b64encode(b"\x00" * CHUNK_SIZE_BYTES).decode("ascii")
LEAD_SILENCE_S = 0.3
TRAIL_SILENCE_S = 2.0

DEFAULT_SERVER_URL = "http://localhost:8000"
VOICE_TO_ACTION_TARGET_MS = 2000

# ── Scenarios ─────────────────────────────────────────────────────────

@dataclass
class LatencyScenario:
    name: str
    utterance: str
    category: str
    expects_tool: bool


SCENARIOS: List[LatencyScenario] = [
    LatencyScenario(
        "general_greeting",
        "Hey Nova, good morning!",
        "general",
        expects_tool=False,
    ),
    LatencyScenario(
        "availability_check",
        "What does my schedule look like today?",
        "availability",
        expects_tool=True,
    ),
    LatencyScenario(
        "event_creation",
        "Schedule a team meeting tomorrow at 3 PM for one hour",
        "event_creation",
        expects_tool=True,
    ),
    LatencyScenario(
        "planning_query",
        "Help me prepare for my job interview next week",
        "planning",
        expects_tool=True,
    ),
    LatencyScenario(
        "free_time_check",
        "When am I free this week?",
        "availability",
        expects_tool=True,
    ),
]

QUICK_SCENARIOS = [SCENARIOS[0], SCENARIOS[1]]


# ── Audio synthesis via Amazon Polly ──────────────────────────────────

def synthesize_speech_chunks(text: str) -> List[str]:
    """Synthesize speech with Polly and return base64 PCM chunks.

    Each chunk is 512 samples of signed 16-bit LE mono PCM at 16 kHz,
    matching the format the AudioWorklet produces in the browser.
    """
    import boto3

    polly = boto3.client("polly", region_name="us-east-1")
    resp = polly.synthesize_speech(
        Text=text,
        OutputFormat="pcm",
        SampleRate=str(SAMPLE_RATE),
        VoiceId="Joanna",
        Engine="neural",
    )
    pcm_data = resp["AudioStream"].read()

    chunks: List[str] = []
    for offset in range(0, len(pcm_data), CHUNK_SIZE_BYTES):
        chunk = pcm_data[offset : offset + CHUNK_SIZE_BYTES]
        if len(chunk) < CHUNK_SIZE_BYTES:
            chunk += b"\x00" * (CHUNK_SIZE_BYTES - len(chunk))
        chunks.append(base64.b64encode(chunk).decode("ascii"))
    return chunks


# ── Socket.IO client measurement harness ─────────────────────────────

@dataclass
class TurnResult:
    """Latency results for a single voice turn."""
    scenario: str
    category: str
    expects_tool: bool

    # Client-side measurements (ms)
    client_voice_to_transcript_ms: Optional[float] = None
    client_transcript_to_response_ms: Optional[float] = None
    client_voice_to_voice_ms: Optional[float] = None
    client_total_round_trip_ms: Optional[float] = None

    # Server-side measurements (ms) — from voice_latency event
    server_metrics: Dict[str, Any] = field(default_factory=dict)

    audio_chunks_sent: int = 0
    audio_duration_s: float = 0.0
    error: Optional[str] = None
    timed_out: bool = False


async def _measure_turn(
    server_url: str,
    scenario: LatencyScenario,
    audio_chunks: List[str],
    realistic_pacing: bool = True,
    timeout_s: float = 45.0,
) -> TurnResult:
    """Connect, start a voice session, send audio, and collect latency."""
    import socketio

    result = TurnResult(
        scenario=scenario.name,
        category=scenario.category,
        expects_tool=scenario.expects_tool,
        audio_chunks_sent=len(audio_chunks),
        audio_duration_s=round(len(audio_chunks) * CHUNK_DURATION_S, 2),
    )

    timestamps: Dict[str, float] = {}
    server_latency: Dict[str, Any] = {}
    got_user_transcript = asyncio.Event()
    got_assistant_event = asyncio.Event()
    got_audio_out = asyncio.Event()
    got_assistant_final = asyncio.Event()
    got_latency = asyncio.Event()

    sio = socketio.AsyncClient(logger=False, engineio_logger=False)
    voice_started = asyncio.Event()

    @sio.on("voice_started")
    async def _on_started(data: Any) -> None:
        voice_started.set()

    @sio.on("voice_transcript")
    async def _on_transcript(data: Any) -> None:
        now = time.perf_counter()
        role = data.get("role")
        is_final = data.get("isFinal", False)

        if role == "user":
            if "first_user_transcript" not in timestamps:
                timestamps["first_user_transcript"] = now
                got_user_transcript.set()
            if is_final:
                timestamps["final_user_transcript"] = now

        elif role == "assistant":
            if "first_assistant_event" not in timestamps:
                timestamps["first_assistant_event"] = now
                got_assistant_event.set()
            if is_final:
                timestamps["assistant_final"] = now
                got_assistant_final.set()

    @sio.on("voice_audio_out")
    async def _on_audio_out(data: Any) -> None:
        now = time.perf_counter()
        if "first_audio_out" not in timestamps:
            timestamps["first_audio_out"] = now
            got_audio_out.set()

    @sio.on("voice_latency")
    async def _on_latency(data: Any) -> None:
        nonlocal server_latency
        server_latency = data
        got_latency.set()

    @sio.on("voice_error")
    async def _on_error(data: Any) -> None:
        result.error = data.get("error", str(data))
        got_assistant_final.set()

    async def _send_silence(n_chunks: int) -> None:
        """Send *n_chunks* of silence at realistic pacing."""
        for _ in range(n_chunks):
            await sio.emit("voice_audio_in", {"audio": SILENCE_CHUNK_B64})
            if realistic_pacing:
                await asyncio.sleep(CHUNK_DURATION_S)

    try:
        await sio.connect(server_url, transports=["websocket", "polling"])
        await sio.emit("voice_start")
        await asyncio.wait_for(voice_started.wait(), timeout=15.0)

        # Lead-in silence (simulates mic-on before the user speaks)
        lead_chunks = int(LEAD_SILENCE_S / CHUNK_DURATION_S)
        await _send_silence(lead_chunks)

        # Speech audio — start the latency clock here
        timestamps["first_audio_sent"] = time.perf_counter()
        for chunk in audio_chunks:
            await sio.emit("voice_audio_in", {"audio": chunk})
            if realistic_pacing:
                await asyncio.sleep(CHUNK_DURATION_S)
        timestamps["last_audio_sent"] = time.perf_counter()

        # Trailing silence so Nova Sonic's VAD detects end-of-utterance
        trail_chunks = int(TRAIL_SILENCE_S / CHUNK_DURATION_S)
        await _send_silence(trail_chunks)

        # Keep feeding silence while waiting for the assistant to finish,
        # just like a real open mic. Stop as soon as we get a response or
        # hit the timeout.
        deadline = time.perf_counter() + timeout_s
        while not got_assistant_final.is_set() and time.perf_counter() < deadline:
            await sio.emit("voice_audio_in", {"audio": SILENCE_CHUNK_B64})
            await asyncio.sleep(CHUNK_DURATION_S)

        if not got_assistant_final.is_set():
            result.timed_out = True

        # Give server a moment to emit voice_latency
        if not got_latency.is_set():
            try:
                await asyncio.wait_for(got_latency.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                pass

        await sio.emit("voice_stop")
        await asyncio.sleep(0.5)

    except Exception as exc:
        result.error = str(exc)
    finally:
        try:
            await sio.disconnect()
        except Exception:
            pass
        # Ensure the underlying aiohttp session is closed
        if sio.eio and sio.eio.http and not sio.eio.http.closed:
            await sio.eio.http.close()

    # ── Compute client-side metrics ──────────────────────────────────

    def ms(k_start: str, k_end: str) -> Optional[float]:
        s, e = timestamps.get(k_start), timestamps.get(k_end)
        if s is not None and e is not None:
            return round((e - s) * 1000, 1)
        return None

    result.client_voice_to_transcript_ms = ms(
        "first_audio_sent", "first_user_transcript"
    )
    result.client_transcript_to_response_ms = ms(
        "final_user_transcript", "first_assistant_event"
    )
    result.client_voice_to_voice_ms = ms("first_audio_sent", "first_audio_out")
    result.client_total_round_trip_ms = ms("first_audio_sent", "assistant_final")
    result.server_metrics = server_latency

    return result


# ── Evaluation runner ─────────────────────────────────────────────────

def _synthesize_all(
    scenarios: List[LatencyScenario],
) -> Dict[str, List[str]]:
    """Pre-synthesize audio for all scenarios (shows progress)."""
    audio_cache: Dict[str, List[str]] = {}
    for i, sc in enumerate(scenarios, 1):
        print(f"  Synthesizing [{i}/{len(scenarios)}]: \"{sc.utterance[:50]}\"")
        audio_cache[sc.name] = synthesize_speech_chunks(sc.utterance)
    return audio_cache


async def run_evaluation(
    scenarios: List[LatencyScenario],
    server_url: str = DEFAULT_SERVER_URL,
    realistic_pacing: bool = True,
) -> List[Dict[str, Any]]:
    """Run all latency scenarios and return result dicts."""
    print(f"\nSynthesizing speech for {len(scenarios)} scenarios via Amazon Polly …")
    audio_cache = _synthesize_all(scenarios)

    print(f"\nRunning latency evaluation against {server_url} …\n")
    results: List[Dict[str, Any]] = []

    for i, sc in enumerate(scenarios, 1):
        label = sc.utterance[:60]
        print(f"[{i}/{len(scenarios)}] {label}{'…' if len(sc.utterance) > 60 else ''}")

        chunks = audio_cache[sc.name]
        turn = await _measure_turn(
            server_url, sc, chunks, realistic_pacing=realistic_pacing
        )

        row: Dict[str, Any] = {
            "scenario": turn.scenario,
            "category": turn.category,
            "expects_tool": turn.expects_tool,
            "audio_chunks": turn.audio_chunks_sent,
            "audio_duration_s": turn.audio_duration_s,
            "client": {
                "voice_to_transcript_ms": turn.client_voice_to_transcript_ms,
                "transcript_to_response_ms": turn.client_transcript_to_response_ms,
                "voice_to_voice_ms": turn.client_voice_to_voice_ms,
                "total_round_trip_ms": turn.client_total_round_trip_ms,
            },
            "server": turn.server_metrics,
            "timed_out": turn.timed_out,
            "error": turn.error,
        }
        results.append(row)

        # Print summary for this scenario
        v2t = turn.client_voice_to_transcript_ms
        t2r = turn.client_transcript_to_response_ms
        v2v = turn.client_voice_to_voice_ms
        total = turn.client_total_round_trip_ms
        v2a = turn.server_metrics.get("voice_to_action_ms")

        parts = []
        if v2t is not None:
            parts.append(f"V→T={v2t:.0f}ms")
        if t2r is not None:
            parts.append(f"T→R={t2r:.0f}ms")
        if v2v is not None:
            parts.append(f"V→V={v2v:.0f}ms")
        if v2a is not None:
            parts.append(f"V→A={v2a:.0f}ms")
        if total is not None:
            parts.append(f"total={total:.0f}ms")

        status = "OK" if not turn.timed_out and not turn.error else "TIMEOUT" if turn.timed_out else "ERROR"
        print(f"        {status}  {' | '.join(parts) if parts else '(no data)'}")
        if turn.error:
            print(f"        error: {turn.error[:100]}")

    return results


# ── Reporting ─────────────────────────────────────────────────────────

def _percentile(values: List[float], pct: int) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(len(s) * pct / 100)
    return s[min(idx, len(s) - 1)]


def _metric_stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {}
    return {
        "mean_ms": round(sum(values) / len(values), 1),
        "p50_ms": round(_percentile(values, 50), 1),
        "p95_ms": round(_percentile(values, 95), 1),
        "max_ms": round(max(values), 1),
        "min_ms": round(min(values), 1),
    }


def print_report(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Print a formatted latency report and return the summary dict."""
    print(f"\n{'=' * 70}")
    print("  END-TO-END LATENCY REPORT")
    print(f"{'=' * 70}")

    total = len(results)
    errors = sum(1 for r in results if r.get("error"))
    timeouts = sum(1 for r in results if r.get("timed_out"))
    print(f"  Scenarios: {total}  |  Errors: {errors}  |  Timeouts: {timeouts}")

    # Collect metric arrays
    metric_names = [
        ("voice_to_transcript_ms", "Voice → Transcript"),
        ("transcript_to_response_ms", "Transcript → Response"),
        ("voice_to_voice_ms", "Voice → Voice"),
        ("total_round_trip_ms", "Total Round-Trip"),
    ]

    print(f"\n  Client-side latency (includes network):\n")
    print(f"  {'Metric':<26s} {'Mean':>8s} {'P50':>8s} {'P95':>8s} {'Max':>8s} {'Min':>8s}  N")
    print(f"  {'─' * 76}")

    client_stats: Dict[str, Dict[str, float]] = {}
    for key, label in metric_names:
        vals = [
            r["client"][key]
            for r in results
            if r["client"].get(key) is not None
        ]
        stats = _metric_stats(vals)
        client_stats[key] = stats
        if stats:
            print(
                f"  {label:<26s} "
                f"{stats['mean_ms']:>7.0f} "
                f"{stats['p50_ms']:>7.0f} "
                f"{stats['p95_ms']:>7.0f} "
                f"{stats['max_ms']:>7.0f} "
                f"{stats['min_ms']:>7.0f}  {len(vals)}"
            )
        else:
            print(f"  {label:<26s}  {'—':>7s} {'—':>7s} {'—':>7s} {'—':>7s} {'—':>7s}  0")

    # Server-side tool timing
    server_tool_vals = [
        r["server"]["tool_execution_ms"]
        for r in results
        if r["server"].get("tool_execution_ms") is not None
    ]
    server_v2a_vals = [
        r["server"]["voice_to_action_ms"]
        for r in results
        if r["server"].get("voice_to_action_ms") is not None
    ]

    if server_tool_vals or server_v2a_vals:
        print(f"\n  Server-side latency (no network overhead):\n")
        print(f"  {'Metric':<26s} {'Mean':>8s} {'P50':>8s} {'P95':>8s} {'Max':>8s} {'Min':>8s}  N")
        print(f"  {'─' * 76}")

        for vals, label in [
            (server_tool_vals, "Tool Execution"),
            (server_v2a_vals, "Voice → Action (server)"),
        ]:
            stats = _metric_stats(vals)
            if stats:
                print(
                    f"  {label:<26s} "
                    f"{stats['mean_ms']:>7.0f} "
                    f"{stats['p50_ms']:>7.0f} "
                    f"{stats['p95_ms']:>7.0f} "
                    f"{stats['max_ms']:>7.0f} "
                    f"{stats['min_ms']:>7.0f}  {len(vals)}"
                )

    # Per-category breakdown
    categories = sorted({r["category"] for r in results})
    if len(categories) > 1:
        print(f"\n  Per-category (client total round-trip):\n")
        print(f"  {'Category':<20s} {'Mean':>8s} {'P50':>8s} {'P95':>8s}  N")
        print(f"  {'─' * 52}")
        for cat in categories:
            vals = [
                r["client"]["total_round_trip_ms"]
                for r in results
                if r["category"] == cat and r["client"].get("total_round_trip_ms") is not None
            ]
            stats = _metric_stats(vals)
            if stats:
                print(
                    f"  {cat:<20s} "
                    f"{stats['mean_ms']:>7.0f} "
                    f"{stats['p50_ms']:>7.0f} "
                    f"{stats['p95_ms']:>7.0f}  {len(vals)}"
                )

    # Target check
    target = VOICE_TO_ACTION_TARGET_MS
    v2a_all = server_v2a_vals or [
        r["client"]["total_round_trip_ms"]
        for r in results
        if r["client"].get("total_round_trip_ms") is not None
    ]
    under_target = sum(1 for v in v2a_all if v <= target) if v2a_all else 0
    pct = under_target / len(v2a_all) * 100 if v2a_all else 0

    print(f"\n  Target: voice-to-action < {target}ms")
    print(f"  Result: {under_target}/{len(v2a_all)} turns under target ({pct:.0f}%)")

    p95 = _percentile(v2a_all, 95) if v2a_all else 0
    meets_target = p95 <= target if v2a_all else False
    if meets_target:
        print(f"  PASS — p95 = {p95:.0f}ms <= {target}ms target")
    else:
        print(f"  FAIL — p95 = {p95:.0f}ms > {target}ms target")

    print(f"{'=' * 70}\n")

    summary = {
        "timestamp": datetime.now().isoformat(),
        "server_url": DEFAULT_SERVER_URL,
        "total_scenarios": total,
        "errors": errors,
        "timeouts": timeouts,
        "target_ms": target,
        "meets_target": meets_target,
        "client_latency": client_stats,
        "server_tool_execution": _metric_stats(server_tool_vals),
        "server_voice_to_action": _metric_stats(server_v2a_vals),
    }
    return summary


def save_results(
    results: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"e2e_latency_{ts}.json"
    payload = {"summary": summary, "results": results}
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"  Results saved to {path}\n")
    return path


# ── pytest entry point ────────────────────────────────────────────────

def test_e2e_latency_basic():
    """Pytest: run quick scenarios and assert p95 voice-to-action < 2s."""
    results = asyncio.run(run_evaluation(QUICK_SCENARIOS))
    summary = print_report(results)
    save_results(results, summary)

    errors = [r for r in results if r.get("error")]
    assert not errors, f"{len(errors)} scenario(s) had errors: {errors}"
    assert summary["meets_target"], (
        f"p95 voice-to-action latency exceeds {VOICE_TO_ACTION_TARGET_MS}ms target"
    )


# ── CLI entry point ───────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="End-to-end voice-to-action latency evaluation"
    )
    parser.add_argument(
        "--server-url",
        default=DEFAULT_SERVER_URL,
        help=f"Nova Tempo server URL (default: {DEFAULT_SERVER_URL})",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only 2 quick scenarios",
    )
    parser.add_argument(
        "--burst",
        action="store_true",
        help="Send audio chunks without pacing (faster, less realistic)",
    )
    args = parser.parse_args()

    scenarios = QUICK_SCENARIOS if args.quick else SCENARIOS
    results = asyncio.run(
        run_evaluation(
            scenarios,
            server_url=args.server_url,
            realistic_pacing=not args.burst,
        )
    )
    summary = print_report(results)
    save_results(results, summary)

    sys.exit(0 if summary["meets_target"] else 1)


if __name__ == "__main__":
    main()
