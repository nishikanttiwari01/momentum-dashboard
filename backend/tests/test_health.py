import pytest
from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager
from app.main import app

@pytest.mark.asyncio
async def test_health_and_live_ok():
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r1 = await ac.get("/api/v1/health")
            r2 = await ac.get("/api/v1/health/live")
        assert r1.status_code == 200 and r1.json() == {"status": "ok"}
        assert r2.status_code == 200 and r2.json() == {"status": "live"}

@pytest.mark.asyncio
async def test_ready_ok_after_startup():
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/health/ready")
        assert r.status_code == 200
