"""
SchedulingAgent — specialized sub-agent for batch time-block scheduling.

Takes a set of tasks (typically from the PlanningAgent) and places them on
the user's Google Calendar as time-blocked events.  The agent finds free
slots, proposes a schedule, and creates events after user confirmation.

Flow:
  1. Receive task list with durations from the orchestrator.
  2. Query free slots to build a proposed schedule.
  3. Call ``prepare_schedule`` to stage all events for review.
  4. Present the proposed schedule to the user.
  5. On approval → ``confirm_schedule`` creates all events.
  6. On decline  → ``cancel_schedule`` discards the batch.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, List

from strands import Agent, tool

from .strands_agent import _ensure_tz


def get_scheduling_tools(get_calendar_service: Callable[[], Any]) -> List[Any]:
    """Return tools for the SchedulingAgent.

    All tools use only required str params and return str (JSON) for
    Nova Sonic compatibility.
    """

    pending_schedule: dict[str, list[dict[str, Any]]] = {}

    @tool
    def current_datetime() -> str:
        """Get the current date and time in the user's local timezone."""
        now = datetime.now().astimezone()
        return now.strftime("%A %B %-d, %Y at %-I:%M %p")

    @tool
    def list_upcoming_events(time_min: str) -> str:
        """List upcoming calendar events starting from a given time.

        Args:
            time_min: Start time for the listing (ISO 8601 datetime string).
        """
        from .calendar_tools import list_upcoming_events as _list

        service = get_calendar_service()
        if service is None:
            return json.dumps({"error": "Calendar not configured."})
        try:
            result = _list(service, time_min=_ensure_tz(time_min), max_results=20)
            return json.dumps(result, default=str)
        except Exception as e:
            return json.dumps({"error": f"Calendar API error: {e}"})

    @tool
    def find_free_slots(duration_minutes: str, search_range_days: str) -> str:
        """Find free time slots that fit a given duration.

        Args:
            duration_minutes: Minimum slot length in minutes (as a string).
            search_range_days: How many days ahead to search (as a string).
        """
        from .calendar_tools import find_free_slots as _find

        service = get_calendar_service()
        if service is None:
            return json.dumps({"error": "Calendar not configured."})
        try:
            result = _find(
                service,
                duration_minutes=int(duration_minutes),
                search_range_days=int(search_range_days),
            )
            return json.dumps(result, default=str)
        except Exception as e:
            return json.dumps({"error": f"Calendar API error: {e}"})

    @tool
    def freebusy_query(time_min: str, time_max: str) -> str:
        """Query busy and free periods in a time range.

        Args:
            time_min: Start of the query window (ISO 8601 datetime string).
            time_max: End of the query window (ISO 8601 datetime string).
        """
        from .calendar_tools import freebusy_query as _freebusy

        service = get_calendar_service()
        if service is None:
            return json.dumps({"error": "Calendar not configured."})
        try:
            result = _freebusy(
                service,
                time_min=_ensure_tz(time_min),
                time_max=_ensure_tz(time_max),
            )
            return json.dumps(result, default=str)
        except Exception as e:
            return json.dumps({"error": f"Calendar API error: {e}"})

    @tool
    def prepare_schedule(events_json: str) -> str:
        """Stage a batch of time-block events for user review.

        The events are NOT created yet — call confirm_schedule after the
        user approves, or cancel_schedule if they decline.

        Args:
            events_json: A JSON array of event objects.  Each object must
                have: "summary" (str), "start_time" (ISO 8601 str),
                "end_time" (ISO 8601 str).  Optional: "description" (str).

        Example input:
            [
              {"summary": "Research topic", "start_time": "2026-03-16T09:00:00", "end_time": "2026-03-16T10:00:00"},
              {"summary": "Create slides",  "start_time": "2026-03-16T14:00:00", "end_time": "2026-03-16T15:30:00"}
            ]
        """
        try:
            events = json.loads(events_json)
            if not isinstance(events, list) or len(events) == 0:
                return json.dumps({"error": "events_json must be a non-empty JSON array."})

            prepared: list[dict[str, Any]] = []
            for ev in events:
                entry = {
                    "summary": ev["summary"],
                    "start_time": _ensure_tz(ev["start_time"]),
                    "end_time": _ensure_tz(ev["end_time"]),
                    "description": ev.get("description"),
                }
                prepared.append(entry)

            pending_schedule["events"] = prepared
            return json.dumps({
                "status": "pending_confirmation",
                "event_count": len(prepared),
                "events": [
                    {"summary": e["summary"], "start_time": e["start_time"], "end_time": e["end_time"]}
                    for e in prepared
                ],
                "message": "Schedule prepared. Present the proposed time blocks to the user and ask for confirmation.",
            }, default=str)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            return json.dumps({"error": f"Invalid events_json: {e}"})

    @tool
    def confirm_schedule() -> str:
        """Create all staged time-block events on the calendar.

        Only call this after the user explicitly approves the proposed
        schedule.
        """
        if "events" not in pending_schedule:
            return json.dumps({"error": "No pending schedule to confirm."})

        from .calendar_tools import create_calendar_event as _create

        service = get_calendar_service()
        if service is None:
            return json.dumps({"error": "Calendar not configured."})

        events = pending_schedule.pop("events")
        created: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for ev in events:
            try:
                result = _create(
                    service,
                    summary=ev["summary"],
                    start_time=ev["start_time"],
                    end_time=ev["end_time"],
                    description=ev.get("description"),
                )
                created.append({
                    "summary": ev["summary"],
                    "id": result.get("id", ""),
                    "start_time": ev["start_time"],
                    "end_time": ev["end_time"],
                })
            except Exception as e:
                errors.append({"summary": ev["summary"], "error": str(e)})

        return json.dumps({
            "status": "completed",
            "created_count": len(created),
            "created": created,
            "error_count": len(errors),
            "errors": errors,
        }, default=str)

    @tool
    def cancel_schedule() -> str:
        """Discard the staged schedule. Call this when the user declines
        or wants to adjust the proposed time blocks."""
        if "events" not in pending_schedule:
            return json.dumps({"error": "No pending schedule to cancel."})
        pending_schedule.pop("events")
        return json.dumps({"status": "cancelled", "message": "Proposed schedule discarded."})

    return [
        current_datetime,
        list_upcoming_events,
        find_free_slots,
        freebusy_query,
        prepare_schedule,
        confirm_schedule,
        cancel_schedule,
    ]


SCHEDULING_SYSTEM_PROMPT = """\
You are a specialized Scheduling Agent. Your job is to take a list of \
tasks (with estimated durations) and schedule them as time-blocked events \
on the user's Google Calendar.

## Workflow

1. Call **current_datetime** to know "now".
2. Use **find_free_slots** or **freebusy_query** to discover available \
windows in the user's calendar. Search enough days ahead to fit all tasks \
(typically 7–14 days, or until a stated deadline).
3. Assign each task to a free slot, respecting:
   - **Priority order**: schedule higher-priority tasks earlier.
   - **Realistic working hours**: prefer 8 AM – 6 PM local time unless the \
user indicates otherwise.
   - **Breaks**: avoid stacking tasks back-to-back — leave at least a 15-min \
gap between blocks when possible.
   - **Deadline**: if a deadline was given, ensure all tasks finish before it.
4. Call **prepare_schedule** with the full batch of events (as a JSON array).
5. Present the proposed schedule clearly (day, time, task name, duration) \
and ask the user for confirmation.
6. On approval → call **confirm_schedule** to create all events.
7. On decline → call **cancel_schedule** and help the user adjust.

## Rules
- You only CREATE time-block events — you do not modify or delete existing ones.
- If there are not enough free slots before the deadline, warn the user and \
propose the best-effort schedule you can.
- Keep event titles concise; put extra context in the description field.
"""


def create_scheduling_agent(
    get_calendar_service: Callable[[], Any],
) -> Agent:
    """Create a SchedulingAgent (Strands Agent for batch time-block scheduling)."""
    tools = get_scheduling_tools(get_calendar_service)
    return Agent(
        name="SchedulingAgent",
        system_prompt=SCHEDULING_SYSTEM_PROMPT,
        tools=tools,
    )
