# backend/app/core/logging_config.py
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_DEFAULT_LOG_DIR = Path(os.getenv("LOG_DIR", Path(__file__).resolve().parents[2] / "logs"))

def setup_logging(level: int = logging.INFO) -> None:
    """
    Idempotent logging setup:
    - console + rotating file handler (10MB x 5 files)
    - creates momentum-dashboard/logs if missing
    - does nothing if handlers already attached
    """
    root = logging.getLogger()
    if root.handlers:  # prevent double config under reload/pytest
        return

    _DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = _DEFAULT_LOG_DIR / "app.log"

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )

    fh = RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)

    root.setLevel(level)
    root.addHandler(fh)
    root.addHandler(ch)

    logging.getLogger(__name__).info("Logging initialized → %s", log_file)
