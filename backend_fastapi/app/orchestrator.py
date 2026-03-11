"""
Multi-agent orchestrator for Nova Tempo.

Uses the "Agents as Tools" pattern from Strands Agents: the OrchestratorAgent
delegates domain-specific tasks to specialized sub-agents (currently CalendarAgent).
Adding a new domain is as simple as creating a sub-agent, wrapping it with @tool,
and appending it to the orchestrator's tools list.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, List

from strands import Agent, tool

from .strands_agent import create_calendar_agent

# ---------------------------------------------------------------------------
# Orchestrator system prompt
# ---------------------------------------------------------------------------
ORCHESTRATOR_SYSTEM_PROMPT = """\
You are Nova Tempo, a friendly and helpful AI assistant.

You coordinate specialized agents to fulfil the user's requests.

## Available agents

| tool name        | when to use |
|------------------|-------------|
| calendar_agent   | Schedule queries, listing events, creating/modifying events, finding free slots — anything Google Calendar. |

## Delegation rules

1. If the request is calendar-related, call **calendar_agent** with the user's request.
2. For general conversation, greetings, small-talk, or topics unrelated to the \
available agents, respond directly — do NOT delegate.
3. Relay the sub-agent's answer to the user naturally; do not parrot it verbatim.
4. If the sub-agent asks the user for confirmation (e.g. before creating an event), \
pass that question to the user, then forward the user's reply back to the sub-agent.
"""


# ---------------------------------------------------------------------------
# Helper: wrap a CalendarAgent as a @tool (Agents as Tools pattern)
# ---------------------------------------------------------------------------
def _make_calendar_agent_tool(
    get_calendar_service: Callable[[], Any],
):
    """Create a ``@tool``-wrapped CalendarAgent.

    The CalendarAgent is created lazily on first call and reused across
    invocations so that its conversation memory and pending-action state
    (the two-phase confirmation flow) persist within a session.
    """

    _calendar_agent: Agent | None = None

    def _get_or_create() -> Agent:
        nonlocal _calendar_agent
        if _calendar_agent is None:
            _calendar_agent = create_calendar_agent(get_calendar_service)
        return _calendar_agent

    @tool
    def calendar_agent(task: str) -> str:
        """Delegate a calendar-related task to the Calendar Agent.

        Use this for any request about the user's schedule, events,
        availability, or creating / modifying / cancelling calendar entries.

        Args:
            task: The calendar-related request or question to handle.

        Returns:
            The Calendar Agent's response.
        """
        agent = _get_or_create()
        result = agent(task)
        return str(result)

    return calendar_agent


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def create_orchestrator_agent(
    get_calendar_service: Callable[[], Any],
) -> Agent:
    """Create the top-level OrchestratorAgent.

    The orchestrator holds one tool per sub-agent. When the LLM decides a
    user request is calendar-related it calls ``calendar_agent``; for
    everything else it responds directly.
    """
    cal_tool = _make_calendar_agent_tool(get_calendar_service)

    now = datetime.now().astimezone()
    today_str = now.strftime("%A %B %-d, %Y, %-I:%M %p")
    date_context = (
        f"\nThe current date and time is {today_str}. "
        f'When the user says "today" they mean {now.strftime("%Y-%m-%d")}, '
        f'"tomorrow" means {(now + timedelta(days=1)).strftime("%Y-%m-%d")}.'
    )

    return Agent(
        name="OrchestratorAgent",
        system_prompt=ORCHESTRATOR_SYSTEM_PROMPT + date_context,
        tools=[cal_tool],
    )


def get_orchestrator_tools(
    get_calendar_service: Callable[[], Any],
) -> List[Any]:
    """Return orchestrator-level tools for use with BidiAgent.

    Wraps the CalendarAgent as a single ``@tool`` so the BidiAgent can
    delegate calendar tasks without holding all calendar tools directly.
    """
    return [_make_calendar_agent_tool(get_calendar_service)]
