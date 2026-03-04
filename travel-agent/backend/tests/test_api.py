"""Integration tests — use a real local Postgres and real Anthropic API.

Run with:
    ANTHROPIC_API_KEY=sk-ant-... pytest tests/test_api.py -v -s
"""
import json
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Patch auth BEFORE importing the app so every endpoint skips JWT validation
import app.auth as auth_module
from app.auth import CurrentUser


async def _mock_get_current_user() -> CurrentUser:
    return CurrentUser(sub="test-user-123", email="test@example.com", name="Test User")


auth_module.get_current_user = _mock_get_current_user

from app.main import app  # noqa: E402


# pytest.ini / pyproject.toml equivalent inline
pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(scope="session")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Tests ──────────────────────────────────────────────────────────────────────

async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    print(f"\nHealth: {data}")


async def test_create_and_list_trips(client):
    resp = await client.post("/api/v1/trips", json={
        "title": "China Spring Break 2025",
        "budget_per_person": 5000,
        "currency": "USD",
        "start_date": "2025-04-05",
        "end_date": "2025-04-15",
    })
    assert resp.status_code == 201, resp.text
    trip = resp.json()
    assert trip["title"] == "China Spring Break 2025"
    assert trip["status"] == "planning"
    trip_id = trip["id"]
    print(f"\nCreated trip id={trip_id}")

    resp = await client.get("/api/v1/trips")
    assert resp.status_code == 200
    trips = resp.json()
    assert any(t["id"] == trip_id for t in trips)
    print(f"Listed {len(trips)} trip(s)")

    resp = await client.get(f"/api/v1/trips/{trip_id}")
    assert resp.status_code == 200


async def test_add_destination(client):
    resp = await client.post("/api/v1/trips", json={"title": "Asia Trip"})
    trip_id = resp.json()["id"]

    resp = await client.post(f"/api/v1/trips/{trip_id}/destinations", json={
        "city": "Beijing",
        "country": "China",
        "country_code": "CHN",
        "arrival_date": "2025-04-05",
        "departure_date": "2025-04-10",
    })
    assert resp.status_code == 200, resp.text
    dest = resp.json()
    assert dest["city"] == "Beijing"
    print(f"\nDestination: {dest['city']}, {dest['country']}")


async def test_conversation_empty(client):
    resp = await client.post("/api/v1/trips", json={"title": "Test Convo Trip"})
    trip_id = resp.json()["id"]

    resp = await client.get(f"/api/v1/trips/{trip_id}/conversation")
    assert resp.status_code == 200
    assert resp.json()["messages"] == []
    print("\nEmpty conversation: OK")


async def test_itinerary_empty(client):
    resp = await client.post("/api/v1/trips", json={"title": "Itin Trip"})
    trip_id = resp.json()["id"]

    resp = await client.get(f"/api/v1/trips/{trip_id}/itinerary")
    assert resp.status_code == 200
    assert resp.json() == []
    print("\nEmpty itinerary: OK")


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") == "test-key",
    reason="Requires real ANTHROPIC_API_KEY",
)
async def test_chat_stream(client):
    """End-to-end: create trip → chat with agent → verify response + persistence."""
    resp = await client.post("/api/v1/trips", json={
        "title": "China Spring Break - E2E Test",
        "budget_per_person": 5000,
        "currency": "USD",
        "start_date": "2025-04-05",
        "end_date": "2025-04-15",
    })
    assert resp.status_code == 201
    trip_id = resp.json()["id"]

    collected_text = ""
    tool_uses = []
    done = False

    async with client.stream(
        "POST",
        f"/api/v1/trips/{trip_id}/chat",
        json={"message": "I want to take my family to China for Spring break, 10 days, $5k per person. We have 2 adults and 1 child aged 8."},
        timeout=90,
    ) as resp:
        assert resp.status_code == 200, resp.text
        assert "text/event-stream" in resp.headers["content-type"]
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                event = json.loads(line[6:])
                if event["type"] == "text":
                    collected_text += event["content"]
                elif event["type"] == "tool_use":
                    tool_uses.append(event["tool"])
                    print(f"  → tool: {event['tool']}")
                elif event["type"] == "done":
                    done = True
                    break

    print(f"\n--- Agent response (first 600 chars) ---")
    print(collected_text[:600])
    print(f"\nTools used: {tool_uses}")
    print(f"Total response length: {len(collected_text)} chars")

    assert done, "Stream should end with 'done' event"
    assert len(collected_text) > 100, "Agent should produce a substantial response"

    # Verify conversation persisted to DB
    resp = await client.get(f"/api/v1/trips/{trip_id}/conversation")
    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert len(messages) >= 2
    assert messages[0]["role"] == "user"
    assert messages[-1]["role"] == "assistant"
    assert len(messages[-1]["content"]) > 50
    print(f"\nConversation persisted: {len(messages)} messages")
