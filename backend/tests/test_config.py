import json
from pathlib import Path
import pytest
from app.core import config as cfg_mod

def test_config_defaults_and_override_tmpfile(tmp_path, monkeypatch):
    # Clear the cache so each test recalculates settings
    try:
        cfg_mod.load.cache_clear()
    except Exception:
        pass

    # Create a temporary override YAML
    override = tmp_path / "override.yaml"
    override.write_text(
        "logging:\n  level: ERROR\nserver:\n  port: 9876\n", encoding="utf-8"
    )

    monkeypatch.setenv("APP_CONFIG", str(override))

    s = cfg_mod.load()
    assert s.logging.level == "ERROR"
    assert s.server.port == 9876

    # Cleanup for other tests
    cfg_mod.load.cache_clear()
    monkeypatch.delenv("APP_CONFIG", raising=False)
