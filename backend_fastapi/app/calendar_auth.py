"""
Calendar auth helpers.

- Loads environment from backend_fastapi/.env when present.
- Reads OAuth token from the GOOGLE_TOKEN_JSON env var (for production /
  Render) or from a local file (for development).
- Returns a cached Calendar service and auto-refreshes expired tokens.
"""

from __future__ import annotations

import json
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


def _load_credentials():
    """Load Google OAuth credentials from env var or file.

    Priority:
    1. GOOGLE_TOKEN_JSON env var (raw JSON string — ideal for Render / production)
    2. File at GOOGLE_CREDENTIALS_PATH or secrets/token.json (local dev)
    """
    from google.oauth2.credentials import Credentials

    token_json = os.environ.get("GOOGLE_TOKEN_JSON")
    if token_json:
        try:
            info = json.loads(token_json)
            return Credentials.from_authorized_user_info(info, scopes=SCOPES)
        except Exception as e:
            print(f"[Calendar] Failed to parse GOOGLE_TOKEN_JSON: {e}")
            return None

    path = _token_path()
    if not path.exists():
        print("[Calendar] No token found. Set GOOGLE_TOKEN_JSON env var or run scripts/get_token.py")
        return None

    try:
        return Credentials.from_authorized_user_file(str(path), scopes=SCOPES)
    except Exception as e:
        print(f"[Calendar] Failed to load token file: {e}")
        return None


def _persist_refreshed_token(creds):
    """Write updated token back to env-var source or file."""
    if os.environ.get("GOOGLE_TOKEN_JSON"):
        os.environ["GOOGLE_TOKEN_JSON"] = creds.to_json()
        print("[Calendar] Token refreshed (updated in-memory env var).")
    else:
        try:
            _token_path().write_text(creds.to_json())
            print("[Calendar] Token refreshed and saved to file.")
        except Exception as e:
            print(f"[Calendar] Token refreshed but could not save to file: {e}")


def get_calendar_service():
    """Return Google Calendar API service or None if not configured.

    Automatically refreshes expired tokens and re-reads the token source
    if the cached credentials become invalid.
    """
    global _calendar_service, _calendar_creds

    if _calendar_service is not None and _calendar_creds is not None:
        if _calendar_creds.valid:
            return _calendar_service
        if _calendar_creds.expired and _calendar_creds.refresh_token:
            try:
                from google.auth.transport.requests import Request
                _calendar_creds.refresh(Request())
                _persist_refreshed_token(_calendar_creds)
                return _calendar_service
            except Exception as e:
                print(f"[Calendar] Refresh failed, will re-load token: {e}")
        _calendar_service = None
        _calendar_creds = None

    try:
        from google.auth.transport.requests import Request

        creds = _load_credentials()
        if creds is None:
            return None

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                _persist_refreshed_token(creds)
            else:
                print("[Calendar] Token invalid and cannot be refreshed. "
                      "Re-run scripts/get_token.py or update GOOGLE_TOKEN_JSON.")
                return None

        _calendar_creds = creds
        _calendar_service = build_calendar_service(creds)
        return _calendar_service
    except Exception as e:
        print(f"[Calendar] Credentials error: {e}")
        return None

