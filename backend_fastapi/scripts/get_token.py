"""
One-time setup: run Google OAuth flow and save secrets/token.json for Calendar API.

Run (from backend_fastapi/ with venv active):
  python scripts/get_token.py

OAuth client file:
  - Put it at backend_fastapi/secrets/credentials.json, OR
  - Set GOOGLE_OAUTH_CLIENT_PATH (or legacy GOOGLE_CLIENT_CREDENTIALS) to its path.
"""

from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]
BASE_DIR = Path(__file__).resolve().parents[1]  # backend_fastapi/
SECRETS_DIR = BASE_DIR / "secrets"
DEFAULT_CLIENT_FILE = SECRETS_DIR / "credentials.json"
DEFAULT_TOKEN_FILE = SECRETS_DIR / "token.json"


def main() -> None:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)

    client_path = (
        os.environ.get("GOOGLE_OAUTH_CLIENT_PATH")
        or os.environ.get("GOOGLE_CLIENT_CREDENTIALS")
        or str(DEFAULT_CLIENT_FILE)
    )
    if not Path(client_path).exists():
        print(
            "Missing OAuth client file.\n"
            f"- Expected: {client_path}\n"
            "- Download it from Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client ID (Desktop).\n"
            f"- Then save it as: {DEFAULT_CLIENT_FILE}"
        )
        return

    creds = None
    if DEFAULT_TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(DEFAULT_TOKEN_FILE), SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        refreshed = False
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                refreshed = True
            except Exception as e:
                print(f"Token refresh failed ({e}). Starting new OAuth flow...")
        if not refreshed:
            flow = InstalledAppFlow.from_client_secrets_file(client_path, SCOPES)
            creds = flow.run_local_server(port=8085, prompt="consent")
        DEFAULT_TOKEN_FILE.write_text(creds.to_json())
        print(f"Saved: {DEFAULT_TOKEN_FILE}")
    else:
        print(f"Already have a valid token: {DEFAULT_TOKEN_FILE}")

    if not creds or not creds.refresh_token:
        print("WARNING: Token is missing refresh_token. Deleting and re-running OAuth flow...")
        DEFAULT_TOKEN_FILE.unlink(missing_ok=True)
        flow = InstalledAppFlow.from_client_secrets_file(client_path, SCOPES)
        creds = flow.run_local_server(port=8085, prompt="consent")
        DEFAULT_TOKEN_FILE.write_text(creds.to_json())
        print(f"Saved: {DEFAULT_TOKEN_FILE}")

    print("Calendar auth is ready.")


if __name__ == "__main__":
    main()

