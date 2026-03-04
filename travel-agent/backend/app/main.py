"""FastAPI application entry point.

Env-agnostic: zero hard AWS SDK imports.
All infra clients are injected via environment variables.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, itinerary, trips
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
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trips.router, prefix="/api/v1", tags=["trips"])
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(itinerary.router, prefix="/api/v1", tags=["itinerary"])


@app.get("/health", tags=["ops"])
async def health():
    return {"status": "ok", "version": app.version}
