from pathlib import Path
from app.services.screening_service import run_screening
from app.core.db import get_sessionmaker

def test_minimal_snapshot_artifacts(tmp_parquet_root):
    sm = get_sessionmaker()
    with sm() as s:
        detail, created = run_screening(session=s, key="PH11_K", payload={})
        assert created is True
        snap = Path(detail.snapshot_path)
        assert (snap / "_SUCCESS").exists()
        rc = int((snap / "rowcount.txt").read_text().strip() or "0")
        assert rc >= 0
