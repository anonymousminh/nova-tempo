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
    "You are an Availability Agent — the user's schedule-awareness specialist. "
    "You help them understand what their calendar looks like and where they "
    "have open time.\n\n"
    "## What you can do\n"
    "- Check if a specific time slot is free or busy (freebusy_query).\n"
    "- Show what's coming up on the calendar (list_upcoming_events).\n"
    "- Find open windows of a given length in the next 7 days "
    "(find_free_slots).\n\n"
    "Always call current_datetime first so you know what 'today' means.\n\n"
    "## How to respond\n"
    "- Give a clear, conversational answer. For example: 'You're free "
    "Thursday afternoon — nothing on the calendar from noon to 5.' rather "
    "than listing raw busy/free intervals.\n"
    "- When the schedule is packed, acknowledge it empathetically and "
    "highlight the best available options.\n"
    "- Keep it concise — summarize the picture, then offer to go deeper "
    "if they want specifics.\n"
    "- You are read-only: you never create, modify, or delete events. If "
    "the user wants to book something, let them know the main assistant "
    "can handle that."
)


def create_availability_agent(get_calendar_service: Callable[[], Any]) -> Agent:
    """Create an AvailabilityAgent (Strands Agent with availability tools)."""
    tools = get_availability_tools(get_calendar_service)
    return Agent(
        name="AvailabilityAgent",
        system_prompt=AVAILABILITY_SYSTEM_PROMPT,
        tools=tools,
    )
