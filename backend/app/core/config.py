# backend/app/core/config.py
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from typing import List, Dict, Any, Optional
import os, yaml
from pydantic import BaseModel, Field, ValidationError

# Track which files were loaded (for logging/diagnostics)
_LOADED_FILES: list[Path] = []

def loaded_files() -> list[str]:
    return [str(p) for p in _LOADED_FILES]

def _find_repo_root(start: Path) -> Path:
    # unchanged: discover monorepo root by presence of backend+frontend folders
    for p in [start] + list(start.parents):
        if (p / "backend").exists() and (p / "frontend").exists():
            return p
    return start.parents[3]

REPO_ROOT = _find_repo_root(Path(__file__).resolve())
CONFIG_DIR = REPO_ROOT / "configs"


# ----------------- Sections (existing) -----------------
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
    timezone: str = "Asia/Singapore"
    backfill_on_start: bool = True

class StorageCfg(BaseModel):
    # default works out-of-the-box; tests can override via env APP_SQLITE_PATH
    sqlite_path: str = "./data/local.db"
    parquet_root: Optional[str] = None
    compression: str = "zstd"
    use_dictionary: bool = True
    write_statistics: bool = True
    write_temp_dir: Optional[str] = None


# ----------------- NEW sections (Phase 10) -----------------
# Minimal, focused config blocks to avoid "magic strings" in code and keep YAML-first design.
class ScreenerCfg(BaseModel):
    # Universe preset used when none is supplied at runtime (e.g., GET /screener, POST /scan).
    default_universe: str = "ALL"  # e.g., NIFTY50|NIFTY100|NIFTY500|MIDCAP|SMALLCAP|ALL

class TradingWindowCfg(BaseModel):
    tz: str = "Asia/Kolkata"
    days: List[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    start: str = "09:15"
    end: str = "15:30"


class SchedulerCfg(BaseModel):
    # Whether background scans are enabled; if False, app runs without APScheduler.
    enabled: bool = False
    # Minutes between scans; keep small & predictable for local use.
    interval_minutes: int = 15
    # Universe to use for scheduled scans; if None, fall back to screener.default_universe.
    universe: str | None = None
    # Optional market trading window; if omitted the scheduler runs continuously.
    trading_window: TradingWindowCfg | None = None

class DataCfg(BaseModel):
    # Data adapter toggle: "stub" (deterministic tests) or "yahoo" (live).
    adapter: str = "stub"


class RulesEuphoriaCfg(BaseModel):
    rsi_min: float = 75.0
    adx_min: float = 30.0
    alt_rsi_min: float = 70.0
    alt_adx_min: float = 25.0
    adx_slope5_min: float = 0.0

class RulesSoftGatesCfg(BaseModel):
    min_score: float = 35.0
    min_relvol20: float = 0.8
    min_adx14: float = 22.0
    min_prox52w_pct: float = -10.0
    require_base_len_bars: float = 15.0
    breakout_overrides_soft_gates: bool = True

class RulesCfg(BaseModel):
    breakeven_gain_pct: float = 5.0
    atr_chand_mult: float = 2.0
    atr_chand_mult_euphoria: float = 1.4
    atr_init_mult: float = 2.0
    euphoria: RulesEuphoriaCfg = RulesEuphoriaCfg()
    soft_gates: RulesSoftGatesCfg = RulesSoftGatesCfg()


# ----------------- NEW: News (flexible, YAML-first) -----------------
class NewsCfg(BaseModel):
    """
    Keep sub-sections as Dict[str, Any] so your YAML can evolve
    (sources, clustering, consensus, summarizer, attribution, run_modes, etc.).
    Only a few top-level toggles are typed for convenience.
    """
    enabled: bool = True
    trading_timezone: str = "Asia/Kolkata"
    storage: Dict[str, Any] = Field(default_factory=dict)
    ingest: Dict[str, Any] = Field(default_factory=dict)
    sources: Dict[str, Any] = Field(default_factory=dict)
    extraction: Dict[str, Any] = Field(default_factory=dict)
    mapping: Dict[str, Any] = Field(default_factory=dict)
    clustering: Dict[str, Any] = Field(default_factory=dict)
    consensus: Dict[str, Any] = Field(default_factory=dict)
    events: Dict[str, Any] = Field(default_factory=dict)
    summarizer: Dict[str, Any] = Field(default_factory=dict)
    attribution: Dict[str, Any] = Field(default_factory=dict)
    run_modes: Dict[str, Any] = Field(default_factory=dict)
    backfill: Dict[str, Any] = Field(default_factory=dict)
    on_demand: Dict[str, Any] = Field(default_factory=dict)
    trigger: Dict[str, Any] = Field(default_factory=dict)
    fallbacks: Dict[str, Any] = Field(default_factory=dict)


class Settings(BaseModel):
    # Existing sections
    app: AppCfg = AppCfg()
    logging: LoggingCfg = LoggingCfg()
    server: ServerCfg = ServerCfg()
    storage: StorageCfg = StorageCfg()
    # NEW sections (Phase 10)
    screener: ScreenerCfg = ScreenerCfg()
    scheduler: SchedulerCfg = SchedulerCfg()
    data: DataCfg = DataCfg()
    rules: RulesCfg = RulesCfg()
    # --- Minimal addition for Alerts (non-breaking) ---
    # Keep it as a free-form dict so YAML can evolve (rules, channels, throttle, etc.)
    # The alerts service will parse/normalize it.
    alerts: Dict[str, Any] = Field(default_factory=dict)
    # --- NEW: features & news (keep flexible) ---
    features: Dict[str, Any] = Field(default_factory=dict)
    news: NewsCfg = NewsCfg()

    @property
    def parquet_root(self) -> str:
        storage_root = self.storage.parquet_root
        if storage_root:
            return storage_root
        return str((REPO_ROOT / 'backend' / 'parquet').resolve())



# ----------------- YAML helpers (unchanged) -----------------
def _read_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _resolve_alerts_path(candidate: str | None) -> Optional[Path]:
    if not candidate:
        return None
    path = Path(candidate)
    if path.is_absolute():
        return path
    for base in (CONFIG_DIR, REPO_ROOT):
        merged = (base / path).resolve()
        if merged.exists():
            return merged
    return (CONFIG_DIR / path).resolve()

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


# ----------------- Loader (with env overrides) -----------------
@lru_cache
def load() -> Settings:
    _LOADED_FILES.clear()
    data: Dict[str, Any] = {}

    # 1) default.yaml (optional)
    data = _maybe_merge(data, CONFIG_DIR / "default.yaml")

    # 2) pick env (APP_ENV > default.yaml:app.env > "development")
    env = os.getenv("APP_ENV") or data.get("app", {}).get("env") or "development"

    # 3) env + env-local (optional)
    data = _maybe_merge(data, CONFIG_DIR / f"{env}.yaml")
    data = _maybe_merge(data, CONFIG_DIR / f"{env}-local.yaml")

    # 4) explicit override file (optional)
    app_config = os.getenv("APP_CONFIG")
    if app_config:
        data = _maybe_merge(data, Path(app_config).expanduser().resolve())

    # Normalize storage paths to be absolute (respect repo root for relative inputs)
    storage_cfg = data.get("storage") or {}
    if isinstance(storage_cfg, dict):
        parquet_root = storage_cfg.get("parquet_root")
        if isinstance(parquet_root, str) and parquet_root.strip():
            p = Path(parquet_root)
            if not p.is_absolute():
                p = (REPO_ROOT / p).resolve()
            else:
                p = p.resolve()
            storage_cfg["parquet_root"] = str(p)
        tmp_dir = storage_cfg.get("write_temp_dir")
        if isinstance(tmp_dir, str) and tmp_dir.strip():
            t = Path(tmp_dir)
            if not t.is_absolute():
                t = (REPO_ROOT / t).resolve()
            else:
                t = t.resolve()
            storage_cfg["write_temp_dir"] = str(t)
        data["storage"] = storage_cfg

    # --- NEW: normalize news.storage paths to absolute (if provided) ---
    news_cfg = data.get("news") or {}
    if isinstance(news_cfg, dict):
        news_storage = news_cfg.get("storage") or {}
        # parquet_root
        nr = news_storage.get("parquet_root")
        if isinstance(nr, str) and nr.strip():
            p = Path(nr)
            if not p.is_absolute():
                p = (REPO_ROOT / p).resolve()
            else:
                p = p.resolve()
            news_storage["parquet_root"] = str(p)
        # duckdb_path
        nd = news_storage.get("duckdb_path")
        if isinstance(nd, str) and nd.strip():
            d = Path(nd)
            if not d.is_absolute():
                d = (REPO_ROOT / d).resolve()
            else:
                d = d.resolve()
            news_storage["duckdb_path"] = str(d)
        news_cfg["storage"] = news_storage

        # backfill.watermark_file (optional path)
        backfill_cfg = news_cfg.get("backfill") or {}
        wm = backfill_cfg.get("watermark_file")
        if isinstance(wm, str) and wm.strip():
            w = Path(wm)
            if not w.is_absolute():
                w = (REPO_ROOT / w).resolve()
            else:
                w = w.resolve()
            backfill_cfg["watermark_file"] = str(w)
        news_cfg["backfill"] = backfill_cfg

        data["news"] = news_cfg

    # 5) Environment variable shims for common nested keys (kept simple & explicit)
    #    This complements, not replaces, YAML files.
    if os.getenv("APP_SQLITE_PATH"):
        data = _deep_merge(data, {"storage": {"sqlite_path": os.getenv("APP_SQLITE_PATH")}})

    # --- Phase 10 env shims (NEW) ---
    # Screener
    if os.getenv("APP_DEFAULT_UNIVERSE"):
        data = _deep_merge(data, {"screener": {"default_universe": os.getenv("APP_DEFAULT_UNIVERSE")}})
    # Scheduler
    if os.getenv("APP_SCHED_ENABLED") is not None:
        # Accept "1/0", "true/false" (case-insensitive)
        v = os.getenv("APP_SCHED_ENABLED", "").strip().lower()
        data = _deep_merge(data, {"scheduler": {"enabled": v in {"1", "true", "yes", "on"}}})
    if os.getenv("APP_SCHED_INTERVAL"):
        data = _deep_merge(data, {"scheduler": {"interval_minutes": int(os.getenv("APP_SCHED_INTERVAL"))}})
    if os.getenv("APP_SCHED_UNIVERSE"):
        data = _deep_merge(data, {"scheduler": {"universe": os.getenv("APP_SCHED_UNIVERSE")}})
    # Data adapter
    if os.getenv("APP_DATA_ADAPTER"):
        data = _deep_merge(data, {"data": {"adapter": os.getenv("APP_DATA_ADAPTER")}})

    # --- NEW: News env shims (optional, safe defaults) ---
    if os.getenv("APP_NEWS_ENABLED") is not None:
        v = os.getenv("APP_NEWS_ENABLED", "").strip().lower()
        data = _deep_merge(data, {"news": {"enabled": v in {"1", "true", "yes", "on"}}})
    # If a token is provided, auto-require it for ingest
    if os.getenv("NEWS_INGEST_TOKEN"):
        data = _deep_merge(data, {"news": {"ingest": {"require_token": True, "token_env": "NEWS_INGEST_TOKEN"}}})

    # Alerts config (optional external file)
    alerts_cfg_path = os.getenv("ALERTS_CONFIG_PATH") or data.get("alerts_config_path")
    resolved_alerts_path = _resolve_alerts_path(alerts_cfg_path) if alerts_cfg_path else None
    if resolved_alerts_path and resolved_alerts_path.exists():
        try:
            _LOADED_FILES.append(resolved_alerts_path)
            alerts_payload = _read_yaml(resolved_alerts_path)
        except Exception:
            alerts_payload = {}
        if isinstance(alerts_payload, dict):
            payload = alerts_payload.get("alerts", alerts_payload)
            if isinstance(payload, dict):
                data["alerts"] = _deep_merge(data.get("alerts") or {}, payload)
    if "alerts_config_path" in data:
        data.pop("alerts_config_path", None)

    try:
        return Settings(**data)
    except ValidationError as e:
        # Make config errors explicit rather than failing later at usage sites
        raise RuntimeError(f"Invalid configuration: {e}") from e


def api_prefix() -> str:
    return load().app.api_prefix

# Back-compat for modules that still call get_settings()
def get_settings() -> Settings:
    return load()
