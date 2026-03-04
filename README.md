# Travel AI Agent

A conversational AI travel assistant powered by Claude. Plan trips end-to-end — destination research, visa checks, itinerary building, flight and hotel search — and get real-time guidance while you're on the ground.

## Repositories in this monorepo

```
Hello-AI-Agent/
├── travel-agent/       — Business logic: Python FastAPI backend + Next.js frontend
├── travel-agent-infra/ — AWS CDK infrastructure (TypeScript)
└── travel-agent-ux/    — Lightweight mobile PWA (Vite + React 19)
```

## How it works

The agent runs in two modes based on the trip's status and time of day:

**Planning mode** — Gathers preferences, recommends destinations, checks visa and entry requirements, flags travel advisories and local restrictions, checks availability of restaurants and events, searches flights and hotels, and builds a day-by-day itinerary. Syncs confirmed bookings to Google Calendar.

**Guide mode** — Morning briefing with the day's schedule and live conditions. Proactive alerts for flight changes and delays. Dynamic replanning when things change. On-demand local queries (directions, wait times, nearby services).

The agent has no direct AWS dependencies in application code — all infrastructure clients are injected via environment variables, so the same code runs locally with Docker Compose and in production on ECS Fargate.

## Quick start (local)

**Requirements:** Docker Desktop, an [Anthropic API key](https://console.anthropic.com).

```bash
git clone https://github.com/phyominn6688/Hello-AI-Agent.git
cd Hello-AI-Agent/travel-agent

cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY (everything else has defaults)

docker compose up
```

| Service | URL |
|---|---|
| Frontend (Next.js desktop) | http://localhost:3000 |
| Mobile PWA | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

Sign in with mock auth — no Google credentials needed in development.

To also run the mobile PWA locally:

```bash
cd travel-agent-ux
cp .env.example .env   # VITE_AUTH_MODE=mock already set
npm install
npm run dev            # → http://localhost:5173
```

## Project structure

### `travel-agent/` — Application

| Path | Description |
|---|---|
| `backend/app/agent/travel_agent.py` | Claude agent loop — tool dispatch, mode detection |
| `backend/app/agent/prompts.py` | System prompts for planning and guide modes |
| `backend/app/agent/mcp/` | External API wrappers (Amadeus, OpenTable, Ticketmaster, weather, calendar, wallet, rail) |
| `backend/app/api/chat.py` | `POST /trips/{id}/chat` — SSE streaming endpoint |
| `backend/app/models/` | SQLAlchemy ORM models (User, Trip, Itinerary, Conversation, Alert) |
| `frontend/` | Next.js 15 desktop chat + itinerary sidebar |
| `docker-compose.yml` | All services: FastAPI, Next.js, PostgreSQL, Redis, LocalStack, mock-auth |

External API keys are all optional — every MCP wrapper returns mock data when keys are absent.

### `travel-agent-ux/` — Mobile PWA

Separate Vite + React 19 client targeting phone screens. Same backend API, no SSR, pure CSS with custom properties, ~50 KB gzipped app shell.

| Feature | Implementation |
|---|---|
| Routing | State-based (`signin → trips → chat`) — no router library |
| Chat | SSE streaming with inline tool-use chips |
| Itinerary | Bottom sheet — CSS transition + swipe-to-dismiss gesture |
| PWA | `manifest.json` + service worker (cache-first shell, network-first API) |
| iOS safety | `100dvh`, `env(safe-area-inset-*)`, `font-size: 16px` on inputs |

### `travel-agent-infra/` — AWS CDK

Six stacks, deployed in dependency order:

| Stack | What it creates |
|---|---|
| Network | VPC, subnets, security groups |
| Auth | Cognito User Pool + Google IdP |
| Data | Aurora Serverless v2, RDS Proxy, ElastiCache Redis |
| Storage | S3 + CloudFront |
| Compute | ECS Fargate backend + ALB + auto-scaling |
| Async | SQS queues + ECS workers + SNS |

Scales from 10 TPS at launch to 10k TPS without re-architecture.

```bash
cd travel-agent-infra
npm install
npm run diff          # Preview changes
npm run deploy:dev    # Deploy dev environment
```

See [`travel-agent-infra/README.md`](travel-agent-infra/README.md) for prerequisites and full deploy instructions.

## Agent tools

| Tool | API | Mode |
|---|---|---|
| `search_flights` / `search_hotels` | Amadeus | Planning |
| `search_restaurants` / `check_availability` | OpenTable + Google Places | Planning |
| `search_events` | Ticketmaster | Planning |
| `search_rail` | Trip.com | Planning |
| `check_entry_requirements` | Sherpa | Planning |
| `get_weather` | OpenWeatherMap | Both |
| `check_calendar_conflicts` / `update_calendar` | Google Calendar | Planning |
| `save_to_wallet` / `store_document` | Apple PassKit / Google Wallet / S3 | Planning |
| `get_directions` / `get_traffic` / `find_nearby` | Google Maps | Guide |
| `get_daily_itinerary` / `optimize_day_plan` | Internal DB | Guide |
| `cancel_booking` / `modify_booking` | Amadeus (write) | Guide |

Adding a new tool: create a module in `backend/app/agent/mcp/` with `get_tools()` and `execute_tool()`, then register it in `travel_agent.py`. See [`travel-agent/README.md`](travel-agent/README.md) for details.

## Iteration roadmap

| | Scope |
|---|---|
| ✅ Iteration 1 | Planning loop · Cognito auth (Google) · Visa/entry checks · Availability · Flight + hotel search · Calendar sync · Desktop chat UI |
| 🔜 Iteration 2 | Guide mode · Morning briefing · Push notifications (SNS) · Dynamic replanning · Leave-now alerts · PWA geolocation |
| 🔜 Iteration 3 | Real write bookings · Autonomous actions + audit log · Apple/Google Wallet · Flight change monitoring · Rail search |
