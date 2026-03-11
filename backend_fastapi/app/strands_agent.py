"""
CalendarAgent — specialized sub-agent for Google Calendar operations.

Builds an Agent (or tool list for BidiAgent) that can list events, create events,
and find free slots.  Calendar service is injected via a getter so credentials
are loaded lazily.

Mutating actions (create event) go through a two-phase confirmation flow:
  1. prepare_calendar_event  → stores params, returns summary for user review
  2. confirm_action          → executes the pending action
  3. cancel_action           → discards the pending action

NOTE: Nova Sonic BidiAgent requires simple tool schemas — all params must be
required (no defaults), no union types (str | None), and return str.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, List

from strands import Agent, tool


def _ensure_tz(dt_str: str) -> str:
    """Ensure a datetime string has timezone info (required by Google Calendar API).

    Handles bare datetimes like '2026-03-10T00:00:00' by appending the local
    UTC offset.  Strings that already have 'Z' or '+'/'-' offset pass through.
    Plain dates like '2026-03-10' get 'T00:00:00' + local offset appended.
    """
    s = dt_str.strip()
    if not s:
        return s
    if s.endswith("Z") or "+" in s[10:] or (len(s) > 19 and "-" in s[19:]):
        return s
    try:
        if "T" in s:
            dt = datetime.fromisoformat(s)
        else:
            dt = datetime.fromisoformat(s + "T00:00:00")
        local_dt = dt.astimezone()
        return local_dt.isoformat()
    except (ValueError, TypeError):
        return s


def get_calendar_tools(get_calendar_service: Callable[[], Any]) -> List[Any]:
    """
    Return the calendar tools for use with Agent or BidiAgent.
    All tools use only required str/int params and return str (JSON) for
    Nova Sonic compatibility.
    """

    pending_actions: dict[str, dict[str, Any]] = {}

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
            result = _list(service, time_min=_ensure_tz(time_min), max_results=10)
            return json.dumps(result, default=str)
        except Exception as e:
            print(f"[list_upcoming_events] Error: {e}")
            return json.dumps({"error": f"Calendar API error: {e}"})

    @tool
    def prepare_calendar_event(summary: str, start_time: str, end_time: str, description: str) -> str:
        """Prepare a calendar event for creation. Returns event details for the user
        to review. The event is NOT created yet — call confirm_action after the user
        approves, or cancel_action if they decline."""
        pending_actions["event"] = {
            "summary": summary,
            "start_time": _ensure_tz(start_time),
            "end_time": _ensure_tz(end_time),
            "description": description if description else None,
        }
        return json.dumps({
            "status": "pending_confirmation",
            "summary": summary,
            "start_time": start_time,
            "end_time": end_time,
            "description": description,
            "message": "Event prepared. Present the details to the user and ask for confirmation.",
        })

    @tool
    def confirm_action() -> str:
        """Execute the pending action after the user has confirmed. Only call this
        when the user explicitly says yes / confirms."""
        if "event" not in pending_actions:
            return json.dumps({"error": "No pending action to confirm."})

        from .calendar_tools import create_calendar_event as _create

        event_data = pending_actions.pop("event")
        service = get_calendar_service()
        if service is None:
            return json.dumps({"error": "Calendar not configured. Check secrets/token.json."})
        try:
            result = _create(
                service,
                summary=event_data["summary"],
                start_time=event_data["start_time"],
                end_time=event_data["end_time"],
                description=event_data["description"],
            )
            return json.dumps(result, default=str)
        except Exception as e:
            print(f"[confirm_action] Error: {e}")
            return json.dumps({"error": f"Calendar API error: {e}"})

    @tool
    def cancel_action() -> str:
        """Cancel the pending action. Call this when the user declines or wants to
        change the event details."""
        if "event" not in pending_actions:
            return json.dumps({"error": "No pending action to cancel."})
        pending_actions.pop("event")
        return json.dumps({"status": "cancelled", "message": "Pending action cancelled."})

    @tool
    def find_free_slots(duration_minutes: str) -> str:
        """Find free time slots in the next 7 days that fit a given duration."""
        from .calendar_tools import find_free_slots as _find

        service = get_calendar_service()
        if service is None:
            return json.dumps({"error": "Calendar not configured. Check secrets/token.json."})
        try:
            mins = int(duration_minutes)
            result = _find(service, duration_minutes=mins, search_range_days=7)
            return json.dumps(result, default=str)
        except Exception as e:
            print(f"[find_free_slots] Error: {e}")
            return json.dumps({"error": f"Calendar API error: {e}"})

    return [
        current_datetime,
        list_upcoming_events,
        prepare_calendar_event,
        confirm_action,
        cancel_action,
        find_free_slots,
    ]


CALENDAR_SYSTEM_PROMPT = (
    "You are a specialized Calendar Agent. You manage the user's Google Calendar: "
    "listing upcoming events, creating events, and finding free time slots.\n"
    "Use the calendar tools when the user asks about their schedule, wants to add an event, "
    "or needs a time suggestion.\n\n"
    "IMPORTANT — Confirmation protocol for creating events:\n"
    "1. When the user wants to create an event, call prepare_calendar_event FIRST.\n"
    "2. Present the prepared event details to the user and ask them to confirm.\n"
    "3. ONLY call confirm_action after the user explicitly agrees (e.g. 'yes', 'go ahead', 'confirm').\n"
    "4. If the user declines or wants changes, call cancel_action and help them adjust.\n"
    "NEVER skip confirmation — always wait for the user's explicit approval before calling confirm_action."
)

# Backward-compat alias used by earlier code.
CONFIRMATION_SYSTEM_PROMPT = CALENDAR_SYSTEM_PROMPT


def create_calendar_agent(get_calendar_service: Callable[[], Any]) -> Agent:
    """Create a CalendarAgent (Strands Agent with calendar tools)."""
    tools = get_calendar_tools(get_calendar_service)
    return Agent(
        name="CalendarAgent",
        system_prompt=CALENDAR_SYSTEM_PROMPT,
        tools=tools,
    )


# Backward-compat alias.
create_strands_agent = create_calendar_agent

