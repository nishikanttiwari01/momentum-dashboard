from __future__ import annotations
from pathlib import Path

from app.core.db import get_sessionmaker  # exposed by your db module
from app.services.screening_service import run_screening

def test_service_writes_minimal_snapshot(tmp_parquet_root):
    # Use the live Session from the app (lifespan already ran init_sqlite)
    sm = get_sessionmaker()
    with sm() as s:
        detail, created = run_screening(session=s, key="SVC_K1", payload={})
        assert created is True
        assert detail.run_id
        # Check snapshot directory (Phase-9 minimal—_SUCCESS + rowcount.txt)
        snap = Path(detail.snapshot_path)
        assert (snap / "_SUCCESS").exists()
        rc = (snap / "rowcount.txt").read_text().strip()
        assert rc >= 0
