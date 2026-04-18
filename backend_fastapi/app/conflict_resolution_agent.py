"""
ConflictResolutionAgent — specialized sub-agent for proactive conflict detection.

Before a new event is scheduled, the orchestrator can delegate to this agent
to check the proposed time window for conflicts using the Google Calendar
FreeBusy API.  If a conflict is found the agent describes the overlap and
suggests alternative times.

This agent is read-only: it never creates, updates, or deletes events.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Callable, List

from strands import Agent, tool

from .strands_agent import _ensure_tz


def get_conflict_resolution_tools(
    get_calendar_service: Callable[[], Any],
) -> List[Any]:
    """Return tools for the ConflictResolutionAgent.

    All tools use only required str params and return str (JSON) for
    Nova Sonic compatibility.
    """

    @tool
    def current_datetime() -> str:
        """Get the current date and time in the user's local timezone."""
        now = datetime.now().astimezone()
        return now.strftime("%A %B %-d, %Y at %-I:%M %p")

    @tool
    def check_conflicts(proposed_start: str, proposed_end: str) -> str:
        """Check whether a proposed event time conflicts with existing events.

        Queries the FreeBusy API for the proposed window and returns any
        overlapping busy periods.  An empty ``conflicts`` list means the
        slot is free.

        Args:
            proposed_start: Proposed event start (ISO 8601 datetime string).
            proposed_end:   Proposed event end   (ISO 8601 datetime string).
        """
        from .calendar_tools import freebusy_query as _freebusy

        service = get_calendar_service()
        if service is None:
            return json.dumps({"error": "Calendar not configured."})
        try:
            result = _freebusy(
                service,
                time_min=_ensure_tz(proposed_start),
                time_max=_ensure_tz(proposed_end),
            )
            busy = result.get("primary", {}).get("busy", [])
            return json.dumps({
                "has_conflict": len(busy) > 0,
                "conflicts": busy,
                "proposed_start": proposed_start,
                "proposed_end": proposed_end,
            }, default=str)
        except Exception as e:
            return json.dumps({"error": f"Calendar API error: {e}"})

    @tool
    def suggest_alternative_times(duration_minutes: str, search_range_days: str) -> str:
        """Find alternative free time slots when a conflict is detected.

        Args:
            duration_minutes:  Desired event length in minutes (as a string).
            search_range_days: How many days ahead to search (as a string).
        """
        from .calendar_tools import find_free_slots as _find

        service = get_calendar_service()
        if service is None:
            return json.dumps({"error": "Calendar not configured."})
        try:
            mins = int(duration_minutes)
            days = int(search_range_days)
            result = _find(service, duration_minutes=mins, search_range_days=days)
            return json.dumps(result, default=str)
        except Exception as e:
            return json.dumps({"error": f"Calendar API error: {e}"})

    @tool
    def freebusy_query(time_min: str, time_max: str) -> str:
        """Query the user's busy and free periods in an arbitrary time range.

        Returns all busy intervals and all free intervals between time_min
        and time_max. Useful for scanning a broader window around the
        proposed event to find nearby openings.

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
    def list_upcoming_events(time_min: str) -> str:
        """List upcoming calendar events starting from a given time.

        Useful for showing the user exactly which events conflict with
        their proposed time.

        Args:
            time_min: Start time for the listing (ISO 8601 datetime string).
        """
        from .calendar_tools import list_upcoming_events as _list

        service = get_calendar_service()
        if service is None:
            return json.dumps({"error": "Calendar not configured."})
        try:
            result = _list(service, time_min=_ensure_tz(time_min), max_results=10)
            return json.dumps(result, default=str)
        except Exception as e:
            return json.dumps({"error": f"Calendar API error: {e}"})

    return [
        current_datetime,
        check_conflicts,
        suggest_alternative_times,
        freebusy_query,
        list_upcoming_events,
    ]


CONFLICT_RESOLUTION_SYSTEM_PROMPT = (
    "You are a Conflict Resolution Agent — you catch scheduling collisions "
    "before they happen and help find better times.\n\n"
    "## How it works\n"
    "1. Call **current_datetime** so you know 'now'.\n"
    "2. Use **check_conflicts** with the proposed start and end times.\n"
    "3. If there's a conflict:\n"
    "   - Explain what's in the way (use list_upcoming_events for event "
    "names if needed). Be specific but brief: 'That overlaps with your "
    "Team Standup from 9 to 9:30.'\n"
    "   - Call **suggest_alternative_times** and offer 3–5 nearby "
    "alternatives, preferring same-day slots first.\n"
    "4. If the time is clear, confirm it simply: 'That slot is wide open — "
    "good to go.'\n\n"
    "## Response style\n"
    "- Be helpful, not alarming. A conflict isn't a crisis — it's just a "
    "scheduling puzzle to solve.\n"
    "- Lead with the answer (conflict or clear), then give details.\n"
    "- When suggesting alternatives, frame them as options, not commands: "
    "'How about 2 PM instead?' rather than 'Alternative: 14:00–15:00.'\n"
    "- You are read-only — you never create, modify, or delete events."
)


def create_conflict_resolution_agent(
    get_calendar_service: Callable[[], Any],
) -> Agent:
    """Create a ConflictResolutionAgent (Strands Agent with conflict tools)."""
    tools = get_conflict_resolution_tools(get_calendar_service)
    return Agent(
        name="ConflictResolutionAgent",
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        system_prompt=CONFLICT_RESOLUTION_SYSTEM_PROMPT,
        tools=tools,
    )
