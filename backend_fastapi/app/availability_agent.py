"""
AvailabilityAgent — specialized sub-agent for schedule awareness.

Uses the Google Calendar FreeBusy API (via freebusy_query) alongside
list_upcoming_events and find_free_slots to answer questions about the
user's availability, conflicts, and open time windows.

This agent is read-only: it never creates or deletes events.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, List

from strands import Agent, tool

from .strands_agent import _ensure_tz


def get_availability_tools(get_calendar_service: Callable[[], Any]) -> List[Any]:
    """Return tools for the AvailabilityAgent.

    All tools use only required str params and return str (JSON) for
    Nova Sonic compatibility.
    """

    @tool
    def current_datetime() -> str:
        """Get the current date and time in the user's local timezone."""
        now = datetime.now().astimezone()
        return now.strftime("%A %B %-d, %Y at %-I:%M %p")

    @tool
    def list_upcoming_events(time_min: str) -> str:
        """List upcoming calendar events starting from a given time."""
        from .calendar_tools import list_upcoming_events as _list

        service = get_calendar_service()
        if service is None:
            return json.dumps({"error": "Calendar not configured. Check secrets/token.json."})
        try:
            result = _list(service, time_min=_ensure_tz(time_min), max_results=20)
            return json.dumps(result, default=str)
        except Exception as e:
            print(f"[availability:list_upcoming_events] Error: {e}")
            return json.dumps({"error": f"Calendar API error: {e}"})

    @tool
    def freebusy_query(time_min: str, time_max: str) -> str:
        """Query the user's busy and free periods in a time range.

        Returns all busy intervals and all free intervals between time_min
        and time_max.  Use this to check whether the user is available at
        a specific time or to find open windows.

        Args:
            time_min: Start of the query window (ISO 8601 datetime string).
            time_max: End of the query window (ISO 8601 datetime string).
        """
        from .calendar_tools import freebusy_query as _freebusy

        service = get_calendar_service()
        if service is None:
            return json.dumps({"error": "Calendar not configured. Check secrets/token.json."})
        try:
            result = _freebusy(
                service,
                time_min=_ensure_tz(time_min),
                time_max=_ensure_tz(time_max),
            )
            return json.dumps(result, default=str)
        except Exception as e:
            print(f"[availability:freebusy_query] Error: {e}")
            return json.dumps({"error": f"Calendar API error: {e}"})

    @tool
    def find_free_slots(duration_minutes: str) -> str:
        """Find free time slots in the next 7 days that fit a given duration.

        Args:
            duration_minutes: Minimum slot length in minutes (as a string).
        """
        from .calendar_tools import find_free_slots as _find

        service = get_calendar_service()
        if service is None:
            return json.dumps({"error": "Calendar not configured. Check secrets/token.json."})
        try:
            mins = int(duration_minutes)
            result = _find(service, duration_minutes=mins, search_range_days=7)
            return json.dumps(result, default=str)
        except Exception as e:
            print(f"[availability:find_free_slots] Error: {e}")
            return json.dumps({"error": f"Calendar API error: {e}"})

    return [current_datetime, list_upcoming_events, freebusy_query, find_free_slots]


AVAILABILITY_SYSTEM_PROMPT = (
    "You are a specialized Availability Agent. Your job is to help the user "
    "understand their schedule and find open time.\n\n"
    "You can:\n"
    "- Check whether the user is free or busy at a specific date/time range "
    "(use freebusy_query).\n"
    "- List upcoming events so the user can see what is on their calendar "
    "(use list_upcoming_events).\n"
    "- Find open time slots of a requested duration in the next 7 days "
    "(use find_free_slots).\n\n"
    "Always call current_datetime first so you know what 'today' and 'now' mean.\n\n"
    "When answering:\n"
    "- Clearly state which periods are busy and which are free.\n"
    "- If the user asks 'Am I free on Thursday afternoon?', query that specific window.\n"
    "- If the user asks 'When can I schedule a 2-hour meeting this week?', "
    "use find_free_slots.\n"
    "- Be concise but complete — summarize conflicts and open windows.\n"
    "- You are READ-ONLY: you do NOT create, update, or delete events. "
    "If the user wants to book something, tell them to ask the main assistant."
)


def create_availability_agent(get_calendar_service: Callable[[], Any]) -> Agent:
    """Create an AvailabilityAgent (Strands Agent with availability tools)."""
    tools = get_availability_tools(get_calendar_service)
    return Agent(
        name="AvailabilityAgent",
        system_prompt=AVAILABILITY_SYSTEM_PROMPT,
        tools=tools,
    )
