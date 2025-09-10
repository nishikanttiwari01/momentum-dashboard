# backend/tests/test_problem_422.py
import pytest
from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager
from app.main import app

@pytest.mark.asyncio
async def test_ready_ok():
    async with LifespanManager(app):  # ensures startup/shutdown events run
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/health/ready")
        assert r.status_code == 200

@pytest.mark.asyncio
async def test_problem_422_idempotency_invalid():
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/api/v1/alerts", headers={"Idempotency-Key": "x"*200})
        assert r.status_code == 422
        assert r.headers["content-type"].startswith("application/problem+json")
        body = r.json()
        assert body.get("code") in {"IDEMPOTENCY_INVALID", "VALIDATION_ERROR"}
