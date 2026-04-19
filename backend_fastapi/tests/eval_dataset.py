"""
Labeled evaluation dataset for orchestrator routing accuracy.

Each case maps a user utterance to the expected sub-agent tool that the
OrchestratorAgent should invoke *first* in response.  ``expected_agent``
is the tool name (e.g. "availability_agent") or ``None`` when the
orchestrator should reply directly without delegating.

``acceptable_agents`` is an optional list for ambiguous cases where
more than one routing decision is reasonable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class EvalCase:
    utterance: str
    expected_agent: Optional[str]
    category: str
    acceptable_agents: List[Optional[str]] = field(default_factory=list)


# ── Availability queries → availability_agent ────────────────────────
_AVAILABILITY = [
    EvalCase("Am I free on Friday afternoon?", "availability_agent", "availability"),
    EvalCase("What does my week look like?", "availability_agent", "availability"),
    EvalCase("Do I have anything scheduled for tomorrow?", "availability_agent", "availability"),
    EvalCase("What's on my calendar today?", "availability_agent", "availability"),
    EvalCase("Am I available at 2pm on Thursday?", "availability_agent", "availability"),
    EvalCase("Show me my schedule for next Monday", "availability_agent", "availability"),
    EvalCase("When am I free this week?", "availability_agent", "availability"),
    EvalCase("Do I have any meetings tomorrow morning?", "availability_agent", "availability"),
    EvalCase("What does my Wednesday look like?", "availability_agent", "availability"),
    EvalCase("Is my Saturday open?", "availability_agent", "availability"),
    EvalCase("How busy am I next week?", "availability_agent", "availability"),
    EvalCase("Show my upcoming events", "availability_agent", "availability"),
    EvalCase("What do I have going on this afternoon?", "availability_agent", "availability"),
    EvalCase("Are there any gaps in my schedule tomorrow?", "availability_agent", "availability"),
    EvalCase("What's the rest of my day look like?", "availability_agent", "availability"),
    EvalCase("Can you check if I have anything on Sunday?", "availability_agent", "availability"),
    EvalCase("How does next Tuesday look for me?", "availability_agent", "availability"),
    EvalCase("Do I have a free hour before lunch tomorrow?", "availability_agent", "availability"),
]

# ── New event creation (full details) → conflict_resolution_agent ────
_EVENT_CREATION = [
    EvalCase(
        "Schedule a team meeting tomorrow at 3pm for one hour",
        "conflict_resolution_agent", "event_creation",
    ),
    EvalCase(
        "Book a dentist appointment on Friday at 10am for 30 minutes",
        "conflict_resolution_agent", "event_creation",
    ),
    EvalCase(
        "Add a lunch meeting on Wednesday from 12 to 1pm",
        "conflict_resolution_agent", "event_creation",
    ),
    EvalCase(
        "Create a team standup for tomorrow at 9am, 30 minutes",
        "conflict_resolution_agent", "event_creation",
    ),
    EvalCase(
        "Put a workout session on my calendar Saturday at 7am for an hour",
        "conflict_resolution_agent", "event_creation",
    ),
    EvalCase(
        "Schedule a call with Sarah next Monday at 2pm for 45 minutes",
        "conflict_resolution_agent", "event_creation",
    ),
    EvalCase(
        "Add a doctor's appointment on Thursday at 11am for one hour",
        "conflict_resolution_agent", "event_creation",
    ),
    EvalCase(
        "Book a coffee chat on Friday at 3:30pm for 30 minutes",
        "conflict_resolution_agent", "event_creation",
    ),
    EvalCase(
        "Schedule a presentation review tomorrow at 4pm for 90 minutes",
        "conflict_resolution_agent", "event_creation",
    ),
    EvalCase(
        "Put a coding block on Monday from 9am to 12pm",
        "conflict_resolution_agent", "event_creation",
    ),
    EvalCase(
        "Add a team retrospective on Friday at 2pm for one hour",
        "conflict_resolution_agent", "event_creation",
    ),
    EvalCase(
        "Schedule a one-on-one with my manager Tuesday at 10am for 30 minutes",
        "conflict_resolution_agent", "event_creation",
    ),
    EvalCase(
        "Book a brainstorming session on Wednesday at 3pm for an hour",
        "conflict_resolution_agent", "event_creation",
    ),
    EvalCase(
        "Schedule my interview prep for Thursday at 1pm, one hour",
        "conflict_resolution_agent", "event_creation",
    ),
    EvalCase(
        "Add a yoga class on Saturday morning at 9am for one hour",
        "conflict_resolution_agent", "event_creation",
    ),
    EvalCase(
        "Put a design review on the calendar for next Wednesday 2pm to 3pm",
        "conflict_resolution_agent", "event_creation",
    ),
    EvalCase(
        "Create a focus block for tomorrow from 8am to 10am",
        "conflict_resolution_agent", "event_creation",
    ),
    EvalCase(
        "I'd like to add a piano lesson on Thursday at 5pm for 45 minutes",
        "conflict_resolution_agent", "event_creation",
    ),
]

# ── Goal / project planning → planning_agent ─────────────────────────
_PLANNING = [
    EvalCase(
        "Help me prepare for my job interview next week",
        "planning_agent", "planning",
    ),
    EvalCase(
        "I need to plan for a product launch in two weeks",
        "planning_agent", "planning",
    ),
    EvalCase(
        "Can you help me create a study plan for my AWS certification?",
        "planning_agent", "planning",
    ),
    EvalCase(
        "I want to learn Spanish over the next month, help me plan it out",
        "planning_agent", "planning",
    ),
    EvalCase(
        "Help me prepare for my presentation on Friday",
        "planning_agent", "planning",
    ),
    EvalCase(
        "I need to organize my apartment move next month",
        "planning_agent", "planning",
    ),
    EvalCase(
        "Help me create a workout routine for the next 2 weeks",
        "planning_agent", "planning",
    ),
    EvalCase(
        "I need to prepare for a marathon in 6 weeks, break it down for me",
        "planning_agent", "planning",
    ),
    EvalCase(
        "Plan my semester project — it's due in 4 weeks",
        "planning_agent", "planning",
    ),
    EvalCase(
        "Help me break down my thesis writing into manageable tasks",
        "planning_agent", "planning",
    ),
    EvalCase(
        "I need to plan a team offsite for next month",
        "planning_agent", "planning",
    ),
    EvalCase(
        "Help me come up with a plan to onboard onto my new team",
        "planning_agent", "planning",
    ),
    EvalCase(
        "I have a hackathon this weekend, help me plan my project",
        "planning_agent", "planning",
    ),
    EvalCase(
        "Break down what I need to do to launch my personal website",
        "planning_agent", "planning",
    ),
    EvalCase(
        "Help me plan my wedding preparation tasks for the next 3 months",
        "planning_agent", "planning",
    ),
]

# ── General / chitchat / vague → no tool call ────────────────────────
_GENERAL = [
    EvalCase("Hey, good morning!", None, "general"),
    EvalCase("How are you doing?", None, "general"),
    EvalCase("Thanks for the help!", None, "general"),
    EvalCase("What can you do?", None, "general"),
    EvalCase("Tell me a fun fact", None, "general"),
    EvalCase("Who built you?", None, "general"),
    EvalCase("Good night!", None, "general"),
    EvalCase("You're awesome, thanks!", None, "general"),
    EvalCase("Hello Nova!", None, "general"),
    EvalCase("That's all for today, bye!", None, "general"),
]

# ── Edge cases / ambiguous ───────────────────────────────────────────
_EDGE_CASES = [
    # Vague creation (missing details) → should ask for details, no tool
    EvalCase(
        "I need to schedule a meeting",
        None, "edge_case",
        acceptable_agents=[None],
    ),
    EvalCase(
        "Can you add something to my calendar?",
        None, "edge_case",
        acceptable_agents=[None],
    ),
    # Delete / modify → should confirm first, no tool in first turn
    EvalCase(
        "Cancel my 3pm meeting",
        None, "edge_case",
        acceptable_agents=[None, "availability_agent", "calendar_agent"],
    ),
    EvalCase(
        "Move my dentist appointment to next Thursday",
        None, "edge_case",
        acceptable_agents=[None, "availability_agent", "calendar_agent"],
    ),
    EvalCase(
        "Delete everything on Friday",
        None, "edge_case",
        acceptable_agents=[None, "availability_agent", "calendar_agent"],
    ),
    # Availability phrased like a creation request
    EvalCase(
        "Could I fit a 2 hour block somewhere this week?",
        "availability_agent", "edge_case",
        acceptable_agents=["availability_agent", "conflict_resolution_agent"],
    ),
    # Planning vs. direct scheduling
    EvalCase(
        "I have an exam in 3 days, what should I do?",
        "planning_agent", "edge_case",
        acceptable_agents=["planning_agent"],
    ),
    # Off-topic
    EvalCase(
        "What's the weather like tomorrow?",
        None, "edge_case",
        acceptable_agents=[None],
    ),
    # Creation with implicit details
    EvalCase(
        "Remind me to call Mom tomorrow at 5pm",
        "conflict_resolution_agent", "edge_case",
        acceptable_agents=["conflict_resolution_agent", "calendar_agent", None],
    ),
    # Ambiguous: checking conflicts directly
    EvalCase(
        "Will a meeting at 2pm tomorrow conflict with anything?",
        "conflict_resolution_agent", "edge_case",
        acceptable_agents=["conflict_resolution_agent", "availability_agent"],
    ),
]


EVAL_DATASET: list[EvalCase] = (
    _AVAILABILITY + _EVENT_CREATION + _PLANNING + _GENERAL + _EDGE_CASES
)

CORE_DATASET: list[EvalCase] = (
    _AVAILABILITY + _EVENT_CREATION + _PLANNING + _GENERAL
)
