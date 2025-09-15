from __future__ import annotations
import re
from pathlib import Path

RUN_PART_RE = re.compile(r"^run_id=\d{14}$")  # YYYYMMDDHHMMSS

def test_scan_201_first_time_and_snapshot_written(client, tmp_parquet_root):
    # First call with a key should create a new run → 201
    r = client.post("/api/v1/scan", headers={"Idempotency-Key": "KEY_123"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["run_id"]
    assert body["status"] in ("RUNNING", "SUCCEEDED")
    # Snapshot folder should exist for Phase 9 minimal writer
    scores = (tmp_parquet_root / "scores")
    runs = [p for p in scores.glob("run_id=*") if p.is_dir()]
    assert runs, "No snapshot directory created under scores/"
    for p in runs:
        assert RUN_PART_RE.match(p.name), f"bad partition name: {p.name}"
        assert (p / "_SUCCESS").exists()
        assert (p / "rowcount.txt").exists()
        assert int((p / "rowcount.txt").read_text().strip()) >= 0

def test_scan_200_on_idempotent_replay(client):
    # Replay with same key should return 200 (not 201)
    first = client.post("/api/v1/scan", headers={"Idempotency-Key": "REPLAY_1"})
    assert first.status_code == 201
    again = client.post("/api/v1/scan", headers={"Idempotency-Key": "REPLAY_1"})
    assert again.status_code == 200, again.text

def test_scan_422_on_invalid_key(client):
    # Space and punctuation should be rejected by header validator
    r = client.post("/api/v1/scan", headers={"Idempotency-Key": "bad key!"})
    assert r.status_code == 422, r.text
    body = r.json()
    # Your Problem+JSON handler includes a 'detail' with 'code'
    assert "detail" in body
