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
from .availability_agent import create_availability_agent

# ---------------------------------------------------------------------------
# Orchestrator system prompt
# ---------------------------------------------------------------------------
ORCHESTRATOR_SYSTEM_PROMPT = """\
You are Nova Tempo, a friendly and helpful AI assistant.

You coordinate specialized agents to fulfil the user's requests.
You have persistent memory across sessions. Use any remembered user preferences \
or facts to personalize your responses. When the user shares preferences \
(e.g. favorite color, dietary choices, scheduling habits), acknowledge them \
naturally — they will be remembered for future conversations.

## Available agents

| tool name            | when to use |
|----------------------|-------------|
| calendar_agent       | Creating, updating, or deleting calendar events — any mutating calendar action. |
| availability_agent   | Checking availability, finding free/busy periods, asking "Am I free on…?", finding open slots — any read-only schedule awareness question. |

## Delegation rules

1. If the user asks about their **availability**, free/busy status, schedule \
conflicts, or when they have open time, call **availability_agent**.
2. If the user wants to **create, modify, or delete** a calendar event (or list \
events for management purposes), call **calendar_agent**.
3. For general conversation, greetings, small-talk, or topics unrelated to the \
available agents, respond directly — do NOT delegate.
4. Relay the sub-agent's answer to the user naturally; do not parrot it verbatim.
5. If the sub-agent asks the user for confirmation (e.g. before creating an event), \
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
# Helper: wrap an AvailabilityAgent as a @tool
# ---------------------------------------------------------------------------
def _make_availability_agent_tool(
    get_calendar_service: Callable[[], Any],
):
    """Create a ``@tool``-wrapped AvailabilityAgent.

    Lazily created on first call and reused across invocations so its
    conversation memory persists within a session.
    """

    _availability_agent: Agent | None = None

    def _get_or_create() -> Agent:
        nonlocal _availability_agent
        if _availability_agent is None:
            _availability_agent = create_availability_agent(get_calendar_service)
        return _availability_agent

    @tool
    def availability_agent(task: str) -> str:
        """Delegate an availability or schedule-awareness question to the
        Availability Agent.

        Use this for any request about the user's free/busy status,
        schedule conflicts, open time windows, or general availability
        queries. This agent is read-only and will never create or delete events.

        Args:
            task: The availability-related request or question to handle.

        Returns:
            The Availability Agent's response.
        """
        agent = _get_or_create()
        result = agent(task)
        return str(result)

    return availability_agent


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def create_orchestrator_agent(
    get_calendar_service: Callable[[], Any],
) -> Agent:
    """Create the top-level OrchestratorAgent.

    The orchestrator holds one tool per sub-agent. When the LLM decides a
    user request is calendar-related it calls ``calendar_agent``; for
    availability questions it calls ``availability_agent``; for everything
    else it responds directly.
    """
    cal_tool = _make_calendar_agent_tool(get_calendar_service)
    avail_tool = _make_availability_agent_tool(get_calendar_service)

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
        tools=[cal_tool, avail_tool],
    )


def get_orchestrator_tools(
    get_calendar_service: Callable[[], Any],
) -> List[Any]:
    """Return orchestrator-level tools for use with BidiAgent.

    Wraps the CalendarAgent and AvailabilityAgent as ``@tool`` functions
    so the BidiAgent can delegate tasks without holding all sub-agent
    tools directly.
    """
    return [
        _make_calendar_agent_tool(get_calendar_service),
        _make_availability_agent_tool(get_calendar_service),
    ]
