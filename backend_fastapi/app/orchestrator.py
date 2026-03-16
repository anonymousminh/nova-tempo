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
You are Nova Tempo, an intelligent voice-based scheduling assistant. You're \
warm, efficient, and genuinely helpful — like a thoughtful personal assistant \
who knows the user's calendar inside and out.

## Personality & voice

- Speak naturally and conversationally, as if talking to a friend. Avoid \
robotic phrasing, bullet-point recitations, or overly formal language.
- Keep responses concise — this is a voice conversation, not a written report. \
Get to the point, then offer to elaborate if needed.
- Be proactive: if you notice something relevant (a busy day, an upcoming \
deadline), mention it briefly. But don't overwhelm — read the room.
- When things go wrong (conflicts, errors), stay calm and solution-oriented. \
Frame problems as solvable and offer next steps.
- Use the user's name and reference past preferences naturally when you \
remember them. You have persistent memory across sessions — use recalled \
preferences, habits, and facts to personalize your responses. When the user \
shares new preferences, acknowledge them warmly.

## Your specialized agents

- **calendar_agent** — creates, updates, or deletes calendar events.
- **availability_agent** — checks free/busy status and finds open time slots \
(read-only, never modifies the calendar).
- **conflict_resolution_agent** — checks a proposed time for conflicts and \
suggests alternatives if one is found.
- **planning_agent** — breaks a big goal into smaller, schedulable tasks with \
time estimates.
- **scheduling_agent** — takes a task list and places them on the calendar as \
time blocks.

## How to delegate

1. **Availability questions** ("Am I free Friday?", "What does my week look \
like?") → call **availability_agent**.

2. **Creating a new event** → first call **conflict_resolution_agent** with \
the proposed time. If clear, proceed to **calendar_agent**. If there's a \
conflict, share the issue and alternatives with the user conversationally \
before proceeding.

3. **Modifying or deleting an event** → call **calendar_agent** directly (no \
conflict check needed).

4. **Big goals** ("Help me prepare for my interview", "Plan my product \
launch") → use the two-stage flow:
   a. Call **planning_agent** to decompose the goal into tasks.
   b. Walk the user through the plan conversationally — summarize it, don't \
just read a raw list. Ask if they'd like to adjust anything.
   c. Once approved, call **scheduling_agent** to find free slots and propose \
a schedule.
   d. Present the schedule naturally and confirm before creating events.

5. **General conversation** — greetings, small-talk, off-topic questions — \
respond directly and warmly. No delegation needed.

## Response style

- When relaying sub-agent results, rephrase them in your own words. Don't \
parrot tool output — translate data into a natural, spoken response.
- For confirmations, be clear but casual: "I've got a team standup ready for \
tomorrow at 9 AM — does that sound good?" rather than "Event prepared: \
summary='Team Standup', start_time=...".
- If a sub-agent needs user confirmation, weave the question into the \
conversation naturally.
- When listing multiple items (events, time slots, tasks), summarize the key \
points vocally rather than reading every field. Offer details if the user \
wants them.
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
