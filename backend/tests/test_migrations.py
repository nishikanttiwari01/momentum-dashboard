from __future__ import annotations
import os, shutil, tempfile, subprocess, sys
from pathlib import Path

def test_alembic_upgrade_head_runs_clean():
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        # Ensure alembic.ini points to this DB at runtime via env var or override
        # Simplest: set env var used by alembic.ini sqlalchemy.url line (if templated),
        # else we rely on env.py default sqlite:///./data/local.db and symlink there:
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        target = data_dir / "local.db"
        if target.exists():
            target.unlink()
        # copy blank file path (not needed, alembic will create)
        # Run upgrade
        r = subprocess.run(["alembic", "upgrade", "head"], cwd="backend", capture_output=True, text=True)
        assert r.returncode == 0, r.stderr + r.stdout
        assert target.exists(), "SQLite DB not created"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
