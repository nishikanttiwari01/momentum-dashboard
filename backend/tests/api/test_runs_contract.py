import pytest
from asgi_lifespan import LifespanManager
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_runs_list_and_get():
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/runs?limit=5")
            assert r.status_code == 200
            body = r.json()
            assert "items" in body
            if body["items"]:
                rid = body["items"][0]["run_id"]
                r2 = await ac.get(f"/api/v1/runs/{rid}")
                assert r2.status_code == 200
