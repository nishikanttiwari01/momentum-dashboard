from starlette.testclient import TestClient
from app.main import app

def test_cors_preflight_allows_vite_origin():
    with TestClient(app) as client:
        r = client.options(
            "/api/v1/alerts",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Starlette CORS returns 200 with allow headers
        assert r.status_code in (200, 204)
        assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
