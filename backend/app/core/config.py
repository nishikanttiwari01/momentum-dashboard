# backend/app/core/config.py
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Literal
import os, re, yaml
from pydantic import BaseModel, Field, ValidationError, ConfigDict, field_validator, model_validator

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
    timezone: str = "Asia/Kolkata"
    backfill_on_start: bool = True

class StorageCfg(BaseModel):
    # default works out-of-the-box; tests can override via env APP_SQLITE_PATH
    sqlite_path: str = "./data/local.db"
    parquet_root: Optional[str] = None
    compression: str = "zstd"
    use_dictionary: bool = True
    write_statistics: bool = True
    write_temp_dir: Optional[str] = None

class BackfillRuntimeCfg(BaseModel):
    # Housekeeping for parquet intraday partitions; keeps recent history only.
    intraday_retention_days: int = Field(default=15, ge=1)

class BackfillExportUtilitiesCfg(BaseModel):
    # Toggle NDJSON exports that run after a daily snapshot is produced.
    enabled: bool = True          # master switch for all utility exports
    details: bool | None = None   # optional override for details NDJSON
    screener: bool | None = None  # optional override for screener NDJSON

class BackfillCfg(BaseModel):
    export_utilities: BackfillExportUtilitiesCfg = BackfillExportUtilitiesCfg()


# ----------------- NEW sections (Phase 10) -----------------
# Minimal, focused config blocks to avoid "magic strings" in code and keep YAML-first design.
class TopMoversEligibilityCfg(BaseModel):
    # OPTIONAL gate for Top Movers. Disabled by default: the section is an
    # FYI market overview, so all movers show. Enable to hide illiquid/penny/
    # circuit-style names. Tune in configs/default.yaml under screener.top_movers.
    enabled: bool = False
    min_price: float = 20.0                # exclude penny stocks below this last price (INR)
    min_avg_traded_value_cr: float = 1.0   # min 20d avg traded value, in INR crore
    max_abs_change_pct: float | None = 19.0  # moves at/above this look like circuits; None disables


class ScreenerCfg(BaseModel):
    # Universe preset used when none is supplied at runtime (e.g., GET /screener, POST /scan).
    default_universe: str = "ALL"  # e.g., NIFTY50|NIFTY100|NIFTY500|MIDCAP|SMALLCAP|ALL
    top_movers: TopMoversEligibilityCfg = TopMoversEligibilityCfg()

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


class FloatRange(BaseModel):
    """Normalized inclusive float range stored as min/max."""

    model_config = ConfigDict(extra="ignore")

    min: float | None = None
    max: float | None = None

    @model_validator(mode="before")
    def _coerce_input(cls, value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, (list, tuple)):
            lo = value[0] if len(value) > 0 else None
            hi = value[1] if len(value) > 1 else None
            return {"min": lo, "max": hi}
        if isinstance(value, dict):
            return value
        try:
            f = float(value)
        except (TypeError, ValueError):
            return {}
        return {"min": f, "max": f}

    @field_validator("min", "max", mode="before")
    def _to_float(cls, raw: Any) -> float | None:
        if raw in (None, "", "None"):
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def as_tuple(self) -> Tuple[float | None, float | None]:
        return (self.min, self.max)


class StrategyIndiaSafetyConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    block_buy: bool = False
    blocklist: List[str] = Field(default_factory=list)


class StrategyRulesPreGatesConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    min_close: float = 50.0
    min_score: float = 35.0
    min_relvol20: float = 0.9
    min_adx14: float = 20.0
    min_prox52w_pct: float = -12.0


class StrategyRulesEuphoriaConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rsi_min: float = 75.0
    adx_min: float = 30.0
    alt_rsi_min: float = 70.0
    alt_adx_min: float = 25.0
    adx_slope5_min: float = 0.0


class StrategyRulesRiskConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    breakeven_gain_pct: float = 5.0
    atr_init_mult: float = 2.0
    atr_chand_mult: float = 2.0
    atr_chand_mult_euphoria: float = 1.4


class StrategyRulesConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pre_gates: StrategyRulesPreGatesConfig = StrategyRulesPreGatesConfig()
    euphoria: StrategyRulesEuphoriaConfig = StrategyRulesEuphoriaConfig()
    risk: StrategyRulesRiskConfig = StrategyRulesRiskConfig()


class StrategyBuyPersistenceConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    require_above_vwap: bool = False
    require_prev_day_high_clear: bool = False
    min_minutes_since_open: int = 0
    avoid_lunch_window: bool = False

    @field_validator("min_minutes_since_open", mode="before")
    def _coerce_int(cls, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0


class StrategyBuyProfileConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    min_score: float | None = None
    starter_score_min_intraday: float | None = None
    pivot_clear_pct: FloatRange | None = None
    base_len_min_bars: int | None = None
    prox52w_min_pct: float | None = None
    relvol20_min: float | None = None
    intraday_relvol_min: float | None = None
    adx14_min: float | None = None
    atr_pct: FloatRange | None = None
    day_change_max_pct: float | None = None
    liquidity_min_traded_value_20d: float | None = None
    persistence: StrategyBuyPersistenceConfig = StrategyBuyPersistenceConfig()
    enforced_checks: List[str] = Field(default_factory=list)

    @field_validator(
        "base_len_min_bars",
        mode="before",
    )
    def _coerce_int(cls, value: Any) -> int | None:
        if value in (None, "", "None"):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @field_validator("enforced_checks", mode="before")
    def _listify_checks(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            val = value.strip()
            return [val] if val else []
        if isinstance(value, (list, tuple, set)):
            out: List[str] = []
            for item in value:
                if not isinstance(item, str):
                    item = str(item)
                item = item.strip()
                if item:
                    out.append(item)
            return out
        return []


class StrategySellStopConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    method: str = "chandelier"
    lookback_bars: int = 22
    atr_period: int = 10
    atr_multiple: float = 2.0
    atr_multiple_euphoria: float = 1.4
    floor_pct: float | None = None


class StrategySellBreakevenConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    gain_pct: float = 5.0
    retrace_to_pct: float = 0.10
    intraday_enabled: bool = False


class StrategySellTargetsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    t1_gain_pct: float = 10.0
    t2_gain_pct: float = 15.0
    allow_intraday: bool = True
    # R-ratio based targets (preferred over fixed pct): target = entry + risk * r_ratio.
    # When set, these override t1_gain_pct / t2_gain_pct in selection_service.
    r_ratio_target: float | None = None       # e.g. 2.0 → target at 2× risk
    r_ratio_target_t2: float | None = None    # e.g. 3.0 → T2 at 3× risk
    # Partial exit at T1: sell this fraction and trail the rest to breakeven.
    t1_partial_exit_pct: float = 50.0


class StrategySellWeaknessConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    eod_only: bool = True
    fast_ema_period: int = 10
    max_closes_below_fast_ema: int = 2
    confirm_relvol_min: float = 1.2


class StrategySellFailedBreakoutConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    eod_only: bool = True
    lookback_days: int = 5
    relvol_down_min: float = 1.2


class StrategySellTimeoutConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    eod_only: bool = True
    max_holding_days: int = 20


class StrategySellTrailUpdateConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    min_tick_move: float = 0.25
    route_alerts: bool = False


class StrategySellCommonConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    stop: StrategySellStopConfig = StrategySellStopConfig()
    breakeven: StrategySellBreakevenConfig = StrategySellBreakevenConfig()
    targets: StrategySellTargetsConfig = StrategySellTargetsConfig()
    weakness: StrategySellWeaknessConfig = StrategySellWeaknessConfig()
    failed_breakout: StrategySellFailedBreakoutConfig = StrategySellFailedBreakoutConfig()
    timeout: StrategySellTimeoutConfig = StrategySellTimeoutConfig()
    trail_update: StrategySellTrailUpdateConfig = StrategySellTrailUpdateConfig()


class StrategySellConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    common: StrategySellCommonConfig = StrategySellCommonConfig()


class StrategyProfilesConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    buy: Dict[str, StrategyBuyProfileConfig] = Field(default_factory=dict)
    sell: StrategySellConfig = StrategySellConfig()


class StrategySelectionBreadthConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    min_ratio: float | None = None
    lookback_days: int | None = None


class StrategySelectionRegimeConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    index_symbol: str = "NIFTY_50"
    require_index_above_fast: bool = True
    require_index_above_slow: bool = False
    fast_ma_period: int = 50
    slow_ma_period: int = 200
    breadth: StrategySelectionBreadthConfig = StrategySelectionBreadthConfig()


class StrategySelectionRMultipleConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    stop_from: str = "profiles.sell.common.stop"
    target_from: str = "profiles.sell.common.targets.t1_gain_pct"


class StrategySelectionPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    apply_at_buy: bool = False
    apply_at_selection: bool = True
    weekly_quota: int = 1
    max_open_positions: int = 5
    sector_cooldown_days: int = 10
    symbol_cooldown_days: int = 30
    # Risk-based position sizing: allocate this % of portfolio per trade so that
    # a stop hit costs exactly risk_pct_per_trade% of portfolio.
    # e.g. 1.5 → risk ₹1.5 per ₹100 of book per trade.
    risk_pct_per_trade: float = 1.5
    # Cap how many BUY_SELECTED picks a single screening run can emit. Default
    # 2 matches a "3-5 position book" target while preventing a single strong
    # session from filling every slot at once.
    top_n_per_run: int = 2
    # Diversification helper: cap picks per sector within a single run so a
    # momentum day in one sector (e.g. Banks) doesn't crowd out the book.
    max_per_sector_per_run: int = 1
    regime: StrategySelectionRegimeConfig = StrategySelectionRegimeConfig()
    tiebreaker: str = "R_multiple_then_score"
    r_multiple: StrategySelectionRMultipleConfig = StrategySelectionRMultipleConfig()


class CandidatePoolRankingConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    score_weight: float = 0.4
    r_multiple_weight: float = 0.3
    adx14_weight: float = 0.2
    prox52w_weight: float = 0.1


class CandidatePoolExitRulesConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_age_days: int = 7
    min_adx14: float = 18.0
    min_prox52w_pct: float = -15.0
    require_above_ema20: bool = True

    @field_validator("max_age_days", mode="before")
    def _coerce_int(cls, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 7


class CandidatePoolPersistenceOverrides(BaseModel):
    model_config = ConfigDict(extra="ignore")

    require_above_vwap: bool = True
    require_prev_day_high_clear: bool = False
    min_minutes_since_open: int = 0
    avoid_lunch_window: bool = False

    @field_validator("min_minutes_since_open", mode="before")
    def _coerce_int(cls, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0


class CandidatePoolIntradayOverridesConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    intraday_relvol_min: float | None = 1.2
    starter_score_min_intraday: float | None = None
    persistence: CandidatePoolPersistenceOverrides = CandidatePoolPersistenceOverrides()


class CandidatePoolConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_size: int = 10
    ranking: CandidatePoolRankingConfig = CandidatePoolRankingConfig()
    exit_rules: CandidatePoolExitRulesConfig = CandidatePoolExitRulesConfig()
    intraday_overrides: CandidatePoolIntradayOverridesConfig = CandidatePoolIntradayOverridesConfig()

    @field_validator("max_size", mode="before")
    def _coerce_max_size(cls, value: Any) -> int:
        try:
            n = int(value)
        except (TypeError, ValueError):
            return 10
        return max(1, min(n, 50))


class StrategyConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    india_safety: StrategyIndiaSafetyConfig = StrategyIndiaSafetyConfig()
    rules: StrategyRulesConfig = StrategyRulesConfig()
    profiles: StrategyProfilesConfig = StrategyProfilesConfig()
    selection_policy: StrategySelectionPolicyConfig = StrategySelectionPolicyConfig()
    scores: Dict[str, Any] = Field(default_factory=dict)
    segments: Dict[str, Any] = Field(default_factory=dict)


class AlertThrottleConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    per_symbol_cooldown_min: int | None = None
    per_event_cooldown_min: int | None = None

    @field_validator("per_symbol_cooldown_min", "per_event_cooldown_min", mode="before")
    def _coerce_int(cls, value: Any) -> int | None:
        if value in (None, "", "None"):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class AlertRouteConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    topic: str = ""
    channels: List[str] | None = None
    throttle: AlertThrottleConfig | None = None


class AlertTopicConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    channels: List[str] = Field(default_factory=list)


class AlertDeliveryEmailSMTPConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    host: str | None = None
    port: int | None = None
    use_tls: bool = True
    username: str | None = None
    password: str | None = None
    from_name: str | None = None
    from_addr: str | None = None

    @field_validator("port", mode="before")
    def _port(cls, value: Any) -> int | None:
        if value in (None, "", "None"):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class AlertDeliveryEmailDefaultsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    to: List[str] = Field(default_factory=list)

    @field_validator("to", mode="before")
    def _listify(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple, set)):
            return [str(x) for x in value]
        return []


class AlertDeliveryEmailConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    on_backfill_digest: bool = True
    include_trades: bool = True
    smtp: AlertDeliveryEmailSMTPConfig = AlertDeliveryEmailSMTPConfig()
    defaults: AlertDeliveryEmailDefaultsConfig = AlertDeliveryEmailDefaultsConfig()


class AlertDeliveryNtfyConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    server: str | None = None
    topic_high: str | None = None
    topic_low: str | None = None


class AlertDeliveryWindowsToastConfig(BaseModel):
    """Windows desktop toast + sound channel.

    Enabled only when the backend is running on Windows. Falls back to a
    SKIPPED delivery on non-Windows hosts (dev machines) without erroring.
    """
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    play_sound: bool = True
    # winsound system alias: SystemAsterisk | SystemExclamation | SystemHand |
    # SystemQuestion | SystemDefault
    sound_alias: str = "SystemAsterisk"
    app_id: str = "Momentum Alerts"


class AlertDeliveryConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    email: AlertDeliveryEmailConfig = AlertDeliveryEmailConfig()
    ntfy: AlertDeliveryNtfyConfig = AlertDeliveryNtfyConfig()
    windows_toast: AlertDeliveryWindowsToastConfig = AlertDeliveryWindowsToastConfig()


class AlertEmailTemplate(BaseModel):
    model_config = ConfigDict(extra="allow")

    subject: str = ""
    body: str = ""


class AlertTemplatesConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    ntfy: Dict[str, str] = Field(default_factory=dict)
    email: Dict[str, AlertEmailTemplate] = Field(default_factory=dict)


class AlertDigestScheduleConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    schedule_local_time: str | None = None
    timezone: str | None = None
    include: Dict[str, Any] = Field(default_factory=dict)
    sort: Dict[str, Any] = Field(default_factory=dict)


class AlertDigestConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    eod: AlertDigestScheduleConfig = AlertDigestScheduleConfig()
    weekly: AlertDigestScheduleConfig = AlertDigestScheduleConfig()


class AlertThrottleDefaultsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    per_symbol_cooldown_min: int | None = None
    per_event_cooldown_min: int | None = None


class AlertsRoutingConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: int | str | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    delivery: AlertDeliveryConfig = AlertDeliveryConfig()
    topics: Dict[str, AlertTopicConfig] = Field(default_factory=dict)
    routes: Dict[str, AlertRouteConfig] = Field(default_factory=dict)
    digest: AlertDigestConfig = AlertDigestConfig()
    templates: AlertTemplatesConfig = AlertTemplatesConfig()
    throttle_defaults: AlertThrottleDefaultsConfig = AlertThrottleDefaultsConfig()

    def get_route(self, code: str) -> AlertRouteConfig | None:
        return self.routes.get(code)

    def get_topic_channels(self, topic: str) -> List[str]:
        cfg = self.topics.get(topic)
        return list(cfg.channels) if cfg else []


# ----------------- NEW: News (flexible, YAML-first) -----------------
class NewsCfg(BaseModel):
    """
    Keep sub-sections as Dict[str, Any] so your YAML can evolve
    (sources, clustering, consensus, summarizer, attribution, run_modes, etc.).
    Only a few top-level toggles are typed for convenience.

    Note: ``extra="allow"`` is explicit — the news YAML holds a lot of
    operator-tunable fields (whitelists, routing knobs, sentiment hints)
    that the service reads as dicts and we don't want pydantic silently
    dropping unknown keys.
    """
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    trading_timezone: str = "Asia/Kolkata"

    # Top-level scheduler knobs read by the in-process news ingest job.
    refresh_minutes: int = 60
    since_days: int = 7
    concurrency: int = 4
    shard_size: int = 50

    storage: Dict[str, Any] = Field(default_factory=dict)
    ingest: Dict[str, Any] = Field(default_factory=dict)
    sources: Dict[str, Any] = Field(default_factory=dict)
    sources_whitelist: List[str] = Field(default_factory=list)
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
    sentiment: Dict[str, Any] = Field(default_factory=dict)
    routing: Dict[str, Any] = Field(default_factory=dict)


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: int | str | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    app: AppCfg = AppCfg()
    logging: LoggingCfg = LoggingCfg()
    server: ServerCfg = ServerCfg()
    storage: StorageCfg = StorageCfg()
    backfill: BackfillCfg = BackfillCfg()
    backfill_runtime: BackfillRuntimeCfg = BackfillRuntimeCfg()
    screener: ScreenerCfg = ScreenerCfg()
    scheduler: SchedulerCfg = SchedulerCfg()
    data: DataCfg = DataCfg()
    strategy: StrategyConfig = StrategyConfig()
    candidate_pool: CandidatePoolConfig = CandidatePoolConfig()
    alerts: AlertsRoutingConfig = AlertsRoutingConfig()
    features: Dict[str, Any] = Field(default_factory=dict)
    news: NewsCfg = NewsCfg()

    @property
    def parquet_root(self) -> str:
        storage_root = self.storage.parquet_root
        if storage_root:
            return storage_root
        return str((REPO_ROOT / 'backend' / 'parquet').resolve())

    @property
    def rules(self) -> StrategyRulesConfig:
        return self.strategy.rules

    @property
    def india_safety(self) -> StrategyIndiaSafetyConfig:
        return self.strategy.india_safety

    @property
    def selection_policy(self) -> StrategySelectionPolicyConfig:
        return self.strategy.selection_policy

    @property
    def profiles(self) -> StrategyProfilesConfig:
        return self.strategy.profiles


# ----------------- YAML helpers (unchanged + small additions) -----------------
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

# --- NEW: env placeholder interpolation for alerts.* (supports ${VAR} and ${VAR:-default}) ---
_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::-(.*?))?\}")

def _env_interpolate_str(s: str) -> str:
    def repl(m: re.Match[str]) -> str:
        var = m.group(1)
        default = m.group(2) if m.group(2) is not None else ""
        val = os.getenv(var)
        return val if (val is not None and val != "") else default
    try:
        return _ENV_PATTERN.sub(repl, s)
    except Exception:
        return s

def _env_interpolate_obj(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _env_interpolate_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_env_interpolate_obj(x) for x in obj]
    if isinstance(obj, str):
        return _env_interpolate_str(obj)
    return obj


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

    # --- Back-compat shim: features.news.enabled -> news.enabled if not set ---
    try:
        features_cfg = data.get("features") or {}
        if isinstance(features_cfg, dict):
            fnews = features_cfg.get("news") or {}
            if isinstance(fnews, dict) and ("enabled" in fnews):
                news_cfg = data.get("news") or {}
                if not isinstance(news_cfg, dict):
                    news_cfg = {}
                if "enabled" not in news_cfg:
                    data = _deep_merge(data, {"news": {"enabled": bool(fnews.get("enabled"))}})
    except Exception:
        pass

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
    if os.getenv("NEWS_INGEST_TOKEN"):
        data = _deep_merge(data, {"news": {"ingest": {"require_token": True, "token_env": "NEWS_INGEST_TOKEN"}}})

    # Consolidate trading strategy knobs under a single strategy object (SSOT).
    strategy_payload = dict(data.get("strategy") or {})
    for key in ("india_safety", "rules", "profiles", "selection_policy", "scores", "segments"):
        if key in data:
            strategy_payload.setdefault(key, data.pop(key))
    data["strategy"] = strategy_payload

    # Alerts config (external file resolution)
    alerts_cfg_path = os.getenv("ALERTS_CONFIG_PATH") or data.get("alerts_config_path")
    resolved_alerts_path = _resolve_alerts_path(alerts_cfg_path) if alerts_cfg_path else None
    # NEW: if not provided, try common defaults: backend/config/alerts.yaml then configs/alerts.yaml
    if not resolved_alerts_path:
        candidates = [
            REPO_ROOT / "backend" / "config" / "alerts.yaml",
            CONFIG_DIR / "alerts.yaml",
        ]
        for c in candidates:
            if c.exists():
                resolved_alerts_path = c.resolve()
                break

    if resolved_alerts_path and resolved_alerts_path.exists():
        try:
            _LOADED_FILES.append(resolved_alerts_path)
            alerts_payload = _read_yaml(resolved_alerts_path)
        except Exception:
            alerts_payload = {}
        if isinstance(alerts_payload, dict):
            payload = alerts_payload.get("alerts", alerts_payload)
            if isinstance(payload, dict):
                # merge into top-level alerts dict
                data["alerts"] = _deep_merge(data.get("alerts") or {}, payload)

    # remove key if present in YAML to avoid leaking into Settings
    if "alerts_config_path" in data:
        data.pop("alerts_config_path", None)

    # --- NEW: interpolate ${ENV} and ${ENV:-default} inside alerts.* ---
    if isinstance(data.get("alerts"), dict):
        data["alerts"] = _env_interpolate_obj(data["alerts"])
    else:
        data["alerts"] = {}

    if isinstance(data.get("strategy"), dict):
        data["strategy"] = _env_interpolate_obj(data["strategy"])
    else:
        data["strategy"] = {}

    # Interpolate ${ENV} / ${ENV:-default} placeholders across the rest of the
    # config (news.*, scheduler.*, storage.*, etc.) so YAML like
    # "refresh_minutes: ${NEWS_REFRESH_MINUTES:-60}" resolves to an int before
    # Pydantic validation.
    for _k in list(data.keys()):
        if _k in ("alerts", "strategy"):
            continue  # already interpolated above
        if isinstance(data[_k], (dict, list, str)):
            data[_k] = _env_interpolate_obj(data[_k])

    try:
        return Settings(**data)
    except ValidationError as e:
        # Make config errors explicit rather than failing later at usage sites
        raise RuntimeError(f"Invalid configuration: {e}") from e


def api_prefix() -> str:
    return load().app.api_prefix

# Convenience helpers
def get_settings() -> Settings:
    return load()

def news_enabled() -> bool:
    """Convenience boolean for gates at call sites; defaults to True if misconfigured."""
    try:
        return bool(load().news.enabled)
    except Exception:
        return True
