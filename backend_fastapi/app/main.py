"""
FastAPI server with Socket.IO — voice-only mode.

Voice path: browser mic → Socket.IO → BidiAgent (Nova Sonic) with
multi-agent orchestrator tools (CalendarAgent via "Agents as Tools").

Direct tool calls (REST + Socket.IO ``tool`` event) still go straight to
the calendar tools for low-level / programmatic access.
"""

from fastapi import FastAPI, Request, Response
from uuid import uuid4
from fastapi.middleware.cors import CORSMiddleware
import socketio

from .calendar_auth import get_calendar_service
from .calendar_tools import (
    list_upcoming_events,
    create_calendar_event,
    delete_calendar_event,
    find_free_slots,
)

# ---------------------------------------------------------------------------
# Direct tool definitions (for REST / Socket.IO `tool` event)
# ---------------------------------------------------------------------------
_pending_direct_actions: dict[str, dict] = {}


def _prepare_event(_service, **kw):
    _pending_direct_actions["event"] = {
        "summary": kw["summary"],
        "start_time": kw["start_time"],
        "end_time": kw["end_time"],
        "description": kw.get("description"),
    }
    return {
        "status": "pending_confirmation",
        **_pending_direct_actions["event"],
        "message": "Event prepared. Call confirm_action to create it or cancel_action to discard.",
    }


def _prepare_delete(_service, **kw):
    _pending_direct_actions["event"] = {
        "action": "delete",
        "event_id": kw["event_id"],
    }
    return {
        "status": "pending_confirmation",
        "action": "delete",
        "event_id": kw["event_id"],
        "message": "Delete prepared. Call confirm_action to delete or cancel_action to discard.",
    }


def _confirm_event(_service, **_kw):
    if "event" not in _pending_direct_actions:
        raise ValueError("No pending action to confirm.")
    data = _pending_direct_actions.pop("event")
    if data.get("action") == "delete":
        return delete_calendar_event(_service, event_id=data["event_id"])
    return create_calendar_event(
        _service,
        summary=data["summary"],
        start_time=data["start_time"],
        end_time=data["end_time"],
        description=data["description"],
    )


def _cancel_event(_service, **_kw):
    if "event" not in _pending_direct_actions:
        raise ValueError("No pending action to cancel.")
    _pending_direct_actions.pop("event")
    return {"status": "cancelled", "message": "Pending action cancelled."}


BIDI_AGENT_TOOLS = [
    {
        "name": "list_upcoming_events",
        "description": "List upcoming calendar events.",
        "parameters": ["time_min", "max_results"],
        "runner": lambda s, **kw: list_upcoming_events(
            s, time_min=kw["time_min"], max_results=kw.get("max_results", 10)
        ),
    },
    {
        "name": "prepare_calendar_event",
        "description": "Prepare a calendar event (requires confirmation via confirm_action).",
        "parameters": ["summary", "start_time", "end_time", "description"],
        "runner": _prepare_event,
    },
    {
        "name": "prepare_delete_event",
        "description": "Prepare to delete a calendar event (requires confirmation via confirm_action).",
        "parameters": ["event_id"],
        "runner": _prepare_delete,
    },
    {
        "name": "confirm_action",
        "description": "Confirm and execute the pending prepared action.",
        "parameters": [],
        "runner": _confirm_event,
    },
    {
        "name": "cancel_action",
        "description": "Cancel the pending prepared action.",
        "parameters": [],
        "runner": _cancel_event,
    },
    {
        "name": "find_free_slots",
        "description": "Find free time slots.",
        "parameters": ["duration_minutes", "search_range_days"],
        "runner": lambda s, **kw: find_free_slots(
            s,
            duration_minutes=kw["duration_minutes"],
            search_range_days=kw.get("search_range_days", 7),
        ),
    },
]

# ---------------------------------------------------------------------------
# App + Socket.IO
# ---------------------------------------------------------------------------
app = FastAPI(title="Nova Tempo API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
combined_asgi_app = socketio.ASGIApp(sio, app)

_sid_to_user: dict[str, str] = {}


@sio.event
async def connect(sid, environ, auth):
    user_id = (auth or {}).get("user_id") if isinstance(auth, dict) else None
    if user_id:
        _sid_to_user[sid] = user_id
    print(f"[Server] Client connected: {sid}  user={user_id}")


@sio.event
async def disconnect(sid):
    from .voice_session import stop_voice

    _sid_to_user.pop(sid, None)
    await stop_voice(sid)
    print(f"[Server] Client disconnected: {sid}")


# ---------------------------------------------------------------------------
# Voice sessions (browser mic <-> BidiAgent via Socket.IO)
# ---------------------------------------------------------------------------
@sio.on("voice_start")
async def on_voice_start(sid, payload=None):
    from .voice_session import start_voice

    try:
        user_id = _sid_to_user.get(sid)
        config = await start_voice(sio, sid, user_id=user_id)
        await sio.emit("voice_started", config, to=sid)
        print(f"[Voice] Session started for {sid}  user={user_id}")
    except Exception as e:
        print(f"[Voice] Start error: {e}")
        await sio.emit("voice_error", {"error": str(e)}, to=sid)


@sio.on("voice_audio_in")
async def on_voice_audio_in(sid, payload):
    from .voice_session import send_audio

    audio = payload.get("audio", "") if isinstance(payload, dict) else ""
    if audio:
        await send_audio(sid, audio)


@sio.on("voice_stop")
async def on_voice_stop(sid, payload=None):
    from .voice_session import stop_voice

    await stop_voice(sid)
    await sio.emit("voice_stopped", {}, to=sid)
    print(f"[Voice] Session stopped for {sid}")


# ---------------------------------------------------------------------------
# Direct tool calls (client or agent dispatches by name)
# ---------------------------------------------------------------------------
def _run_agent_tool(name: str, params: dict) -> dict:
    service = get_calendar_service()
    if service is None:
        return {
            "ok": False,
            "error": "Calendar not configured. Add secrets/token.json or set GOOGLE_CREDENTIALS_PATH.",
        }
    for t in BIDI_AGENT_TOOLS:
        if t["name"] == name:
            try:
                result = t["runner"](service, **params)
                return {"ok": True, "result": result}
            except Exception as e:
                return {"ok": False, "error": str(e)}
    return {"ok": False, "error": f"Unknown tool: {name}"}


@sio.on("tool")
async def on_tool(sid, payload):
    if not isinstance(payload, dict):
        await sio.emit("tool_result", {"ok": False, "error": "Payload must be an object"}, to=sid)
        return
    name = payload.get("name")
    params = payload.get("params") or {}
    if not name:
        await sio.emit("tool_result", {"ok": False, "error": "Missing tool name"}, to=sid)
        return
    out = _run_agent_tool(name, params)
    print(f"[Tool] {name} -> ok={out.get('ok')}")
    await sio.emit("tool_result", out, to=sid)


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------
@app.get("/")
async def root():
    return {"service": "Nova Tempo", "mode": "voice-calendar-assistant"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/agent/tools")
async def agent_tools():
    return {
        "tools": [
            {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
            for t in BIDI_AGENT_TOOLS
        ]
    }


@app.post("/agent/tool")
async def agent_tool_call(payload: dict):
    name = payload.get("name")
    params = payload.get("params") or {}
    if not name:
        return {"ok": False, "error": "Missing tool name"}
    return _run_agent_tool(name, params)


# ---------------------------------------------------------------------------
# Guest identity using cookie based session
# ---------------------------------------------------------------------------
COOKIE_NAME = "nova_user_id"

@app.get("/id")
async def get_nova_user_id(request: Request, response: Response):
    # Read the existing cookie
    nova_user_id = request.cookies.get(COOKIE_NAME)

    # If it's missing, generate a new one and set the cookie
    if not nova_user_id:
        nova_user_id = f"nova_user_{str(uuid4())}"
        response.set_cookie(
            key=COOKIE_NAME,
            value=nova_user_id,
            httponly=True,
            secure=False,
            samesite="lax",
        )

    return {"nova_user_id": nova_user_id}