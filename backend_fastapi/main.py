"""
FastAPI server with Socket.IO for binary audio.
BidiAgent is configured as a simple "Echo" agent: receives audio chunks and sends them back.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
import uvicorn

# ---------------------------------------------------------------------------
# BidiAgent: Echo system prompt (for testing the audio pipeline)
# In production this would be replaced by a real agent (e.g. Gemini Live, ADK).
# ---------------------------------------------------------------------------
BIDI_AGENT_SYSTEM_PROMPT = "Echo"

app = FastAPI(title="Nova Tempo Audio API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Socket.IO: async ASGI server, allow all origins for dev
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
)
combined_asgi_app = socketio.ASGIApp(sio, app)


@sio.event
async def connect(sid, environ, auth):
    print(f"[BidiAgent:Echo] Client connected: {sid}")


@sio.event
async def disconnect(sid):
    print(f"[BidiAgent:Echo] Client disconnected: {sid}")


def _to_bytes(data):
    """Normalize incoming payload to bytes for echo."""
    if data is None:
        return b""
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if hasattr(data, "read"):
        return data.read()
    if isinstance(data, dict) and "base64" in data:
        import base64
        return base64.b64decode(data["base64"])
    if isinstance(data, (list, tuple)):
        return bytes(data)
    if hasattr(data, "buffer"):
        return bytes(data.buffer)
    return b""


@sio.on("audio-chunk")
async def on_audio_chunk(sid, data):
    """
    Receive binary audio chunk from client; echo it back (BidiAgent Echo behavior).
    """
    raw = _to_bytes(data)
    size = len(raw)
    if size > 0:
        print(f"[BidiAgent:Echo] Audio chunk received: {size} bytes -> echoing back")
        await sio.emit("audio_response", raw, to=sid)


@app.get("/")
async def root():
    return {"service": "Nova Tempo Audio", "agent": BIDI_AGENT_SYSTEM_PROMPT}


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        combined_asgi_app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
