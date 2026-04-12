# Travel AI Agent — Project Guide

## Repository Structure

This monorepo contains two independent projects:

```
Hello-AI-Agent/
├── travel-agent/          ← Business logic (Python + Next.js)
└── travel-agent-infra/    ← AWS CDK infrastructure (TypeScript)
```

## travel-agent

Conversational AI travel assistant with two modes:
- **Planning mode** — destination research, itinerary building, visa checks, availability
- **Guide mode** — real-time daily briefing, dynamic replanning, on-demand local queries

### Tech Stack
- **Backend**: Python 3.12, FastAPI, SQLAlchemy (async), Alembic, Anthropic SDK
- **Frontend**: Next.js 15, TypeScript, Tailwind CSS
- **AI**: Claude claude-sonnet-4-6 with MCP-style tool use
- **DB**: PostgreSQL (Aurora Serverless v2 in prod)
- **Cache**: Redis (ElastiCache cluster mode in prod)
- **Async**: SQS + ECS workers

### Local Development

```bash
cd travel-agent
cp .env.example .env          # Fill in ANTHROPIC_API_KEY at minimum
docker compose up             # Starts all services

# Backend hot-reloads on file changes
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# pgAdmin: http://localhost:5050 (dev override)
```

### Key Files
- `backend/app/main.py` — FastAPI app entry point
- `backend/app/agent/travel_agent.py` — Claude agent loop (agentic tool use)
- `backend/app/agent/prompts.py` — Planning + guide mode system prompts
- `backend/app/agent/mcp/` — External API wrappers (Amadeus, weather, etc.)
- `backend/app/models/` — SQLAlchemy ORM models
- `frontend/app/trips/[id]/page.tsx` — Main chat + itinerary view

### Environment Variables (backend)
All infra clients injected via env vars — zero hard AWS imports in app code:
- `DATABASE_URL` — PostgreSQL connection string (asyncpg driver)
- `REDIS_URL` — Redis connection string
- `QUEUE_URL` — SQS queue URL
- `STORAGE_BUCKET` — S3 bucket name
- `AUTH_JWKS_URL` — JWKS endpoint (mock-auth in dev, Cognito in prod)
- `ANTHROPIC_API_KEY` — Required
- External API keys — all optional; MCP wrappers return mock data when not configured

### Agent Tool System
Tools are defined in `backend/app/agent/mcp/*.py` — each module provides:
- `get_tools()` → list of Anthropic tool definitions (JSON schema)
- `execute_tool(name, input)` → async call to external API

Tools are registered in `travel_agent.py:TOOL_DISPATCH`. To add a new tool:
1. Add the module in `agent/mcp/`
2. Import and add to `PLANNING_TOOLS` / `GUIDE_TOOLS`
3. Add to `TOOL_DISPATCH`

### Iteration Status
- **Iteration 1** (current): Core planning loop, Cognito (Google), chat UI, itinerary sidebar
- **Iteration 2**: Guide mode, push notifications, dynamic replanning, PWA location
- **Iteration 3**: Real bookings, autonomous actions, digital wallet, flight monitoring

## travel-agent-infra

AWS CDK TypeScript — all infrastructure as code.

```bash
cd travel-agent-infra
npm install
npm run deploy:dev            # Deploy dev environment
npm run diff                  # Preview changes
```

### Stacks (deploy order matters — CDK handles dependencies)
1. `Network` — VPC, subnets, security groups
2. `Auth` — Cognito User Pool + Google IdP
3. `Data` — Aurora Serverless v2 + RDS Proxy + ElastiCache Redis
4. `Storage` — S3 + CloudFront
5. `Compute` — ECS Fargate backend + ALB + auto-scaling
6. `Async` — SQS queues + ECS workers + SNS

### Prerequisites for CDK Deploy
```
AWS_DEFAULT_ACCOUNT=123456789012
AWS_DEFAULT_REGION=us-east-1

# SSM Parameters (set before deploy):
/travel-agent/dev/google-client-id      (SecureString)
/travel-agent/dev/google-client-secret  (SecureString)
/travel-agent/dev/anthropic-api-key     (SecureString)

# ECR repositories must exist before Compute/Async stacks:
aws ecr create-repository --repository-name travel-agent-backend
```
