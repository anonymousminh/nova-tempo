# Nova Tempo

Voice-first calendar assistant powered by **Amazon Nova Sonic** and a **multi-agent orchestrator** built with [Strands Agents](https://github.com/strands-agents/sdk-python).

Talk to your calendar — create events, check availability, resolve conflicts, decompose goals into tasks, and batch-schedule them, all by voice.

## Tech stack

| Layer | Technology |
|-------|------------|
| Voice | Amazon Nova Sonic (BidiAgent — real-time speech-to-speech) |
| Orchestration | Strands Agents ("Agents as Tools" pattern) |
| Backend | FastAPI + python-socketio + Uvicorn |
| Frontend | Vanilla JS + Socket.IO + Web Audio API / AudioWorklet |
| Calendar | Google Calendar API (OAuth 2.0) |
| LLM infra | AWS Bedrock (us-east-1) |

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Browser                                                         │
│  ┌──────────┐  Socket.IO   ┌─────────────────────────────────┐  │
│  │ Mic/Spkr ├─────────────►│ BidiAgent (Nova Sonic)          │  │
│  │ (Worklet)│◄─────────────│ real-time speech-to-speech      │  │
│  └──────────┘              └──────────────┬──────────────────┘  │
│                                           │ @tool calls         │
│                              ┌────────────┴────────────┐        │
│                              │   OrchestratorAgent     │        │
│                              └────┬───┬───┬───┬───┬────┘        │
│                                   │   │   │   │   │             │
└───────────────────────────────────┼───┼───┼───┼───┼─────────────┘
         ┌──────────────────────────┘   │   │   │   └──────────┐
         ▼              ▼               ▼   │   ▼              ▼
  CalendarAgent   AvailabilityAgent  ConflictRes │  SchedulingAgent
  (CRUD events)   (free/busy, open   Agent      │  (batch time-block
                   slots)         (pre-create   │   scheduling)
                                  conflict      ▼
                                  check)   PlanningAgent
                                           (goal → tasks)
         └──────────────┬──────────────────────┘
                        ▼
                 Google Calendar API
```

The **BidiAgent** handles real-time speech-to-speech via Nova Sonic. It delegates requests to the **OrchestratorAgent**, which routes tasks to five specialized sub-agents — each exposed as a single `@tool` function.

### Agent roles

| Agent | Purpose |
|-------|---------|
| **CalendarAgent** | Create, update, and delete calendar events (mutating operations) |
| **AvailabilityAgent** | Read-only schedule awareness — free/busy, open slots, "Am I free on…?" |
| **ConflictResolutionAgent** | Check for conflicts before creating an event; suggest alternatives |
| **PlanningAgent** | Decompose a high-level goal into schedulable sub-tasks with time estimates |
| **SchedulingAgent** | Find free slots and batch-schedule a list of tasks as time-blocked events |

### Delegation flow

- **Single event** → ConflictResolutionAgent (check) → CalendarAgent (create)
- **Availability question** → AvailabilityAgent
- **Modify / delete** → CalendarAgent (directly)
- **Goal → calendar** → PlanningAgent (decompose) → user review → SchedulingAgent (place on calendar)

## Prerequisites

- **Python 3.11+**
- **AWS credentials** with Bedrock access in `us-east-1` (`aws configure`)
- **Google Cloud project** with the Calendar API enabled and an OAuth 2.0 client ID (for calendar features)

## Quick start

### 1. Backend

```bash
cd backend_fastapi
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env        # edit .env if needed
python main.py
```

The server starts at **http://localhost:8000**.

### 2. Frontend

Serve the `frontend/` folder with any static server (e.g. VS Code Live Server on port 5500):

```
http://localhost:5500/frontend/
```

Click the **mic button** and start talking.

### 3. CLI voice (optional)

Run the BidiAgent directly from your terminal mic/speaker:

```bash
cd backend_fastapi
python scripts/bidi_agent_run.py
```

## Setup details

### AWS credentials

Required for Nova Sonic. Run `aws configure` and make sure your account has Bedrock model access in **us-east-1**.

### Google Calendar (optional)

Without calendar credentials the agent still runs, but calendar tools will return errors.

1. Place your Google OAuth client JSON at `backend_fastapi/secrets/credentials.json`.
2. Generate a user token:
   ```bash
   cd backend_fastapi
   python scripts/get_token.py
   ```
   This writes `secrets/token.json`.
3. Alternatively, set `GOOGLE_CREDENTIALS_PATH` in your `.env` to point to an existing token file.

## Project structure

```
backend_fastapi/
├── main.py                          # Entry point (uvicorn)
├── app/
│   ├── main.py                      # FastAPI + Socket.IO server
│   ├── orchestrator.py              # OrchestratorAgent + @tool wrappers
│   ├── voice_session.py             # Per-client BidiAgent session
│   ├── strands_agent.py             # CalendarAgent
│   ├── availability_agent.py        # AvailabilityAgent
│   ├── conflict_resolution_agent.py # ConflictResolutionAgent
│   ├── planning_agent.py            # PlanningAgent
│   ├── scheduling_agent.py          # SchedulingAgent
│   ├── calendar_tools.py            # Google Calendar API helpers
│   └── calendar_auth.py             # OAuth token loading
├── scripts/
│   ├── bidi_agent_run.py            # Standalone CLI voice session
│   └── get_token.py                 # Generate Google OAuth token
└── secrets/                         # credentials.json + token.json (git-ignored)

frontend/
├── index.html
├── script.js                        # Socket.IO client, voice capture + playback
├── style.css
└── audio-capture-processor.js       # AudioWorklet — mic → PCM Int16 @ 16 kHz
```

## REST API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Service info |
| `GET` | `/health` | Health check |
| `GET` | `/agent/tools` | List available agent tools |
| `POST` | `/agent/tool` | Call an agent tool by name |
| `GET` | `/id` | Get or create a `nova_user_id` cookie |

## Socket.IO events

| Event | Direction | Payload | Description |
|-------|-----------|---------|-------------|
| `voice_start` | client → server | — | Start voice session |
| `voice_started` | server → client | `{ inputSampleRate, outputSampleRate, channels, format }` | Voice session ready |
| `voice_audio_in` | client → server | `{ audio }` (base64 PCM) | Mic audio chunk |
| `voice_audio_out` | server → client | `{ audio, sampleRate, channels }` | Agent audio chunk |
| `voice_transcript` | server → client | `{ text, role, isFinal, currentTranscript }` | Speech transcript |
| `voice_interrupted` | server → client | `{ reason }` | Agent was interrupted |
| `voice_stop` | client → server | — | Stop voice session |
| `voice_stopped` | server → client | — | Session ended |
| `voice_error` | server → client | `{ error }` | Voice session error |

## Adding a new sub-agent

1. Create a new module (e.g. `app/email_agent.py`) with its own tools and system prompt.
2. In `app/orchestrator.py`, add a `_make_<name>_agent_tool()` function following the existing pattern.
3. Append the new `@tool` to the orchestrator's `tools` list in `create_orchestrator_agent()` and `get_orchestrator_tools()`.
4. Update `ORCHESTRATOR_SYSTEM_PROMPT` so the LLM knows when to delegate to the new agent.
