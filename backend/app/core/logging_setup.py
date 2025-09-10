from pathlib import Path
import logging, sys
from logging.handlers import RotatingFileHandler
from .config import load  # uses your YAML/defaults

def setup_logging() -> None:
    cfg = load().logging  # expects: level, file (string), max_bytes, backup_count

    # resolve log path relative to backend/
    backend_dir = Path(__file__).resolve().parents[2]  # .../backend
    file_path = Path(cfg.file)
    if not file_path.is_absolute():
        file_path = (backend_dir / file_path).resolve()

    # ensure logs folder exists
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # reset root handlers (important when reloading)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, cfg.level, logging.INFO))

    # console + rotating file
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    console = logging.StreamHandler(sys.stdout); console.setFormatter(fmt); root.addHandler(console)
    file_h = RotatingFileHandler(str(file_path), maxBytes=cfg.max_bytes, backupCount=cfg.backup_count)
    file_h.setFormatter(fmt); root.addHandler(file_h)
