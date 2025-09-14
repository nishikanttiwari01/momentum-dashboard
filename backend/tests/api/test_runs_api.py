from __future__ import annotations

def _ensure_run(client):
    r = client.post("/api/v1/scan", headers={"Idempotency-Key": "LISTME"})
    assert r.status_code in (200, 201)
    return r.json()["run_id"]

def test_runs_list_and_get(client):
    run_id = _ensure_run(client)

    # List
    r = client.get("/api/v1/runs?limit=5")
    assert r.status_code == 200, r.text
    items = r.json().get("items", [])
    assert isinstance(items, list)
    assert any(it["run_id"] == run_id for it in items)

    # Get run by id
    r = client.get(f"/api/v1/runs/{run_id}")
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["run_id"] == run_id
    assert got["status"] in ("RUNNING", "SUCCEEDED", "FAILED")

def test_runs_get_404(client):
    r = client.get("/api/v1/runs/00000000000000")
    assert r.status_code == 404
