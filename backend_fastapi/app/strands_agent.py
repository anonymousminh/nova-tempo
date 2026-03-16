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

        event_data = pending_actions.pop("event")
        service = get_calendar_service()
        if service is None:
            return json.dumps({"error": "Calendar not configured. Check secrets/token.json."})

        action = event_data.get("action", "create")

        try:
            if action == "delete":
                from .calendar_tools import delete_calendar_event as _delete
                result = _delete(service, event_id=event_data["event_id"])
            else:
                from .calendar_tools import create_calendar_event as _create
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
    def prepare_delete_event(event_id: str, event_title: str) -> str:
        """Prepare to delete a calendar event. Returns details for the user to
        review. The event is NOT deleted yet — call confirm_action after the user
        approves, or cancel_action if they decline.

        Args:
            event_id: The Google Calendar event ID (from list_upcoming_events).
            event_title: The title of the event (for display in the confirmation).
        """
        pending_actions["event"] = {
            "action": "delete",
            "event_id": event_id,
            "event_title": event_title,
        }
        return json.dumps({
            "status": "pending_confirmation",
            "action": "delete",
            "event_id": event_id,
            "event_title": event_title,
            "message": "Event deletion prepared. Present the details to the user and ask for confirmation.",
        })

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

    @tool
    def freebusy_query(time_min: str, time_max: str) -> str:
        """Query busy and free periods in a time range using the Google Calendar
        FreeBusy API. Returns all busy intervals and all free intervals between
        time_min and time_max.

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
            print(f"[freebusy_query] Error: {e}")
            return json.dumps({"error": f"Calendar API error: {e}"})

    return [
        current_datetime,
        list_upcoming_events,
        prepare_calendar_event,
        prepare_delete_event,
        confirm_action,
        cancel_action,
        find_free_slots,
        freebusy_query,
    ]


CALENDAR_SYSTEM_PROMPT = (
    "You are a Calendar Agent — the hands-on specialist that manages the "
    "user's Google Calendar. You handle creating events, deleting events, "
    "listing what's coming up, and finding free time.\n\n"
    "## How to respond\n"
    "- Be clear and conversational. Summarize what you're about to do (or "
    "just did) in plain language — don't dump raw data.\n"
    "- When listing events, highlight the essentials: name, day, and time. "
    "Skip technical IDs and metadata unless specifically asked.\n\n"
    "## Confirmation flow (critical)\n"
    "Every create or delete goes through a two-step safety check:\n"
    "1. **Create**: call prepare_calendar_event first. Summarize the event "
    "details naturally and ask the user to confirm.\n"
    "2. **Delete**: call list_upcoming_events to find the right event, then "
    "prepare_delete_event. Confirm with the user before proceeding.\n"
    "3. Only call confirm_action after the user explicitly says yes.\n"
    "4. If they change their mind or want adjustments, call cancel_action "
    "and help them revise.\n\n"
    "Never skip confirmation. Always wait for a clear 'yes' before executing."
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

