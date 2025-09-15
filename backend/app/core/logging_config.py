from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

def _repo_root() -> Path:
    # backend/app/core/logging_config.py -> parents[3] == repo root (momentum-dashboard/)
    try:
        return Path(__file__).resolve().parents[3]
    except Exception:
        return Path.cwd()

def setup_logging(level: int = logging.INFO) -> None:
    """
    Idempotent logging:
    - Always add a rotating file handler to <repo-root>/logs/app.log
    - Keep console logging
    - Don't remove existing uvicorn handlers, just add ours
    - Force child loggers to propagate to root
    """
    logging.captureWarnings(True)  # include warnings in logs

    log_dir = Path(os.getenv("LOG_DIR", _repo_root() / "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    root = logging.getLogger()
    root.setLevel(level if root.level in (logging.NOTSET, logging.WARNING) else min(root.level, level))

    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    # File handler (if not already present)
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        fh = RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)

    # Console handler (if not already present)
    if not any(isinstance(h, logging.StreamHandler) and h.stream is sys.stdout for h in root.handlers):
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        root.addHandler(ch)

    # Ensure our app loggers propagate to root
    for name in ("app", "app.main", "app.api.v1.instruments", "app.services.detail"):
        lg = logging.getLogger(name)
        lg.propagate = True

    logging.getLogger("app.core.logging_config").info("Logging initialized → %s", log_file)
