"""
PlanningAgent — specialized sub-agent for goal decomposition.

Takes a high-level goal (e.g. "Prepare for my presentation next week")
and breaks it into smaller, schedulable tasks with estimated durations,
priority ordering, and optional dependency hints.

This agent is purely a reasoning agent — it has no calendar write access.
It returns a structured task plan that the SchedulingAgent can then place
on the calendar as time blocks.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, List

from strands import Agent, tool


def get_planning_tools() -> List[Any]:
    """Return tools for the PlanningAgent."""

    @tool
    def current_datetime() -> str:
        """Get the current date and time in the user's local timezone.

        Use this so you know the user's 'today' and can reason about
        deadlines relative to now.
        """
        now = datetime.now().astimezone()
        return now.strftime("%A %B %-d, %Y at %-I:%M %p")

    return [current_datetime]


PLANNING_SYSTEM_PROMPT = """\
You are a specialized Planning Agent. Your job is to take a high-level \
goal from the user and decompose it into concrete, schedulable sub-tasks.

## Instructions

1. Always call **current_datetime** first so you know what "today" is.
2. Analyze the goal and break it into 3–8 actionable sub-tasks.
3. For each sub-task provide:
   - **title**: a short, calendar-friendly name (will become the event title).
   - **duration_minutes**: estimated time needed (integer).
   - **priority**: 1 = must do first, 2 = next, etc. Tasks with the same \
priority can be scheduled in any order.
   - **notes** (optional): brief context or tips for the task.
4. If the user mentioned a deadline, ensure the tasks can realistically fit \
before that date.
5. Return your plan as a numbered list with the fields above clearly stated \
for each task so the scheduling agent can parse them.

## Guidelines
- Be realistic with time estimates — prefer slightly generous durations.
- Prefer shorter focused blocks (30–90 min) over marathon sessions.
- Include buffer/review tasks when appropriate (e.g. "Review and polish slides").
- If the goal is vague, make reasonable assumptions and state them.
- You do NOT schedule anything — just produce the plan. Scheduling is \
handled by a separate agent.
"""


def create_planning_agent() -> Agent:
    """Create a PlanningAgent (Strands Agent for goal decomposition)."""
    tools = get_planning_tools()
    return Agent(
        name="PlanningAgent",
        system_prompt=PLANNING_SYSTEM_PROMPT,
        tools=tools,
    )
