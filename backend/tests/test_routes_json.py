import pytest
from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager
from app.main import app

ENDPOINTS = [
    "/api/v1/screener",
    "/api/v1/history",
    "/api/v1/alerts",
    "/api/v1/settings",
    "/api/v1/instruments/RELIANCE/detail",
]

@pytest.mark.asyncio
@pytest.mark.parametrize("path", ENDPOINTS)
async def test_stub_endpoints_return_json(path):
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get(path) if "alerts" not in path else await ac.get(path)
        assert r.status_code == 200
        # Should be valid JSON of some kind (list or dict)
        body = r.json()
        assert isinstance(body, (dict, list))
