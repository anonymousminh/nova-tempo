"""
Evaluation dataset for task completion / success rate testing.

Each scenario defines a multi-turn conversation and the expected outcome:
which Google Calendar API calls should be made, or which sub-agents invoked.

Categories:
    - create_event        Event creation (2 turns: request + confirm)
    - check_availability  Schedule / availability queries (1 turn)
    - find_free_time      Finding open time slots (1 turn)
    - check_conflicts     Conflict checks for proposed times (1 turn)
    - delete_event        Event deletion (2 turns: request + confirm)
    - planning            Goal decomposition into tasks (1 turn)
    - general             Greetings, off-topic, no-op (1 turn)
    - edge_case           Ambiguous / tricky requests (mixed)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class TaskScenario:
    """A single task-completion evaluation scenario.

    Attributes:
        name: Unique identifier.
        category: Grouping key for reporting.
        turns: User messages sent in sequence to the same agent.
        expected_api_calls: At least one of these Google Calendar API methods
            must appear in the recorded calls for the scenario to pass.
            Empty list means *no* API calls are expected.
        expected_agents: At least one of these sub-agent tools must be invoked.
            Empty list means no specific agent is required.
        forbid_writes: If True, no ``events.insert`` or ``events.delete``
            should occur (used for read-only / no-op scenarios).
        description: Human-readable explanation of what is being tested.
    """

    name: str
    category: str
    turns: List[str]
    expected_api_calls: List[str] = field(default_factory=list)
    expected_agents: List[str] = field(default_factory=list)
    forbid_writes: bool = False
    description: str = ""


# ── Event creation (2 turns: request + confirm) ─────────────────────

_CREATE_EVENT = [
    TaskScenario(
        "create_team_meeting",
        "create_event",
        ["Schedule a team meeting tomorrow at 3pm for one hour", "Yes, go ahead"],
        expected_api_calls=["events.insert"],
        description="Standard meeting with all details provided",
    ),
    TaskScenario(
        "create_dentist_appt",
        "create_event",
        ["Book a dentist appointment on Friday at 10am for 30 minutes", "Yes please"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_lunch",
        "create_event",
        ["Add a lunch meeting on Wednesday from 12 to 1pm", "Sure, do it"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_standup",
        "create_event",
        ["Create a team standup for tomorrow at 9am, 30 minutes", "Yes"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_workout",
        "create_event",
        ["Put a workout session on my calendar Saturday at 7am for an hour", "Yep, add it"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_call_sarah",
        "create_event",
        ["Schedule a call with Sarah next Monday at 2pm for 45 minutes", "Yes, go ahead"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_doctor",
        "create_event",
        ["Add a doctor's appointment on Thursday at 11am for one hour", "Yes please"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_coffee_chat",
        "create_event",
        ["Book a coffee chat on Friday at 3:30pm for 30 minutes", "Sure"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_presentation_review",
        "create_event",
        ["Schedule a presentation review tomorrow at 4pm for 90 minutes", "Yes, add it"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_coding_block",
        "create_event",
        ["Put a coding block on Monday from 9am to 12pm", "Go ahead"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_retro",
        "create_event",
        ["Add a team retrospective on Friday at 2pm for one hour", "Yes"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_one_on_one",
        "create_event",
        [
            "Schedule a one-on-one with my manager Tuesday at 10am for 30 minutes",
            "Yes, book it",
        ],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_brainstorm",
        "create_event",
        ["Book a brainstorming session on Wednesday at 3pm for an hour", "Do it"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_interview_prep",
        "create_event",
        ["Schedule my interview prep for Thursday at 1pm, one hour", "Yes please"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_yoga",
        "create_event",
        ["Add a yoga class on Saturday morning at 9am for one hour", "Yes, add it"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_design_review",
        "create_event",
        [
            "Put a design review on the calendar for next Wednesday 2pm to 3pm",
            "Sounds good, go ahead",
        ],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_focus_block",
        "create_event",
        ["Create a focus block for tomorrow from 8am to 10am", "Yes"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_piano_lesson",
        "create_event",
        [
            "I'd like to add a piano lesson on Thursday at 5pm for 45 minutes",
            "Yes, schedule it",
        ],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_dinner",
        "create_event",
        ["Schedule dinner with Alex on Friday at 7pm for two hours", "Yes please"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_sprint_planning",
        "create_event",
        ["Add sprint planning on Monday at 10am for 90 minutes", "Go ahead and book it"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_movie_night",
        "create_event",
        ["Put a movie night on Saturday at 8pm for three hours", "Yes"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_gym",
        "create_event",
        ["Book gym time on Tuesday and Thursday at 6am for one hour", "Yes, add it"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_client_meeting",
        "create_event",
        [
            "Schedule a client meeting next Tuesday at 1pm for an hour",
            "Yes, put it on my calendar",
        ],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_study_session",
        "create_event",
        ["Add a study session tomorrow from 6pm to 8pm", "Yep"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_haircut",
        "create_event",
        ["Book a haircut appointment for next Saturday at 11am, 45 minutes", "Yes"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_standup_friday",
        "create_event",
        ["Create a standup on Friday at 9:15am for 15 minutes", "Sure, go ahead"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_reading_block",
        "create_event",
        ["Schedule a reading block on Sunday from 10am to 12pm", "Yes please"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_therapy",
        "create_event",
        ["Add a therapy session on Wednesday at 4pm for 50 minutes", "Yes, add it"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_team_lunch",
        "create_event",
        ["Put a team lunch on the calendar for Friday 12:30 to 1:30pm", "Do it"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_all_hands",
        "create_event",
        ["Schedule an all-hands meeting for next Monday at 2pm for one hour", "Yes"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_demo",
        "create_event",
        ["I need to add a product demo on Thursday at 11am for 30 minutes", "Yes, go ahead"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_walk",
        "create_event",
        ["Put a lunch walk on my calendar tomorrow at 12:15pm for 30 minutes", "Sure"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_mentoring",
        "create_event",
        [
            "Schedule a mentoring session with Jake next Wednesday at 3pm for one hour",
            "Yes, book it",
        ],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_deep_work",
        "create_event",
        ["Block out Tuesday morning from 8am to 11am for deep work", "Yes"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_vet",
        "create_event",
        ["Book a vet appointment next Friday at 2pm for one hour", "Go ahead"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_board_games",
        "create_event",
        ["Add a board game night on Saturday at 7pm for three hours", "Yes, add it"],
        expected_api_calls=["events.insert"],
    ),
    TaskScenario(
        "create_standup_mon",
        "create_event",
        ["Put a daily standup on Monday at 9am for 15 minutes", "Yes"],
        expected_api_calls=["events.insert"],
    ),
]

# ── Availability / schedule checks (1 turn) ─────────────────────────

_CHECK_AVAILABILITY = [
    TaskScenario(
        "avail_today",
        "check_availability",
        ["What's on my calendar today?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_tomorrow",
        "check_availability",
        ["Do I have anything scheduled for tomorrow?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_week",
        "check_availability",
        ["What does my week look like?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_friday_afternoon",
        "check_availability",
        ["Am I free on Friday afternoon?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_thursday_2pm",
        "check_availability",
        ["Am I available at 2pm on Thursday?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_next_monday",
        "check_availability",
        ["Show me my schedule for next Monday"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_free_this_week",
        "check_availability",
        ["When am I free this week?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_tomorrow_morning",
        "check_availability",
        ["Do I have any meetings tomorrow morning?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_wednesday",
        "check_availability",
        ["What does my Wednesday look like?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_saturday",
        "check_availability",
        ["Is my Saturday open?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_busy_next_week",
        "check_availability",
        ["How busy am I next week?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_upcoming",
        "check_availability",
        ["Show my upcoming events"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_this_afternoon",
        "check_availability",
        ["What do I have going on this afternoon?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_gaps_tomorrow",
        "check_availability",
        ["Are there any gaps in my schedule tomorrow?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_rest_of_day",
        "check_availability",
        ["What's the rest of my day look like?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_sunday",
        "check_availability",
        ["Can you check if I have anything on Sunday?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_next_tuesday",
        "check_availability",
        ["How does next Tuesday look for me?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_before_lunch",
        "check_availability",
        ["Do I have a free hour before lunch tomorrow?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_tonight",
        "check_availability",
        ["Am I free tonight after 6pm?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_early_morning",
        "check_availability",
        ["What's happening on my calendar first thing tomorrow?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_this_weekend",
        "check_availability",
        ["Do I have plans this weekend?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_end_of_week",
        "check_availability",
        ["What does the end of this week look like?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_double_booked",
        "check_availability",
        ["Am I double-booked anywhere this week?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_meetings_count",
        "check_availability",
        ["How many meetings do I have tomorrow?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_next_event",
        "check_availability",
        ["What's my next event?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_morning_slot",
        "check_availability",
        ["Is there anything on my calendar between 8am and noon tomorrow?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_friday",
        "check_availability",
        ["Walk me through my Friday schedule"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_packed_day",
        "check_availability",
        ["Is tomorrow going to be a packed day?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_late_afternoon",
        "check_availability",
        ["Is anything happening between 4pm and 6pm tomorrow?"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "avail_three_day",
        "check_availability",
        ["Give me an overview of the next three days"],
        expected_api_calls=["events.list", "freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
]

# ── Find free time (1 turn) ─────────────────────────────────────────

_FIND_FREE_TIME = [
    TaskScenario(
        "free_hour_this_week",
        "find_free_time",
        ["Can you find me a free hour this week?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "free_2hr_block",
        "find_free_time",
        ["I need a 2-hour block somewhere this week, when works?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "free_30min_tomorrow",
        "find_free_time",
        ["Find me a free 30 minutes tomorrow afternoon"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "free_slot_for_meeting",
        "find_free_time",
        ["When could I fit in a 45-minute meeting this week?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "free_morning_slot",
        "find_free_time",
        ["Any free morning slots this week?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "free_next_available",
        "find_free_time",
        ["When is my next free hour?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "free_half_day",
        "find_free_time",
        ["Is there a half-day block free anywhere this week?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "free_afternoon",
        "find_free_time",
        ["Do I have a free afternoon this week?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "free_15min_today",
        "find_free_time",
        ["Can you find 15 minutes free today?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "free_lunch_slot",
        "find_free_time",
        ["Is there a free slot around lunchtime tomorrow?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "free_90min",
        "find_free_time",
        ["I need 90 minutes of uninterrupted time — when's the earliest?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "free_early_morning",
        "find_free_time",
        ["Any free slots before 9am this week?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "free_3hr_block",
        "find_free_time",
        ["Find me a 3-hour window sometime next week"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "free_evening",
        "find_free_time",
        ["When am I free in the evenings this week?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "free_quick_break",
        "find_free_time",
        ["I need a quick 20-minute break today — where can I squeeze it in?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["availability_agent"],
        forbid_writes=True,
    ),
]

# ── Conflict checks (1 turn) ────────────────────────────────────────

_CHECK_CONFLICTS = [
    TaskScenario(
        "conflict_2pm_tomorrow",
        "check_conflicts",
        ["Will a meeting at 2pm tomorrow conflict with anything?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["conflict_resolution_agent", "availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "conflict_morning",
        "check_conflicts",
        ["Would 9am on Wednesday work or does it conflict?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["conflict_resolution_agent", "availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "conflict_friday_3pm",
        "check_conflicts",
        ["Check if 3pm on Friday is open for a meeting"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["conflict_resolution_agent", "availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "conflict_lunch_slot",
        "check_conflicts",
        ["Is 12pm to 1pm tomorrow going to conflict with anything?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["conflict_resolution_agent", "availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "conflict_back_to_back",
        "check_conflicts",
        ["If I put something at 4pm on Thursday, will that clash with anything?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["conflict_resolution_agent", "availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "conflict_overlap",
        "check_conflicts",
        ["Can I add a 2-hour event starting at 10am Monday without any overlap?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["conflict_resolution_agent", "availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "conflict_early",
        "check_conflicts",
        ["Does 7:30am tomorrow morning have any conflicts?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["conflict_resolution_agent", "availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "conflict_evening",
        "check_conflicts",
        ["Is 6pm on Friday evening free, or do I have something?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["conflict_resolution_agent", "availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "conflict_weekend",
        "check_conflicts",
        ["Any conflicts if I schedule something Saturday at 10am?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["conflict_resolution_agent", "availability_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "conflict_tight_window",
        "check_conflicts",
        ["I want to fit a 30-minute call at 1:30pm tomorrow — any issues?"],
        expected_api_calls=["freebusy.query"],
        expected_agents=["conflict_resolution_agent", "availability_agent"],
        forbid_writes=True,
    ),
]

# ── Event deletion (2 turns: request + confirm) ─────────────────────

_DELETE_EVENT = [
    TaskScenario(
        "delete_standup",
        "delete_event",
        ["Cancel my Team Standup", "Yes, remove it"],
        expected_api_calls=["events.delete"],
        expected_agents=["calendar_agent"],
    ),
    TaskScenario(
        "delete_lunch",
        "delete_event",
        ["Remove the Lunch with Sarah from my calendar", "Yes"],
        expected_api_calls=["events.delete"],
        expected_agents=["calendar_agent"],
    ),
    TaskScenario(
        "delete_code_review",
        "delete_event",
        ["Delete my Code Review", "Go ahead"],
        expected_api_calls=["events.delete"],
        expected_agents=["calendar_agent"],
    ),
    TaskScenario(
        "delete_product_meeting",
        "delete_event",
        ["Cancel the Product Meeting", "Yes, cancel it"],
        expected_api_calls=["events.delete"],
        expected_agents=["calendar_agent"],
    ),
    TaskScenario(
        "delete_dentist",
        "delete_event",
        ["Remove my Dentist Appointment", "Yes please"],
        expected_api_calls=["events.delete"],
        expected_agents=["calendar_agent"],
    ),
    TaskScenario(
        "delete_need_to_cancel",
        "delete_event",
        ["I need to cancel the Team Standup tomorrow", "Yes, do it"],
        expected_api_calls=["events.delete"],
        expected_agents=["calendar_agent"],
    ),
    TaskScenario(
        "delete_something_came_up",
        "delete_event",
        ["Something came up, please remove my Code Review", "Yep"],
        expected_api_calls=["events.delete"],
        expected_agents=["calendar_agent"],
    ),
    TaskScenario(
        "delete_cant_make_it",
        "delete_event",
        ["I can't make the Lunch with Sarah anymore, take it off", "Yes"],
        expected_api_calls=["events.delete"],
        expected_agents=["calendar_agent"],
    ),
    TaskScenario(
        "delete_clear_afternoon",
        "delete_event",
        ["Get rid of my Code Review this afternoon", "Sure, remove it"],
        expected_api_calls=["events.delete"],
        expected_agents=["calendar_agent"],
    ),
    TaskScenario(
        "delete_no_longer_needed",
        "delete_event",
        [
            "The Product Meeting tomorrow is no longer needed, please cancel it",
            "Yes",
        ],
        expected_api_calls=["events.delete"],
        expected_agents=["calendar_agent"],
    ),
    TaskScenario(
        "delete_drop",
        "delete_event",
        ["Drop the Team Standup from my schedule", "Go ahead and remove it"],
        expected_api_calls=["events.delete"],
        expected_agents=["calendar_agent"],
    ),
    TaskScenario(
        "delete_unschedule",
        "delete_event",
        ["Can you unschedule the Dentist Appointment?", "Yes"],
        expected_api_calls=["events.delete"],
        expected_agents=["calendar_agent"],
    ),
]

# ── Planning (1 turn — only agent routing checked) ──────────────────

_PLANNING = [
    TaskScenario(
        "plan_interview",
        "planning",
        ["Help me prepare for my job interview next week"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_product_launch",
        "planning",
        ["I need to plan for a product launch in two weeks"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_aws_cert",
        "planning",
        ["Can you help me create a study plan for my AWS certification?"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_learn_spanish",
        "planning",
        ["I want to learn Spanish over the next month, help me plan it out"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_presentation",
        "planning",
        ["Help me prepare for my presentation on Friday"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_apartment_move",
        "planning",
        ["I need to organize my apartment move next month"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_workout_routine",
        "planning",
        ["Help me create a workout routine for the next 2 weeks"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_marathon",
        "planning",
        ["I need to prepare for a marathon in 6 weeks, break it down for me"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_semester_project",
        "planning",
        ["Plan my semester project — it's due in 4 weeks"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_thesis",
        "planning",
        ["Help me break down my thesis writing into manageable tasks"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_offsite",
        "planning",
        ["I need to plan a team offsite for next month"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_onboarding",
        "planning",
        ["Help me come up with a plan to onboard onto my new team"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_hackathon",
        "planning",
        ["I have a hackathon this weekend, help me plan my project"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_website",
        "planning",
        ["Break down what I need to do to launch my personal website"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_wedding",
        "planning",
        ["Help me plan my wedding preparation tasks for the next 3 months"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_garden",
        "planning",
        ["I want to start a vegetable garden — help me plan the steps over 4 weeks"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_book",
        "planning",
        ["Help me plan writing a book over the next 3 months"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_migration",
        "planning",
        ["We have a database migration coming up — break it into phases"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_fundraiser",
        "planning",
        ["I'm organizing a charity fundraiser in 3 weeks, help me plan everything"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
    TaskScenario(
        "plan_home_renovation",
        "planning",
        ["Help me plan a bathroom renovation — what are the steps?"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
    ),
]

# ── General / no-op (1 turn) ────────────────────────────────────────

_GENERAL = [
    TaskScenario(
        "general_morning",
        "general",
        ["Hey, good morning!"],
        forbid_writes=True,
        description="Greeting — no calendar operation expected",
    ),
    TaskScenario(
        "general_how_are_you",
        "general",
        ["How are you doing?"],
        forbid_writes=True,
    ),
    TaskScenario(
        "general_thanks",
        "general",
        ["Thanks for the help!"],
        forbid_writes=True,
    ),
    TaskScenario(
        "general_capabilities",
        "general",
        ["What can you do?"],
        forbid_writes=True,
    ),
    TaskScenario(
        "general_fun_fact",
        "general",
        ["Tell me a fun fact"],
        forbid_writes=True,
    ),
    TaskScenario(
        "general_who_built",
        "general",
        ["Who built you?"],
        forbid_writes=True,
    ),
    TaskScenario(
        "general_goodnight",
        "general",
        ["Good night!"],
        forbid_writes=True,
    ),
    TaskScenario(
        "general_awesome",
        "general",
        ["You're awesome, thanks!"],
        forbid_writes=True,
    ),
    TaskScenario(
        "general_hello",
        "general",
        ["Hello Nova!"],
        forbid_writes=True,
    ),
    TaskScenario(
        "general_bye",
        "general",
        ["That's all for today, bye!"],
        forbid_writes=True,
    ),
    TaskScenario(
        "general_joke",
        "general",
        ["Tell me a joke"],
        forbid_writes=True,
    ),
    TaskScenario(
        "general_weather",
        "general",
        ["What's the weather like tomorrow?"],
        forbid_writes=True,
    ),
    TaskScenario(
        "general_name",
        "general",
        ["What's your name?"],
        forbid_writes=True,
    ),
    TaskScenario(
        "general_how_help",
        "general",
        ["How can you help me?"],
        forbid_writes=True,
    ),
    TaskScenario(
        "general_feeling",
        "general",
        ["I'm having a great day!"],
        forbid_writes=True,
    ),
]

# ── Edge cases / ambiguous ───────────────────────────────────────────

_EDGE_CASES = [
    TaskScenario(
        "edge_vague_schedule",
        "edge_case",
        ["I need to schedule a meeting"],
        forbid_writes=True,
        description="Missing details — should ask for clarification, not create",
    ),
    TaskScenario(
        "edge_vague_add",
        "edge_case",
        ["Can you add something to my calendar?"],
        forbid_writes=True,
        description="No event details — should ask what to add",
    ),
    TaskScenario(
        "edge_vague_reminder",
        "edge_case",
        ["Remind me about something tomorrow"],
        forbid_writes=True,
        description="No specifics — should ask for details",
    ),
    TaskScenario(
        "edge_availability_like_creation",
        "edge_case",
        ["Could I fit a 2-hour block somewhere this week?"],
        expected_api_calls=["freebusy.query"],
        forbid_writes=True,
        description="Sounds like creation but is really availability",
    ),
    TaskScenario(
        "edge_exam_planning",
        "edge_case",
        ["I have an exam in 3 days, what should I do?"],
        expected_agents=["planning_agent"],
        forbid_writes=True,
        description="Implicit planning request",
    ),
    TaskScenario(
        "edge_mixed_request",
        "edge_case",
        ["Check my schedule tomorrow and also help me plan for my interview"],
        expected_agents=["availability_agent", "planning_agent"],
        forbid_writes=True,
        description="Two tasks in one — should handle at least one",
    ),
    TaskScenario(
        "edge_past_event",
        "edge_case",
        ["What happened in my meeting yesterday?"],
        forbid_writes=True,
        description="Past event query — may try availability or respond directly",
    ),
    TaskScenario(
        "edge_nonstandard_time",
        "edge_case",
        [
            "Schedule a meeting for the day after tomorrow at half past two for an hour",
            "Yes",
        ],
        expected_api_calls=["events.insert"],
        description="Non-standard time phrasing",
    ),
    TaskScenario(
        "edge_implicit_duration",
        "edge_case",
        ["Put a quick sync on my calendar tomorrow at 10am", "Yes, add it"],
        expected_api_calls=["events.insert", "freebusy.query"],
        description="No explicit duration — agent should assume or ask",
    ),
    TaskScenario(
        "edge_relative_day",
        "edge_case",
        ["Schedule a workout the morning after next", "Yes"],
        expected_api_calls=["events.insert", "freebusy.query"],
        description="Relative day reference",
    ),
    TaskScenario(
        "edge_create_then_cancel",
        "edge_case",
        [
            "Schedule a meeting tomorrow at 4pm for one hour",
            "Actually, never mind, don't add it",
        ],
        forbid_writes=True,
        description="User cancels after the proposal — no event should be created",
    ),
    TaskScenario(
        "edge_off_topic",
        "edge_case",
        ["Can you write me a poem?"],
        forbid_writes=True,
        description="Completely off-topic — should respond directly",
    ),
    TaskScenario(
        "edge_polite_decline_create",
        "edge_case",
        [
            "Schedule a team lunch tomorrow at noon for one hour",
            "No, don't add it",
        ],
        forbid_writes=True,
        description="User declines after proposal — no event should be created",
    ),
]


# ── Aggregated datasets ─────────────────────────────────────────────

TASK_SCENARIOS: list[TaskScenario] = (
    _CREATE_EVENT
    + _CHECK_AVAILABILITY
    + _FIND_FREE_TIME
    + _CHECK_CONFLICTS
    + _DELETE_EVENT
    + _PLANNING
    + _GENERAL
    + _EDGE_CASES
)

CORE_SCENARIOS: list[TaskScenario] = (
    _CREATE_EVENT
    + _CHECK_AVAILABILITY
    + _FIND_FREE_TIME
    + _CHECK_CONFLICTS
    + _DELETE_EVENT
    + _PLANNING
    + _GENERAL
)

QUICK_SCENARIOS: list[TaskScenario] = [
    _CREATE_EVENT[0],       # create_team_meeting
    _CHECK_AVAILABILITY[0], # avail_today
    _FIND_FREE_TIME[0],     # free_hour_this_week
    _CHECK_CONFLICTS[0],    # conflict_2pm_tomorrow
    _DELETE_EVENT[0],       # delete_standup
    _PLANNING[0],           # plan_interview
    _GENERAL[0],            # general_morning
]
