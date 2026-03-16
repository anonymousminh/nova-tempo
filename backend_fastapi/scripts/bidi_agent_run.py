"""
Run BidiAgent with Nova Sonic using the multi-agent orchestrator.

The BidiAgent acts as the voice interface.  Instead of holding all calendar
tools directly it delegates via a single ``calendar_agent`` tool that wraps
the CalendarAgent (Agents as Tools pattern).

Usage (from backend_fastapi/ with venv active):
  pip install -r requirements.txt   # includes strands-agents[bidi-all]
  python scripts/bidi_agent_run.py

Requires: AWS credentials for Nova Sonic (us-east-1).
Optional: GOOGLE_CREDENTIALS_PATH or secrets/token.json for calendar tools.
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strands.experimental.bidi import BidiAgent
from strands.experimental.bidi.io import BidiAudioIO, BidiTextIO
from strands.experimental.bidi.models import BidiNovaSonicModel
from strands.experimental.bidi.tools import stop_conversation

from app.calendar_auth import get_calendar_service
from app.orchestrator import get_orchestrator_tools, ORCHESTRATOR_SYSTEM_PROMPT


async def main() -> None:
    model = BidiNovaSonicModel(
        model_id="amazon.nova-sonic-v1:0",
        provider_config={"audio": {"voice": "tiffany"}},
        client_config={"region": "us-east-1"},
    )
    now = datetime.now().astimezone()
    today_str = now.strftime("%A %B %-d, %Y, %-I:%M %p")

    svc = get_calendar_service()
    if svc is None:
        print("[WARN] Calendar service not available — tools will return errors.")
        print("       Run: python scripts/get_token.py")
    else:
        print("[OK] Calendar service connected.")

    orchestrator_tools = get_orchestrator_tools(get_calendar_service)

    date_context = (
        f"\n## Current date and time\n"
        f"Right now it is **{today_str}**. The current year is **{now.year}**.\n"
        f'When the user says "today" they mean {now.strftime("%Y-%m-%d")}, '
        f'"tomorrow" means {(now + timedelta(days=1)).strftime("%Y-%m-%d")}.\n'
        f"IMPORTANT: Always use the year {now.year} when creating events. "
        f"Never use a past year."
    )
    agent = BidiAgent(
        model=model,
        system_prompt=ORCHESTRATOR_SYSTEM_PROMPT + date_context,
        tools=[*orchestrator_tools, stop_conversation],
    )

    audio_io = BidiAudioIO()
    text_io = BidiTextIO()
    await agent.run(
        inputs=[audio_io.input()],
        outputs=[audio_io.output(), text_io.output()],
    )


if __name__ == "__main__":
    asyncio.run(main())

