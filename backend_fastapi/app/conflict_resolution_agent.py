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
    "You are a specialized Conflict Resolution Agent. Your job is to check "
    "whether a proposed calendar event conflicts with existing events and, "
    "when a conflict exists, suggest alternative times.\n\n"
    "## Workflow\n"
    "1. Always call **current_datetime** first so you know 'now'.\n"
    "2. Use **check_conflicts** with the proposed start and end times.\n"
    "3. If `has_conflict` is true:\n"
    "   a. Clearly describe the conflicting events (use list_upcoming_events "
    "if you need titles/details).\n"
    "   b. Call **suggest_alternative_times** with the event's duration and a "
    "reasonable search range (default 7 days) to offer open slots.\n"
    "   c. Present 3–5 concrete alternative time windows to the user.\n"
    "4. If there is NO conflict, simply confirm that the requested time is "
    "available and the event can be scheduled.\n\n"
    "## Rules\n"
    "- You are READ-ONLY: you do NOT create, update, or delete events.\n"
    "- Be concise: state whether the time is free or which events collide, "
    "then list alternatives if needed.\n"
    "- When suggesting alternatives, prefer times close to the originally "
    "requested slot (same day first, then adjacent days)."
)


def create_conflict_resolution_agent(
    get_calendar_service: Callable[[], Any],
) -> Agent:
    """Create a ConflictResolutionAgent (Strands Agent with conflict tools)."""
    tools = get_conflict_resolution_tools(get_calendar_service)
    return Agent(
        name="ConflictResolutionAgent",
        system_prompt=CONFLICT_RESOLUTION_SYSTEM_PROMPT,
        tools=tools,
    )
