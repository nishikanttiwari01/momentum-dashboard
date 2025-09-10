from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from typing import List, Dict, Any
import os, yaml
from pydantic import BaseModel, Field, ValidationError

# Track which files were loaded (for logging/diagnostics)
_LOADED_FILES: list[Path] = []

def loaded_files() -> list[str]:
    return [str(p) for p in _LOADED_FILES]

def _find_repo_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "backend").exists() and (p / "frontend").exists():
            return p
    return start.parents[3]

REPO_ROOT = _find_repo_root(Path(__file__).resolve())
CONFIG_DIR = REPO_ROOT / "configs"

class LoggingCfg(BaseModel):
    level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    file: str = "./logs/app.log"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5

class ServerCfg(BaseModel):
    cors_origins: List[str] = ["http://localhost:5173"]
    host: str = "0.0.0.0"
    port: int = 8000

class AppCfg(BaseModel):
    name: str = "Momentum API"
    env: str = Field(default="development")   # effective env after layering
    api_prefix: str = "/api/v1"

class Settings(BaseModel):
    app: AppCfg = AppCfg()
    logging: LoggingCfg = LoggingCfg()
    server: ServerCfg = ServerCfg()

def _read_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out

def _maybe_merge(data: Dict[str, Any], p: Path) -> Dict[str, Any]:
    if p and p.exists():
        _LOADED_FILES.append(p)
        return _deep_merge(data, _read_yaml(p))
    return data

@lru_cache
def load() -> Settings:
    _LOADED_FILES.clear()
    data: Dict[str, Any] = {}

    # 1) default
    data = _maybe_merge(data, CONFIG_DIR / "default.yaml")

    # 2) env selection
    env = os.getenv("APP_ENV") or data.get("app", {}).get("env") or "development"

    # 3) env + env-local
    data = _maybe_merge(data, CONFIG_DIR / f"{env}.yaml")
    data = _maybe_merge(data, CONFIG_DIR / f"{env}-local.yaml")

    # 4) explicit override file
    app_config = os.getenv("APP_CONFIG")
    if app_config:
        data = _maybe_merge(data, Path(app_config).expanduser().resolve())

    # Ensure effective env is set
    data = _deep_merge(data, {"app": {"env": env}})

    try:
        return Settings(**data)
    except ValidationError as e:
        raise RuntimeError(f"Invalid configuration: {e}") from e

def api_prefix() -> str:
    return load().app.api_prefix

# backend/app/core/config.py
class _Storage:
    sqlite_path: str = "./data/local.db"

class _Settings:
    storage: _Storage = _Storage()

def get_settings() -> _Settings:
    # Minimal settings object used by init_sqlite()
    return _Settings()

