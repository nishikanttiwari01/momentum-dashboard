import pytest
from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager
from app.main import app

@pytest.mark.asyncio
async def test_idempotency_invalid_returns_422():
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/api/v1/alerts", headers={"Idempotency-Key": "x"*200})
        assert r.status_code == 422
        assert r.headers["content-type"].startswith("application/problem+json")

@pytest.mark.asyncio
async def test_idempotency_valid_returns_200():
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/api/v1/alerts", headers={"Idempotency-Key": "Key_123"})
        assert r.status_code == 200
