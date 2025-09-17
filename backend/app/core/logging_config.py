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
    - Redirect uvicorn loggers to root
    - Force child loggers to propagate
    """
    logging.captureWarnings(True)

    log_dir = Path(os.getenv("LOG_DIR", _repo_root() / "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = []  # reset so we fully control what’s attached

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s")

    # File handler
    fh = RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # Ensure our app loggers propagate to root
    for name in ("app", "app.main", "app.api.v1.instruments", "app.services.detail"):
        logging.getLogger(name).propagate = True

    # Redirect uvicorn loggers to root (no separate handlers)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True

    logging.getLogger("app.core.logging_config").info("Logging initialized → %s", log_file)
