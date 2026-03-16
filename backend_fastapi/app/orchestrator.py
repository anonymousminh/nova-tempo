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
from .conflict_resolution_agent import create_conflict_resolution_agent
from .planning_agent import create_planning_agent
from .scheduling_agent import create_scheduling_agent

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

| tool name                    | when to use |
|------------------------------|-------------|
| calendar_agent               | Creating, updating, or deleting calendar events — any mutating calendar action. |
| availability_agent           | Checking availability, finding free/busy periods, asking "Am I free on…?", finding open slots — any read-only schedule awareness question. |
| conflict_resolution_agent    | Proactively checking for scheduling conflicts before creating an event, and suggesting alternative times when a conflict is found. |
| planning_agent               | Breaking a high-level goal into smaller, schedulable sub-tasks with time estimates (goal decomposition). |
| scheduling_agent             | Taking a list of tasks with durations and placing them on the calendar as time-blocked events (batch scheduling). |

## Delegation rules

1. If the user asks about their **availability**, free/busy status, or when \
they have open time, call **availability_agent**.
2. **Before creating a single event**, call **conflict_resolution_agent** with \
the proposed start/end time to check for conflicts. \
   - If the agent reports no conflict, proceed to **calendar_agent** to create the event. \
   - If a conflict is detected, relay the conflicts and suggested alternative \
times to the user. Wait for the user to choose a new time or confirm they want \
to proceed despite the conflict, then call **calendar_agent**.
3. If the user wants to **modify or delete** a calendar event (or list events \
for management purposes), call **calendar_agent** directly (no conflict check needed).
4. If the user states a **high-level goal** that needs to be broken into steps \
(e.g. "prepare for my presentation", "plan a product launch"), use the \
**two-stage goal-to-calendar flow**: \
   a. Call **planning_agent** with the goal (and any deadline the user mentioned). \
   b. Present the decomposed task plan to the user for review. \
   c. Once the user approves (or adjusts), call **scheduling_agent** with the \
approved task list so it can find free slots and create the time blocks. \
   d. Relay the proposed schedule to the user. After the user confirms, the \
scheduling agent will create all the calendar events.
5. For general conversation, greetings, small-talk, or topics unrelated to the \
available agents, respond directly — do NOT delegate.
6. Relay the sub-agent's answer to the user naturally; do not parrot it verbatim.
7. If a sub-agent asks the user for confirmation (e.g. before creating events), \
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
# Helper: wrap a ConflictResolutionAgent as a @tool
# ---------------------------------------------------------------------------
def _make_conflict_resolution_agent_tool(
    get_calendar_service: Callable[[], Any],
):
    """Create a ``@tool``-wrapped ConflictResolutionAgent.

    Lazily created on first call and reused across invocations so its
    conversation memory persists within a session.
    """

    _conflict_agent: Agent | None = None

    def _get_or_create() -> Agent:
        nonlocal _conflict_agent
        if _conflict_agent is None:
            _conflict_agent = create_conflict_resolution_agent(get_calendar_service)
        return _conflict_agent

    @tool
    def conflict_resolution_agent(task: str) -> str:
        """Check whether a proposed event time conflicts with existing
        calendar events, and suggest alternatives if it does.

        Call this BEFORE creating a new event. Pass a description of the
        proposed event including start and end times.

        Args:
            task: Description of the proposed event with its time window.

        Returns:
            Whether a conflict exists, details of conflicting events,
            and suggested alternative times if applicable.
        """
        agent = _get_or_create()
        result = agent(task)
        return str(result)

    return conflict_resolution_agent


# ---------------------------------------------------------------------------
# Helper: wrap a PlanningAgent as a @tool
# ---------------------------------------------------------------------------
def _make_planning_agent_tool():
    """Create a ``@tool``-wrapped PlanningAgent.

    Lazily created on first call and reused so conversation memory
    persists within a session.  No calendar service needed — this agent
    only reasons about task decomposition.
    """

    _planning_agent: Agent | None = None

    def _get_or_create() -> Agent:
        nonlocal _planning_agent
        if _planning_agent is None:
            _planning_agent = create_planning_agent()
        return _planning_agent

    @tool
    def planning_agent(task: str) -> str:
        """Break a high-level goal into smaller, schedulable sub-tasks
        with estimated durations and priorities.

        Use this when the user describes a goal or project that needs to
        be decomposed into concrete calendar-sized work blocks.

        Args:
            task: The high-level goal or project description, including
                any deadline the user mentioned.

        Returns:
            A structured task plan with titles, durations, and priorities.
        """
        agent = _get_or_create()
        result = agent(task)
        return str(result)

    return planning_agent


# ---------------------------------------------------------------------------
# Helper: wrap a SchedulingAgent as a @tool
# ---------------------------------------------------------------------------
def _make_scheduling_agent_tool(
    get_calendar_service: Callable[[], Any],
):
    """Create a ``@tool``-wrapped SchedulingAgent.

    Lazily created on first call and reused so its pending-schedule state
    persists within a session.
    """

    _scheduling_agent: Agent | None = None

    def _get_or_create() -> Agent:
        nonlocal _scheduling_agent
        if _scheduling_agent is None:
            _scheduling_agent = create_scheduling_agent(get_calendar_service)
        return _scheduling_agent

    @tool
    def scheduling_agent(task: str) -> str:
        """Take a list of tasks with durations and schedule them as
        time-blocked events on the user's calendar.

        The agent will find free slots, propose a schedule for user
        review, and create the events after confirmation.

        Args:
            task: The list of tasks to schedule, including titles,
                durations, priorities, and any deadline constraints.

        Returns:
            The proposed or confirmed schedule details.
        """
        agent = _get_or_create()
        result = agent(task)
        return str(result)

    return scheduling_agent


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def create_orchestrator_agent(
    get_calendar_service: Callable[[], Any],
) -> Agent:
    """Create the top-level OrchestratorAgent.

    The orchestrator holds one tool per sub-agent:
    - ``calendar_agent``              — single-event CRUD
    - ``availability_agent``          — read-only schedule awareness
    - ``conflict_resolution_agent``   — pre-creation conflict checks
    - ``planning_agent``              — goal → task decomposition
    - ``scheduling_agent``            — batch time-block scheduling
    """
    cal_tool = _make_calendar_agent_tool(get_calendar_service)
    avail_tool = _make_availability_agent_tool(get_calendar_service)
    conflict_tool = _make_conflict_resolution_agent_tool(get_calendar_service)
    plan_tool = _make_planning_agent_tool()
    sched_tool = _make_scheduling_agent_tool(get_calendar_service)

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
        tools=[cal_tool, avail_tool, conflict_tool, plan_tool, sched_tool],
    )


def get_orchestrator_tools(
    get_calendar_service: Callable[[], Any],
) -> List[Any]:
    """Return orchestrator-level tools for use with BidiAgent.

    Wraps all sub-agents as ``@tool`` functions so the BidiAgent can
    delegate tasks without holding all sub-agent tools directly.
    """
    return [
        _make_calendar_agent_tool(get_calendar_service),
        _make_availability_agent_tool(get_calendar_service),
        _make_conflict_resolution_agent_tool(get_calendar_service),
        _make_planning_agent_tool(),
        _make_scheduling_agent_tool(get_calendar_service),
    ]
