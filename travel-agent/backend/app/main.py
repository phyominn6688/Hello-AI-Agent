"""FastAPI application entry point.

Env-agnostic: zero hard AWS SDK imports.
All infra clients are injected via environment variables.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, itinerary, location, payments, trips, users, webhooks
from app.config import settings
from app.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Travel AI Agent",
    version="0.1.0",
    description="Conversational AI travel assistant — planning and guide modes",
    lifespan=lifespan,
    # Disable interactive docs in production (docs_enabled=False via env)
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)


# ── Security headers ───────────────────────────────────────────────────────────


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if not settings.docs_enabled:
        # HSTS only in production (where TLS is enforced)
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
    return response


# ── CORS ───────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(trips.router, prefix="/api/v1", tags=["trips"])
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(itinerary.router, prefix="/api/v1", tags=["itinerary"])
app.include_router(users.router, prefix="/api/v1", tags=["users"])
app.include_router(location.router, prefix="/api/v1", tags=["location"])
app.include_router(payments.router, prefix="/api/v1", tags=["payments"])
# Webhooks are mounted at root — no /api/v1 prefix, no auth middleware
app.include_router(webhooks.router, tags=["webhooks"])


@app.get("/health", tags=["ops"])
async def health():
    return {"status": "ok", "version": app.version}
