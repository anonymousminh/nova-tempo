"""
Calendar auth helpers.

- Loads environment from backend_fastapi/.env when present.
- Looks for an OAuth user token file and returns a cached Calendar service.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from .calendar_tools import build_calendar_service

SCOPES = ["https://www.googleapis.com/auth/calendar"]

BASE_DIR = Path(__file__).resolve().parents[1]  # backend_fastapi/
load_dotenv(BASE_DIR / ".env")

_calendar_service = None
_calendar_creds = None


def _default_token_path() -> Path:
    return BASE_DIR / "secrets" / "token.json"


def _token_path() -> Path:
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")
    return Path(creds_path) if creds_path else _default_token_path()


def get_calendar_service():
    """Return Google Calendar API service or None if not configured.

    Automatically refreshes expired tokens and re-reads token.json if the
    cached credentials become invalid (e.g. after a token was re-generated
    via ``get_token.py`` while the server was running).
    """
    global _calendar_service, _calendar_creds

    if _calendar_service is not None and _calendar_creds is not None:
        if _calendar_creds.valid:
            return _calendar_service
        if _calendar_creds.expired and _calendar_creds.refresh_token:
            try:
                from google.auth.transport.requests import Request
                _calendar_creds.refresh(Request())
                _token_path().write_text(_calendar_creds.to_json())
                print("[Calendar] Token refreshed and saved.")
                return _calendar_service
            except Exception as e:
                print(f"[Calendar] Refresh failed, will re-read token file: {e}")
        _calendar_service = None
        _calendar_creds = None

    path = _token_path()
    if not path.exists():
        return None

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_file(str(path), scopes=SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                path.write_text(creds.to_json())
                print("[Calendar] Token refreshed and saved.")
            else:
                print("[Calendar] Token invalid and cannot be refreshed. Re-run scripts/get_token.py")
                return None
        _calendar_creds = creds
        _calendar_service = build_calendar_service(creds)
        return _calendar_service
    except Exception as e:
        print(f"[Calendar] Credentials error: {e}")
        return None

