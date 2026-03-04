# Travel AI Agent

A conversational AI travel assistant powered by Claude claude-sonnet-4-6. Plan trips end-to-end and get real-time guidance while traveling.

**Two modes:**
- **Planning** — destination research, itinerary building, visa/entry checks, availability, calendar sync
- **Guide** — morning briefing, live conditions, dynamic replanning, on-demand local queries

---

## Stack

| Layer | Technology |
|---|---|
| AI | Claude claude-sonnet-4-6 (Anthropic SDK, MCP-style tool use) |
| Backend | Python 3.12, FastAPI, SQLAlchemy async |
| Frontend | Next.js 15, TypeScript, Tailwind CSS |
| Database | PostgreSQL (Aurora Serverless v2 in prod) |
| Cache | Redis (ElastiCache cluster mode in prod) |
| Async jobs | SQS + ECS workers |
| Auth | AWS Cognito (Google OAuth) / mock-auth in dev |

---

## Local Development

**Prerequisites:** Docker Desktop — all services run via Compose, no local installs needed.

```bash
git clone <repo>
cd travel-agent

# 1. Copy env file and add your Anthropic API key (minimum required)
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY at minimum

# 2. Start everything
docker compose up

# Optional dev tooling (pgAdmin + Redis Insight)
docker compose --profile dev up
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| pgAdmin | http://localhost:5050 |
| Redis Insight | http://localhost:5540 |

Sign in at http://localhost:3000 — mock-auth is pre-configured, no Google credentials needed in dev.

### Without Docker

If you prefer running services directly:

```bash
# Backend
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Point to a local Postgres (e.g. brew install postgresql@16)
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/travelagent"
export ANTHROPIC_API_KEY="sk-ant-..."
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 NEXT_PUBLIC_AUTH_MODE=mock npm run dev
```

---

## Environment Variables

Copy `.env.example` to `.env`. Only `ANTHROPIC_API_KEY` is required to run — all other API integrations fall back to mock data when keys are absent.

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | **Yes** | Claude API key |
| `AMADEUS_CLIENT_ID` / `_SECRET` | No | Flight + hotel search (sandbox: [developers.amadeus.com](https://developers.amadeus.com)) |
| `OPENWEATHER_API_KEY` | No | Weather (free tier: [openweathermap.org](https://openweathermap.org/api)) |
| `GOOGLE_MAPS_API_KEY` | No | Restaurant search, directions, places |
| `TICKETMASTER_API_KEY` | No | Event search ([developer.ticketmaster.com](https://developer.ticketmaster.com)) |
| `TRIPDOTCOM_API_KEY` | No | High-speed rail search |
| `GOOGLE_CALENDAR_CREDENTIALS_JSON` | No | Google Calendar sync (service account JSON) |
| `SHERPA_API_KEY` | No | Visa requirement lookups |

---

## Project Structure

```
travel-agent/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── config.py            # Settings (all via env vars)
│   │   ├── auth.py              # JWT validation (Cognito / mock-auth)
│   │   ├── api/
│   │   │   ├── trips.py         # Trip + destination CRUD
│   │   │   ├── chat.py          # POST /trips/{id}/chat — SSE streaming
│   │   │   └── itinerary.py     # Itinerary CRUD + alerts
│   │   ├── agent/
│   │   │   ├── travel_agent.py  # Claude agent loop + tool dispatch
│   │   │   ├── prompts.py       # Planning and guide mode system prompts
│   │   │   └── mcp/             # External API wrappers
│   │   │       ├── amadeus.py       # Flights + hotels
│   │   │       ├── opentable.py     # Restaurant search + availability
│   │   │       ├── ticketmaster.py  # Events
│   │   │       ├── weather.py       # OpenWeatherMap
│   │   │       ├── calendar.py      # Google Calendar
│   │   │       ├── wallet.py        # Apple/Google Wallet passes
│   │   │       └── tripdotcom.py    # High-speed rail
│   │   ├── workers/
│   │   │   ├── flight_monitor.py   # SQS consumer — flight status polling
│   │   │   ├── notifier.py         # SQS consumer — push notifications
│   │   │   └── scheduler.py        # Guide mode nudges
│   │   ├── models/              # SQLAlchemy ORM models
│   │   └── db/                  # Database setup + Alembic migrations
│   ├── tests/
│   │   └── test_api.py          # Integration tests
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── page.tsx             # Trip list + sign-in
│   │   └── trips/[id]/page.tsx  # Chat + itinerary view
│   ├── components/
│   │   ├── ChatWindow.tsx       # SSE streaming chat input/output
│   │   ├── MessageBubble.tsx    # Markdown-rendering message component
│   │   ├── ItinerarySidebar.tsx # Collapsible day-by-day itinerary
│   │   ├── AlertBanner.tsx      # Proactive agent alerts
│   │   ├── DayBriefing.tsx      # Guide mode morning card
│   │   └── TradeOffOptions.tsx  # Replanning options card
│   ├── lib/
│   │   ├── api.ts               # API client + SSE streaming generator
│   │   └── auth.ts              # Auth abstraction (Amplify / mock)
│   └── types/index.ts           # Shared TypeScript types
├── scripts/
│   └── localstack-init.sh       # Creates S3/SQS/SNS on LocalStack startup
├── docker-compose.yml
├── docker-compose.override.yml  # Dev extras: pgAdmin, Redis Insight
└── .env.example
```

---

## API Reference

Full interactive docs at http://localhost:8000/docs when running locally.

### Trips

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/trips` | List all trips for current user |
| `POST` | `/api/v1/trips` | Create a new trip |
| `GET` | `/api/v1/trips/{id}` | Get trip details |
| `PATCH` | `/api/v1/trips/{id}` | Update trip (title, dates, status) |
| `DELETE` | `/api/v1/trips/{id}` | Delete trip |
| `POST` | `/api/v1/trips/{id}/destinations` | Add a destination |

### Chat

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/trips/{id}/chat` | Send message — returns SSE stream |
| `GET` | `/api/v1/trips/{id}/conversation` | Full conversation history |

**SSE event types:**

```
data: {"type": "text", "content": "..."}          # Streamed text delta
data: {"type": "tool_use", "tool": "search_flights", "id": "..."}
data: {"type": "tool_result", "tool": "search_flights", "result": {...}}
data: {"type": "done"}
data: {"type": "error", "message": "..."}
```

### Itinerary

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/trips/{id}/itinerary` | Full itinerary, ordered by date |
| `POST` | `/api/v1/trips/{id}/itinerary/{date}/items` | Add item to a day |
| `PATCH` | `/api/v1/trips/{id}/items/{item_id}` | Update item |
| `GET` | `/api/v1/trips/{id}/alerts` | Proactive agent alerts |
| `POST` | `/api/v1/trips/{id}/alerts/{alert_id}/read` | Mark alert as read |

---

## Agent Tools

The agent has access to the following tools, organized by MCP wrapper:

| Tool | Module | Description |
|---|---|---|
| `search_flights` | amadeus | Amadeus flight search |
| `search_hotels` | amadeus | Amadeus hotel search |
| `search_restaurants` | opentable | Google Places restaurant search |
| `check_availability` | opentable | Restaurant availability deep-link |
| `search_events` | ticketmaster | Ticketmaster event search |
| `get_weather` | weather | OpenWeatherMap current + forecast |
| `check_calendar_conflicts` | calendar | Google Calendar conflict check |
| `update_calendar` | calendar | Add booking to Google Calendar |
| `save_to_wallet` | wallet | Queue Apple/Google Wallet pass generation |
| `store_document` | wallet | Queue S3 document storage |
| `search_rail` | tripdotcom | Trip.com high-speed rail search |

### Adding a new tool

1. Create `backend/app/agent/mcp/my_service.py` with:
   ```python
   def get_tools() -> list[dict]: ...      # Anthropic tool definitions
   async def execute_tool(name, input) -> dict: ...  # API call
   ```
2. Import and add to `PLANNING_TOOLS` / `GUIDE_TOOLS` in `travel_agent.py`
3. Add to `TOOL_DISPATCH` dict in `travel_agent.py`

---

## Running Tests

```bash
cd backend

# Unit + integration tests (mock auth, real local DB)
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/travelagent" \
ANTHROPIC_API_KEY=sk-ant-... \
pytest tests/ -v

# The chat stream test requires a funded API key and is automatically
# skipped if the key is missing or has zero balance.
```

---

## Data Model

```
User                    Trip (planning | active | completed)
  └─ travelers[]          └─ Destination[]
  └─ preferences{}        └─ Itinerary (per day)
                              └─ ItineraryItem
                                   type: flight|hotel|restaurant|event|...
                                   flexibility: fixed|flexible|droppable
                                   wishlist_status: wishlist|available|booked|...
                          └─ Conversation
                              └─ messages[]
                          └─ AgentAction (audit log)
                          └─ Alert
```

---

## Iteration Roadmap

| | Feature |
|---|---|
| ✅ **Iteration 1** | Core planning loop · Cognito auth (Google) · Visa/entry checks · Availability checks · Flight + hotel search · Calendar sync · Responsive chat UI |
| 🔜 **Iteration 2** | Guide mode · Morning briefing · Push notifications (SNS) · Dynamic replanning · Leave-now alerts · PWA geolocation |
| 🔜 **Iteration 3** | Real bookings (write access) · Autonomous actions + audit log · Apple/Google Wallet · Flight change monitoring · Rail search |
