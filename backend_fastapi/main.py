"""Entrypoint wrapper for the FastAPI Socket.IO app.

Keeps `python main.py` working while the actual app lives in `app/`.
"""

import uvicorn

from app.main import combined_asgi_app


if __name__ == "__main__":
    uvicorn.run(combined_asgi_app, host="0.0.0.0", port=8000, log_level="info")
