import os, time, requests

LIVE = os.getenv("LIVE_TEST") == "1"

def test_live_scan_nifty50():
    if not LIVE:
        import pytest; pytest.skip("LIVE_TEST=1 not set")

    # 1) flip to live adapter (use env before app boots)
    # You’ll run pytest with APP_DATA_ADAPTER=yahoo APP_DEFAULT_UNIVERSE=NIFTY50 LIVE_TEST=1

    # 2) trigger scan
    r = requests.post("http://localhost:8000/api/v1/scan",
                      headers={"Idempotency-Key": f"LIVE_{int(time.time())}"},
                      json={"universe":"NIFTY50"})
    assert r.status_code == 201
    run_id = r.json()["run_id"]

    # 3) check screener has rows
    s = requests.get(f"http://localhost:8000/api/v1/screener?run_id={run_id}&per_page=50")
    assert s.status_code == 200
    js = s.json()
    assert js["pagination"]["total"] > 0
    syms = [row["symbol"] for row in js["items"]]
    assert any(sym.endswith(".NS") for sym in syms)
