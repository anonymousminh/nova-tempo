"""
Modular calendar tools for Strands Agents.

These are Python functions the agent can "call" to list events, create events,
and find free slots. They expect an authenticated Google Calendar API service
(build once from credentials, then pass into each tool).
"""

from __future__ import annotations

__all__ = [
    "build_calendar_service",
    "list_upcoming_events",
    "create_calendar_event",
    "delete_calendar_event",
    "find_free_slots",
]

from datetime import datetime, timezone, timedelta
from typing import Any

# Type for the Google Calendar API service (build from googleapiclient.discovery)
CalendarService = Any

PRIMARY_CALENDAR_ID = "primary"


def _local_timezone_name() -> str:
    """Return IANA timezone name (e.g. 'America/Denver') for event creation."""
    try:
        from pathlib import Path

        tz_link = Path("/etc/localtime").resolve()
        parts = tz_link.parts
        idx = parts.index("zoneinfo")
        return "/".join(parts[idx + 1 :])
    except Exception:
        pass
    import time

    return time.tzname[0]


DEFAULT_TIMEZONE = _local_timezone_name()


def _to_local_friendly(iso_str: str) -> str:
    """Convert an ISO datetime string to a human-friendly local time string.

    e.g. "2025-03-07T02:00:00Z" → "Thursday Mar 6, 2025 at 8:00 PM" (in local tz).
    All-day dates like "2025-03-07" pass through unchanged.
    """
    if not iso_str or "T" not in iso_str:
        return iso_str
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        local_dt = dt.astimezone()
        return local_dt.strftime("%A %B %-d, %Y at %-I:%M %p")
    except (ValueError, TypeError):
        return iso_str


def build_calendar_service(credentials: Any) -> CalendarService:
    """
    Build a Google Calendar API service from credentials.
    Use this once when the agent starts (or when handling a user session),
    then pass the returned service into the tool functions.
    """
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=credentials)


def list_upcoming_events(
    service: CalendarService,
    time_min: str,
    max_results: int = 10,
    calendar_id: str = PRIMARY_CALENDAR_ID,
) -> list[dict[str, str]]:
    """List upcoming events on the primary (or given) calendar."""
    events_result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    events = events_result.get("items", [])
    out: list[dict[str, str]] = []
    for ev in events:
        start = ev.get("start", {}) or {}
        end = ev.get("end", {}) or {}
        start_str = start.get("dateTime") or start.get("date") or ""
        end_str = end.get("dateTime") or end.get("date") or ""
        out.append(
            {
                "id": ev.get("id", ""),
                "title": ev.get("summary", "(No title)"),
                "start": _to_local_friendly(start_str),
                "end": _to_local_friendly(end_str),
            }
        )
    return out


def create_calendar_event(
    service: CalendarService,
    summary: str,
    start_time: str,
    end_time: str,
    description: str | None = None,
    calendar_id: str = PRIMARY_CALENDAR_ID,
) -> dict[str, Any]:
    """Create a calendar event."""
    body: dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start_time, "timeZone": DEFAULT_TIMEZONE},
        "end": {"dateTime": end_time, "timeZone": DEFAULT_TIMEZONE},
    }
    if description is not None:
        body["description"] = description
    event = service.events().insert(calendarId=calendar_id, body=body).execute()
    return event


def delete_calendar_event(
    service: CalendarService,
    event_id: str,
    calendar_id: str = PRIMARY_CALENDAR_ID,
) -> dict[str, Any]:
    """Delete a calendar event by its ID."""
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    return {"status": "deleted", "event_id": event_id}


def find_free_slots(
    service: CalendarService,
    duration_minutes: int,
    search_range_days: int = 7,
    calendar_id: str = PRIMARY_CALENDAR_ID,
) -> list[dict[str, str]]:
    """Find free time slots that can fit the requested duration."""
    now = datetime.now(timezone.utc)
    time_min = now.isoformat().replace("+00:00", "Z")
    time_max = (now + timedelta(days=search_range_days)).isoformat().replace("+00:00", "Z")
    body = {"timeMin": time_min, "timeMax": time_max, "items": [{"id": calendar_id}]}
    response = service.freebusy().query(body=body).execute()
    calendars = response.get("calendars", {})
    busy_list = calendars.get(calendar_id, {}).get("busy", [])

    busy_tuples: list[tuple[datetime, datetime]] = []
    for b in busy_list:
        s = b.get("start")
        e = b.get("end")
        if s and e:
            try:
                start_dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(e.replace("Z", "+00:00"))
                busy_tuples.append((start_dt, end_dt))
            except (ValueError, TypeError):
                continue

    busy_tuples.sort(key=lambda x: x[0])
    merged: list[tuple[datetime, datetime]] = []
    for start_dt, end_dt in busy_tuples:
        if merged and start_dt <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end_dt))
        else:
            merged.append((start_dt, end_dt))

    duration_delta = timedelta(minutes=duration_minutes)
    time_max_dt = datetime.fromisoformat(time_max.replace("Z", "+00:00"))
    free_slots: list[dict[str, str]] = []

    def slot_fits(s_start: datetime, s_end: datetime) -> bool:
        return (s_end - s_start) >= duration_delta

    def to_iso(dt: datetime) -> str:
        return dt.isoformat().replace("+00:00", "Z")

    def add_slot(s_start: datetime) -> None:
        s_end = s_start + duration_delta
        free_slots.append({"start": _to_local_friendly(to_iso(s_start)), "end": _to_local_friendly(to_iso(s_end))})

    if not merged:
        if slot_fits(now, time_max_dt):
            add_slot(now)
    else:
        first_start, _ = merged[0]
        if slot_fits(now, first_start):
            add_slot(now)

        for i in range(len(merged) - 1):
            gap_start = merged[i][1]
            gap_end = merged[i + 1][0]
            if slot_fits(gap_start, gap_end):
                add_slot(gap_start)

        last_end = merged[-1][1]
        if slot_fits(last_end, time_max_dt):
            add_slot(last_end)

    return free_slots

