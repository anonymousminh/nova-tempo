"""
Task Completion / Success Rate evaluation.

Measures the orchestrator's ability to correctly complete calendar
operations end-to-end: routing to the right sub-agent, the sub-agent
calling the correct Google Calendar API, and the system completing the
user's request across multi-turn conversations.

Uses a mock Google Calendar service so no real API calls are made, but
all agent logic (LLM routing + sub-agent tool selection) runs for real
via AWS Bedrock.

Run standalone:
    cd backend_fastapi
    python -m tests.test_task_completion              # full dataset (~152 cases)
    python -m tests.test_task_completion --quick       # quick smoke test (~7 cases)
    python -m tests.test_task_completion --core        # core dataset (no edge cases)

Run with pytest:
    cd backend_fastapi
    pytest tests/test_task_completion.py -v

Requires:
    - AWS credentials configured (for Bedrock LLM access)
    - No Google Calendar credentials needed (calendar service is mocked)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from strands import Agent

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.orchestrator import ORCHESTRATOR_SYSTEM_PROMPT, get_orchestrator_tools

from .task_completion_dataset import (
    CORE_SCENARIOS,
    QUICK_SCENARIOS,
    TASK_SCENARIOS,
    TaskScenario,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"


# ─── Mock Google Calendar service ────────────────────────────────────


class _MockRequest:
    """Simulates the ``execute()`` pattern of Google API client resources."""

    def __init__(self, result: Any):
        self._result = result

    def execute(self) -> Any:
        return self._result


class _MockEventsResource:
    """Mock for ``service.events()``."""

    def __init__(self, service: "MockCalendarService"):
        self._svc = service

    def list(self, **kwargs: Any) -> _MockRequest:
        self._svc.api_calls.append({"method": "events.list", "kwargs": kwargs})
        return _MockRequest({"items": list(self._svc.mock_events)})

    def insert(self, **kwargs: Any) -> _MockRequest:
        self._svc.api_calls.append({"method": "events.insert", "kwargs": kwargs})
        body = kwargs.get("body", {})
        created = {
            "id": f"evt_created_{len(self._svc.api_calls):03d}",
            "summary": body.get("summary", "New Event"),
            "start": body.get("start", {}),
            "end": body.get("end", {}),
            "htmlLink": "https://calendar.google.com/calendar/event?eid=mock",
            "status": "confirmed",
        }
        self._svc.mock_events.append(created)
        return _MockRequest(created)

    def delete(self, **kwargs: Any) -> _MockRequest:
        self._svc.api_calls.append({"method": "events.delete", "kwargs": kwargs})
        event_id = kwargs.get("eventId")
        self._svc.mock_events = [
            e for e in self._svc.mock_events if e["id"] != event_id
        ]
        return _MockRequest(None)


class _MockFreebusyResource:
    """Mock for ``service.freebusy()``."""

    def __init__(self, service: "MockCalendarService"):
        self._svc = service

    def query(self, **kwargs: Any) -> _MockRequest:
        self._svc.api_calls.append({"method": "freebusy.query", "kwargs": kwargs})
        body = kwargs.get("body", {})
        calendar_ids = [
            item["id"] if isinstance(item, dict) else item
            for item in body.get("items", [{"id": "primary"}])
        ]
        result: Dict[str, Any] = {"calendars": {}}
        for cal_id in calendar_ids:
            result["calendars"][cal_id] = {"busy": []}
        return _MockRequest(result)


class MockCalendarService:
    """Drop-in mock for the Google Calendar API service object.

    Records every API call made through ``events()`` and ``freebusy()``
    resources so tests can verify the correct operations were performed.

    ``freebusy`` always returns empty busy periods (no conflicts) so
    event-creation flows proceed to the confirmation step cleanly.
    ``events().list()`` returns a small set of pre-populated mock events
    so availability and delete scenarios have data to work with.
    """

    def __init__(self) -> None:
        self.api_calls: List[Dict[str, Any]] = []
        self.mock_events: List[Dict[str, Any]] = self._seed_events()

    @staticmethod
    def _seed_events() -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        tomorrow = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        day_after = tomorrow + timedelta(days=1)
        return [
            {
                "id": "evt_standup_001",
                "summary": "Team Standup",
                "start": {
                    "dateTime": tomorrow.replace(hour=9).isoformat(),
                },
                "end": {
                    "dateTime": tomorrow.replace(hour=9, minute=30).isoformat(),
                },
            },
            {
                "id": "evt_lunch_002",
                "summary": "Lunch with Sarah",
                "start": {
                    "dateTime": tomorrow.replace(hour=12).isoformat(),
                },
                "end": {
                    "dateTime": tomorrow.replace(hour=13).isoformat(),
                },
            },
            {
                "id": "evt_review_003",
                "summary": "Code Review",
                "start": {
                    "dateTime": tomorrow.replace(hour=15).isoformat(),
                },
                "end": {
                    "dateTime": tomorrow.replace(hour=16).isoformat(),
                },
            },
            {
                "id": "evt_meeting_004",
                "summary": "Product Meeting",
                "start": {
                    "dateTime": day_after.replace(hour=10).isoformat(),
                },
                "end": {
                    "dateTime": day_after.replace(hour=11).isoformat(),
                },
            },
            {
                "id": "evt_dentist_005",
                "summary": "Dentist Appointment",
                "start": {
                    "dateTime": (day_after + timedelta(days=1))
                    .replace(hour=14)
                    .isoformat(),
                },
                "end": {
                    "dateTime": (day_after + timedelta(days=1))
                    .replace(hour=15)
                    .isoformat(),
                },
            },
        ]

    def events(self) -> _MockEventsResource:
        return _MockEventsResource(self)

    def freebusy(self) -> _MockFreebusyResource:
        return _MockFreebusyResource(self)


# ─── Tracked orchestrator ────────────────────────────────────────────


def _build_date_context() -> str:
    now = datetime.now().astimezone()
    today_str = now.strftime("%A %B %-d, %Y, %-I:%M %p")
    return (
        f"\n## Current date and time\n"
        f"Right now it is **{today_str}**. The current year is **{now.year}**.\n"
        f'When the user says "today" they mean {now.strftime("%Y-%m-%d")}, '
        f'"tomorrow" means {(now + timedelta(days=1)).strftime("%Y-%m-%d")}.\n'
        f"IMPORTANT: Always use the year {now.year} when creating events. "
        f"Never use a past year."
    )


def create_tracked_orchestrator(
    mock_service: MockCalendarService,
) -> Tuple[Agent, List[str]]:
    """Build an orchestrator wired to a mock calendar, with agent call logging.

    Returns ``(agent, tool_log)`` where *tool_log* records the name of
    every sub-agent invoked (in order).
    """
    tool_log: List[str] = []

    def get_calendar_service() -> MockCalendarService:
        return mock_service

    def on_tool_invoke(name: str, phase: str) -> None:
        if phase == "start":
            tool_log.append(name)

    tools = get_orchestrator_tools(get_calendar_service, on_tool_invoke)

    agent = Agent(
        system_prompt=ORCHESTRATOR_SYSTEM_PROMPT + _build_date_context(),
        tools=tools,
    )
    return agent, tool_log


# ─── Verification ────────────────────────────────────────────────────

WRITE_METHODS = {"events.insert", "events.delete"}


def _verify(
    scenario: TaskScenario,
    api_calls: List[Dict[str, Any]],
    tool_log: List[str],
) -> Tuple[bool, str]:
    """Check whether the scenario's success criteria are met.

    Returns ``(passed, reason)``.
    """
    actual_methods = [c["method"] for c in api_calls]
    reasons: List[str] = []

    # 1. Check expected API calls (at least one must be present)
    if scenario.expected_api_calls:
        found = any(m in actual_methods for m in scenario.expected_api_calls)
        if not found:
            reasons.append(
                f"Expected one of {scenario.expected_api_calls}, "
                f"got {actual_methods or '(none)'}"
            )

    # 2. Check expected agents (at least one must have been invoked)
    if scenario.expected_agents:
        found = any(a in tool_log for a in scenario.expected_agents)
        if not found:
            reasons.append(
                f"Expected one of agents {scenario.expected_agents}, "
                f"invoked {tool_log or '(none)'}"
            )

    # 3. Check forbid_writes
    if scenario.forbid_writes:
        writes = [m for m in actual_methods if m in WRITE_METHODS]
        if writes:
            reasons.append(f"Write operations forbidden but got {writes}")

    passed = len(reasons) == 0
    return passed, "; ".join(reasons) if reasons else "OK"


# ─── Evaluation runner ───────────────────────────────────────────────


def run_single(scenario: TaskScenario) -> Dict[str, Any]:
    """Execute a single task-completion scenario and return the result."""
    mock_service = MockCalendarService()
    agent, tool_log = create_tracked_orchestrator(mock_service)

    responses: List[str] = []
    error: Optional[str] = None

    try:
        t0 = time.perf_counter()
        for turn in scenario.turns:
            response = agent(turn)
            responses.append(str(response)[:300])
        elapsed = time.perf_counter() - t0
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        error = str(exc)

    passed, reason = _verify(scenario, mock_service.api_calls, tool_log)
    if error:
        passed = False
        reason = f"Error: {error}" + (f" | {reason}" if reason != "OK" else "")

    return {
        "name": scenario.name,
        "category": scenario.category,
        "turns": scenario.turns,
        "passed": passed,
        "reason": reason,
        "agents_invoked": list(tool_log),
        "api_calls": [c["method"] for c in mock_service.api_calls],
        "latency_s": round(elapsed, 2),
        "responses": responses,
        "error": error,
    }


def run_evaluation(
    scenarios: List[TaskScenario],
    quick: bool = False,
) -> List[Dict[str, Any]]:
    """Run all scenarios and return a list of result dicts."""
    if quick:
        sampled: Dict[str, List[TaskScenario]] = defaultdict(list)
        for s in scenarios:
            sampled[s.category].append(s)
        scenarios = []
        for cat_list in sampled.values():
            scenarios.extend(cat_list[:2])

    total = len(scenarios)
    results: List[Dict[str, Any]] = []

    print(f"\nRunning task-completion evaluation on {total} scenarios …\n")

    for i, scenario in enumerate(scenarios, 1):
        label = scenario.turns[0][:60]
        n_turns = len(scenario.turns)
        print(
            f"[{i:3d}/{total}] ({n_turns}T) {label}"
            f"{'…' if len(scenario.turns[0]) > 60 else ''}"
        )

        result = run_single(scenario)
        results.append(result)

        mark = "PASS" if result["passed"] else "FAIL"
        agents = ", ".join(result["agents_invoked"]) or "(none)"
        apis = ", ".join(result["api_calls"]) or "(none)"
        latency = result["latency_s"]
        print(f"        {mark}  agents=[{agents}]  apis=[{apis}]  ({latency}s)")
        if not result["passed"]:
            print(f"        reason: {result['reason'][:120]}")

    return results


# ─── Reporting ────────────────────────────────────────────────────────


def _percentile(values: List[float], pct: int) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(len(s) * pct / 100)
    return s[min(idx, len(s) - 1)]


def print_report(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Print a formatted report and return the summary dict."""
    total = len(results)
    passed = sum(r["passed"] for r in results)
    success_rate = passed / total * 100 if total else 0

    print(f"\n{'=' * 68}")
    print("  TASK COMPLETION / SUCCESS RATE REPORT")
    print(f"{'=' * 68}")
    print(f"  Overall: {passed}/{total} completed ({success_rate:.1f}%)")
    print()

    # Per-category breakdown
    categories = sorted({r["category"] for r in results})
    cat_stats: Dict[str, Dict[str, Any]] = {}
    print(
        f"  {'Category':<22s} {'Passed':>8s} {'Total':>6s} {'Success':>9s}"
    )
    print(f"  {'─' * 48}")
    for cat in categories:
        cat_results = [r for r in results if r["category"] == cat]
        cat_passed = sum(r["passed"] for r in cat_results)
        cat_rate = cat_passed / len(cat_results) * 100
        print(
            f"  {cat:<22s} {cat_passed:>8d} {len(cat_results):>6d} "
            f"{cat_rate:>8.1f}%"
        )
        cat_stats[cat] = {
            "passed": cat_passed,
            "total": len(cat_results),
            "success_pct": round(cat_rate, 1),
        }

    # Failed scenarios
    failed = [r for r in results if not r["passed"]]
    if failed:
        print(f"\n  Failed scenarios ({len(failed)}):")
        for r in failed:
            print(f'    - "{r["turns"][0][:70]}"')
            print(f"      reason: {r['reason'][:100]}")
    else:
        print("\n  All scenarios passed — perfect completion!")

    # Latency stats
    latencies = [r["latency_s"] for r in results if r.get("latency_s")]
    latency_stats: Dict[str, float] = {}
    if latencies:
        latency_stats = {
            "mean_s": round(sum(latencies) / len(latencies), 2),
            "p50_s": round(_percentile(latencies, 50), 2),
            "p95_s": round(_percentile(latencies, 95), 2),
            "max_s": round(max(latencies), 2),
        }
        print(
            f"\n  Latency: mean={latency_stats['mean_s']}s  "
            f"p50={latency_stats['p50_s']}s  "
            f"p95={latency_stats['p95_s']}s  "
            f"max={latency_stats['max_s']}s"
        )

    # API call distribution
    all_apis = [api for r in results for api in r["api_calls"]]
    if all_apis:
        api_counts: Dict[str, int] = defaultdict(int)
        for api in all_apis:
            api_counts[api] += 1
        print("\n  API call distribution:")
        for api, count in sorted(api_counts.items(), key=lambda x: -x[1]):
            print(f"    {api:<20s} {count:>4d} calls")

    print(f"{'=' * 68}\n")

    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_scenarios": total,
        "passed": passed,
        "success_rate_pct": round(success_rate, 1),
        "category_breakdown": cat_stats,
        "latency": latency_stats,
        "failed_count": len(failed),
        "failed": [
            {
                "name": r["name"],
                "turns": r["turns"],
                "reason": r["reason"],
                "agents_invoked": r["agents_invoked"],
                "api_calls": r["api_calls"],
            }
            for r in failed
        ],
    }
    return summary


def save_results(
    results: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> Path:
    """Save detailed results and summary to JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"task_completion_{ts}.json"
    payload = {"summary": summary, "results": results}
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"  Results saved to {path}\n")
    return path


# ─── pytest entry point ──────────────────────────────────────────────


def test_task_completion_core():
    """Pytest: run core scenarios and assert success rate >= 80%."""
    results = run_evaluation(CORE_SCENARIOS)
    summary = print_report(results)
    save_results(results, summary)
    assert summary["success_rate_pct"] >= 80.0, (
        f"Task completion rate {summary['success_rate_pct']}% "
        f"is below 80% threshold"
    )


# ─── CLI entry point ─────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate task completion / success rate"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run a small subset (~2 per category) for quick validation",
    )
    parser.add_argument(
        "--core",
        action="store_true",
        help="Run only the core dataset (exclude edge cases)",
    )
    args = parser.parse_args()

    dataset = CORE_SCENARIOS if args.core else TASK_SCENARIOS
    results = run_evaluation(dataset, quick=args.quick)
    summary = print_report(results)
    save_results(results, summary)

    sys.exit(0 if summary["success_rate_pct"] >= 80.0 else 1)


if __name__ == "__main__":
    main()
