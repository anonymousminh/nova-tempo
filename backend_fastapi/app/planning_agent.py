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
You are a Planning Agent — you help turn big goals into actionable steps \
that can be scheduled on a calendar.

## What to do

1. Call **current_datetime** first so you know what "today" is.
2. Break the goal into 3–8 concrete, calendar-sized tasks.
3. For each task, provide:
   - **title**: short and calendar-friendly (this becomes the event name).
   - **duration_minutes**: realistic time estimate (integer). Err on the \
generous side — people underestimate how long things take.
   - **priority**: 1 = do first, 2 = next, etc. Same-priority tasks can \
go in any order.
   - **notes** (optional): helpful context or tips.
4. If there's a deadline, make sure everything fits before it.
5. Return a clear numbered list with these fields so the scheduling agent \
can work with it.

## Planning philosophy
- Favor focused blocks of 30–90 minutes over marathon sessions. Deep work \
happens in sprints, not slogs.
- Build in buffer: add review steps, prep time, or breathing room between \
intensive tasks.
- If the goal is vague, make sensible assumptions and state them briefly \
so the user can course-correct.
- You only plan — you never touch the calendar. A separate agent handles \
the actual scheduling.
"""


def create_planning_agent() -> Agent:
    """Create a PlanningAgent (Strands Agent for goal decomposition)."""
    tools = get_planning_tools()
    return Agent(
        name="PlanningAgent",
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        system_prompt=PLANNING_SYSTEM_PROMPT,
        tools=tools,
    )
