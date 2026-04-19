"""
Orchestrator routing accuracy evaluation.

Measures how accurately the OrchestratorAgent routes user utterances to the
correct sub-agent.  Uses mock sub-agent tools (same descriptions, no real
calendar calls) so the only LLM invocation is the orchestrator's routing
decision via AWS Bedrock.

Run standalone:
    cd backend_fastapi
    python -m tests.test_routing_accuracy              # full dataset (~76 cases)
    python -m tests.test_routing_accuracy --quick       # quick smoke test (~12 cases)
    python -m tests.test_routing_accuracy --core        # core dataset only (no edge cases)

Run with pytest:
    cd backend_fastapi
    pytest tests/test_routing_accuracy.py -v

Requires:
    - AWS credentials configured (for Bedrock LLM access)
    - No Google Calendar credentials needed (calendar service is mocked)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from strands import Agent, tool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.orchestrator import ORCHESTRATOR_SYSTEM_PROMPT

from .eval_dataset import CORE_DATASET, EVAL_DATASET, EvalCase

RESULTS_DIR = Path(__file__).resolve().parent / "results"
AGENT_NAMES = [
    "calendar_agent",
    "availability_agent",
    "conflict_resolution_agent",
    "planning_agent",
    "scheduling_agent",
]


# ─── Mock orchestrator ───────────────────────────────────────────────

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


def create_mock_orchestrator() -> Tuple[Agent, List[str]]:
    """Create an orchestrator with mock sub-agent tools that track calls.

    Returns the Agent and a mutable list that records tool names in call order.
    Tool descriptions match the real orchestrator exactly so routing behaviour
    is identical.
    """
    call_log: List[str] = []

    @tool
    def calendar_agent(task: str) -> str:
        """Delegate a calendar-related task to the Calendar Agent.

        Use this for any request about the user's schedule, events,
        availability, or creating / modifying / cancelling calendar entries.

        Args:
            task: The calendar-related request or question to handle.

        Returns:
            The Calendar Agent's response.
        """
        call_log.append("calendar_agent")
        return (
            "Done. The event has been created on the user's Google Calendar. "
            "Relay the confirmation to the user."
        )

    @tool
    def availability_agent(task: str) -> str:
        """Delegate an availability or schedule-awareness question to the
        Availability Agent.

        Use this for any request about the user's free/busy status,
        schedule conflicts, open time windows, or general availability
        queries. This agent is read-only and will never create or delete events.

        Args:
            task: The availability-related request or question to handle.

        Returns:
            The Availability Agent's response.
        """
        call_log.append("availability_agent")
        return (
            "The user has 3 events today: Team Standup at 9 AM, Lunch at "
            "12 PM, and Code Review at 3 PM. They are free from 10 AM to "
            "12 PM and from 1 PM to 3 PM."
        )

    @tool
    def conflict_resolution_agent(task: str) -> str:
        """Check whether a proposed event time conflicts with existing
        calendar events, and suggest alternatives if it does.

        Call this BEFORE creating a new event. Pass a description of the
        proposed event including start and end times.

        Args:
            task: Description of the proposed event with its time window.

        Returns:
            Whether a conflict exists, details of conflicting events,
            and suggested alternative times if applicable.
        """
        call_log.append("conflict_resolution_agent")
        return "No conflicts found for the proposed time. The slot is available."

    @tool
    def planning_agent(task: str) -> str:
        """Break a high-level goal into smaller, schedulable sub-tasks
        with estimated durations and priorities.

        Use this when the user describes a goal or project that needs to
        be decomposed into concrete calendar-sized work blocks.

        Args:
            task: The high-level goal or project description, including
                any deadline the user mentioned.

        Returns:
            A structured task plan with titles, durations, and priorities.
        """
        call_log.append("planning_agent")
        return (
            "Plan created: 1. Research (60 min, P1), 2. Outline (30 min, P1), "
            "3. Draft (90 min, P2), 4. Review (30 min, P3), 5. Polish (30 min, P3)."
        )

    @tool
    def scheduling_agent(task: str) -> str:
        """Take a list of tasks with durations and schedule them as
        time-blocked events on the user's calendar.

        The agent will find free slots, propose a schedule for user
        review, and create the events after confirmation.

        Args:
            task: The list of tasks to schedule, including titles,
                durations, priorities, and any deadline constraints.

        Returns:
            The proposed or confirmed schedule details.
        """
        call_log.append("scheduling_agent")
        return "All tasks have been scheduled on the calendar for this week."

    agent = Agent(
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        system_prompt=ORCHESTRATOR_SYSTEM_PROMPT + _build_date_context(),
        tools=[
            calendar_agent,
            availability_agent,
            conflict_resolution_agent,
            planning_agent,
            scheduling_agent,
        ],
    )
    return agent, call_log


# ─── Evaluation runner ───────────────────────────────────────────────

def _is_correct(case: EvalCase, first_tool: Optional[str]) -> bool:
    if case.acceptable_agents:
        return first_tool in case.acceptable_agents
    return first_tool == case.expected_agent


def run_single(case: EvalCase) -> Dict[str, Any]:
    """Run a single eval case and return the result dict."""
    agent, call_log = create_mock_orchestrator()
    try:
        t0 = time.perf_counter()
        response = agent(case.utterance)
        elapsed = time.perf_counter() - t0

        first_tool = call_log[0] if call_log else None
        correct = _is_correct(case, first_tool)

        return {
            "utterance": case.utterance,
            "expected": case.expected_agent,
            "actual": first_tool,
            "all_tools": list(call_log),
            "correct": correct,
            "category": case.category,
            "latency_s": round(elapsed, 2),
            "response_preview": str(response)[:200],
        }
    except Exception as exc:
        return {
            "utterance": case.utterance,
            "expected": case.expected_agent,
            "actual": "ERROR",
            "all_tools": [],
            "correct": False,
            "category": case.category,
            "latency_s": 0,
            "error": str(exc),
        }


def run_evaluation(
    cases: List[EvalCase],
    quick: bool = False,
) -> List[Dict[str, Any]]:
    """Run the full evaluation and return a list of result dicts."""
    if quick:
        sampled: Dict[str, List[EvalCase]] = defaultdict(list)
        for c in cases:
            sampled[c.category].append(c)
        cases = []
        for cat_cases in sampled.values():
            cases.extend(cat_cases[:3])

    total = len(cases)
    results: List[Dict[str, Any]] = []

    print(f"\nRunning routing evaluation on {total} cases …\n")

    for i, case in enumerate(cases, 1):
        label = case.utterance[:65]
        print(f"[{i:3d}/{total}] {label}{'…' if len(case.utterance) > 65 else ''}")

        result = run_single(case)
        results.append(result)

        mark = "PASS" if result["correct"] else "FAIL"
        expected = result["expected"] or "(none)"
        actual = result["actual"] or "(none)"
        latency = result.get("latency_s", "?")
        print(f"        {mark}  expected={expected}  actual={actual}  ({latency}s)")

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
    correct = sum(r["correct"] for r in results)
    accuracy = correct / total * 100 if total else 0

    print(f"\n{'=' * 64}")
    print(f"  ROUTING ACCURACY REPORT")
    print(f"{'=' * 64}")
    print(f"  Overall accuracy : {correct}/{total} ({accuracy:.1f}%)")
    print()

    # Per-category breakdown
    categories = sorted({r["category"] for r in results})
    cat_stats: Dict[str, Dict[str, Any]] = {}
    print(f"  {'Category':<20s} {'Correct':>8s} {'Total':>6s} {'Accuracy':>9s}")
    print(f"  {'─' * 46}")
    for cat in categories:
        cat_results = [r for r in results if r["category"] == cat]
        cat_correct = sum(r["correct"] for r in cat_results)
        cat_acc = cat_correct / len(cat_results) * 100
        print(f"  {cat:<20s} {cat_correct:>8d} {len(cat_results):>6d} {cat_acc:>8.1f}%")
        cat_stats[cat] = {
            "correct": cat_correct,
            "total": len(cat_results),
            "accuracy_pct": round(cat_acc, 1),
        }

    # Confusion matrix
    all_labels = AGENT_NAMES + [None]
    label_name = {a: a for a in AGENT_NAMES}
    label_name[None] = "(none)"

    confusion: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in results:
        confusion[label_name.get(r["expected"], str(r["expected"]))][
            label_name.get(r["actual"], str(r["actual"]))
        ] += 1

    active_expected = sorted({label_name.get(r["expected"], str(r["expected"])) for r in results})
    active_actual = sorted({label_name.get(r["actual"], str(r["actual"])) for r in results})
    all_labels_str = sorted(set(active_expected) | set(active_actual))

    print(f"\n  Confusion matrix (rows = expected, cols = actual):\n")
    col_w = 8
    header = "  " + " " * 28
    for lbl in all_labels_str:
        header += f"{lbl[:col_w]:>{col_w}s} "
    print(header)
    print("  " + "─" * (28 + (col_w + 1) * len(all_labels_str)))
    for exp in active_expected:
        row = f"  {exp:<28s}"
        for act in all_labels_str:
            count = confusion[exp][act]
            row += f"{count:>{col_w}d} " if count else f"{'·':>{col_w}s} "
        print(row)

    # Misrouted cases
    misrouted = [r for r in results if not r["correct"]]
    if misrouted:
        print(f"\n  Misrouted cases ({len(misrouted)}):")
        for r in misrouted:
            exp = r["expected"] or "(none)"
            act = r["actual"] or "(none)"
            print(f"    - \"{r['utterance'][:70]}\"")
            print(f"      expected={exp}  actual={act}")
    else:
        print(f"\n  No misrouted cases — perfect accuracy!")

    # Latency stats
    latencies = [r["latency_s"] for r in results if r.get("latency_s")]
    latency_stats = {}
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

    print(f"{'=' * 64}\n")

    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_cases": total,
        "correct": correct,
        "accuracy_pct": round(accuracy, 1),
        "category_breakdown": cat_stats,
        "latency": latency_stats,
        "misrouted_count": len(misrouted),
        "misrouted": [
            {
                "utterance": r["utterance"],
                "expected": r["expected"],
                "actual": r["actual"],
            }
            for r in misrouted
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
    path = RESULTS_DIR / f"routing_accuracy_{ts}.json"
    payload = {"summary": summary, "results": results}
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"  Results saved to {path}\n")
    return path


# ─── pytest entry point ──────────────────────────────────────────────

def test_routing_accuracy_core():
    """Pytest test: run core dataset and assert accuracy >= 80%."""
    results = run_evaluation(CORE_DATASET)
    summary = print_report(results)
    save_results(results, summary)
    assert summary["accuracy_pct"] >= 80.0, (
        f"Routing accuracy {summary['accuracy_pct']}% is below 80% threshold"
    )


# ─── CLI entry point ─────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate orchestrator routing accuracy")
    parser.add_argument(
        "--quick", action="store_true",
        help="Run a small subset (~3 per category) for quick validation",
    )
    parser.add_argument(
        "--core", action="store_true",
        help="Run only the core dataset (exclude edge cases)",
    )
    args = parser.parse_args()

    dataset = CORE_DATASET if args.core else EVAL_DATASET
    results = run_evaluation(dataset, quick=args.quick)
    summary = print_report(results)
    save_results(results, summary)

    sys.exit(0 if summary["accuracy_pct"] >= 80.0 else 1)


if __name__ == "__main__":
    main()
