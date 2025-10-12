from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, timezone, time, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, Iterable, List, Optional, Tuple
import json
import logging
import os
import math

from app.repos.sql.alerts_repo import AlertsRepo
from app.repos.sql.alerts_repo import AlertState as AlertStateDTO
from app.repos.parquet.scores_repo import ScoresRepo
from app.domain.rules.next_action import compute_next_action, global_pre_gates
from app.notifs.telegram_toast import notify as notify_tg_toast
from app.notifs.ntfy import notify as notify_ntfy

log = logging.getLogger(__name__)

RULE_CODE = "momentum_score_gte"
ACTION_ORDER = {"BUY_STARTER": 1, "BUY_PULLBACK": 2, "BUY_BREAKOUT": 3}


@dataclass
class AlertsConfig:
    enabled: bool = True
    min_score: int = 70
    regime_down_min_score: int = 72
    block_starter_in_down: bool = True
    persistence_runs: int = 2
    score_jump_realert: int = 10
    cooloff_runs_after_alert: int = 0
    cooloff_runs_failed_breakout: int = 3
    suppress_open_minutes: int = 15
    suppress_close_minutes: int = 5
    min_breadth_breakout: float = 35.0
    max_upper_circuit_hits: int = 2
    tz_name: str = "Asia/Kolkata"
    channels: Dict[str, bool] = None

    @staticmethod
    def from_settings(cfg: Dict[str, Any]) -> "AlertsConfig":
        alerts = cfg.get("alerts", {}) if cfg else {}
        rules_cfg = alerts.get("alerts", alerts)
        rules = alerts.get("rules", rules_cfg)
        rules = rules.get("actions", rules)
        # Fallback to top-level keys if nested structure absent
        meta = alerts.get("alerts", {})
        channels = alerts.get("channels", {})
        alerts_inner = alerts.get("alerts", {})
        cooloff_after_alert = alerts_inner.get(
            "cooloff_runs_after_alert",
            alerts_inner.get("cooloff_runs_after_sell", alerts.get("cooloff_runs_after_alert", alerts.get("cooloff_runs_after_sell", 2))),
        )
        cooloff_after_failed_bo = alerts_inner.get(
            "cooloff_runs_after_failed_bo",
            alerts.get("cooloff_runs_after_failed_bo", 3),
        )
        return AlertsConfig(
            enabled=bool(alerts.get("enabled", True)),
            min_score=int(alerts.get("rules", {}).get("min_score", alerts.get("min_score", 70))),
            regime_down_min_score=int(alerts.get("regime", {}).get("down", {}).get("min_score", 72)),
            block_starter_in_down=bool(alerts.get("regime", {}).get("down", {}).get("block_starter", True)),
            persistence_runs=int(alerts.get("alerts", {}).get("persistence_runs_intraday", alerts.get("persistence_runs_intraday", 2))),
            score_jump_realert=int(alerts.get("alerts", {}).get("realert_score_jump", alerts.get("realert_score_jump", 10))),
            cooloff_runs_after_alert=int(cooloff_after_alert),
            cooloff_runs_failed_breakout=int(cooloff_after_failed_bo),
            suppress_open_minutes=int(alerts.get("alerts", {}).get("suppress_open_minutes", 15)),
            suppress_close_minutes=int(alerts.get("alerts", {}).get("suppress_close_minutes", 5)),
            min_breadth_breakout=float(alerts.get("breadth", {}).get("pct_above_50dma_min", 35)),
            max_upper_circuit_hits=int(alerts.get("india_safety", {}).get("max_upper_circuit_hits_60d", 2)),
            tz_name=str(alerts.get("timezone", cfg.get("app", {}).get("timezone", "Asia/Kolkata"))),
            channels={
                "telegram": bool(channels.get("telegram", False)),
                "desktop": bool(channels.get("desktop", False)),
                "ntfy": bool(channels.get("ntfy", True)),
            },
        )


def _parse_run_meta(last_fired_run_id: Optional[str]) -> Tuple[Optional[str], Dict[str, Any]]:
    if not last_fired_run_id:
        return None, {}
    if "||" in last_fired_run_id:
        run_id, meta_json = last_fired_run_id.split("||", 1)
        try:
            meta = json.loads(meta_json)
        except json.JSONDecodeError:
            meta = {}
        return run_id or None, meta
    return last_fired_run_id, {}


def _format_run_meta(run_id: Optional[str], meta: Dict[str, Any]) -> Optional[str]:
    if run_id is None and not meta:
        return None
    return f"{run_id or ''}||{json.dumps(meta, separators=(',', ':'))}"


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _row_trading_day(row: Dict[str, Any], tz: ZoneInfo) -> Tuple[date, datetime]:
    dt = _parse_iso_datetime(row.get("as_of"))
    if dt is None:
        dt = datetime.now(timezone.utc)
    local_dt = dt.astimezone(tz)
    return local_dt.date(), local_dt


def _within_suppressed_window(local_dt: datetime, cfg: AlertsConfig) -> bool:
    suppress_start = time(9, 15)
    open_window_end = (datetime.combine(local_dt.date(), suppress_start, tzinfo=local_dt.tzinfo)
                       + timedelta(minutes=cfg.suppress_open_minutes)).time()
    close_window_start = time(15, 30 - cfg.suppress_close_minutes)
    current_time = local_dt.time()
    if suppress_start <= current_time < open_window_end:
        return True
    if current_time >= close_window_start:
        return True
    return False


def _breadth_allows_breakout(row: Dict[str, Any], cfg: AlertsConfig) -> bool:
    breadth = _f(row.get("breadth_pct_50dma"))
    if breadth is None:
        return True
    return breadth >= cfg.min_breadth_breakout


def _f(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def evaluate_momentum_crossups(*, run_id: Optional[str], settings: Dict[str, Any]) -> int:
    if not settings:
        settings = {}

    cfg = AlertsConfig.from_settings(settings)
    if not cfg.enabled:
        log.info("alerts_disabled")
        return 0

    repo_scores = ScoresRepo()
    items, *_ = repo_scores.read(run_id=run_id, as_of_str=None, filters=None, sort=None, page=1, per_page=10_000)
    if not items:
        log.info("alerts_no_rows")
        return 0

    tz = ZoneInfo(cfg.tz_name)
    run_dt = None
    if run_id:
        run_dt = _parse_iso_datetime(run_id_to_iso(run_id))
        if run_dt:
            run_dt = run_dt.astimezone(tz)

    fired = 0
    session_gen = get_session()
    session = next(session_gen)
    repo_alerts = AlertsRepo(session)
    now_utc = datetime.now(timezone.utc)

    try:
        for row in items:
            symbol = str(row.get("symbol") or "").upper()
            if not symbol:
                continue

            score_val = row.get("score")
            try:
                score = int(round(float(score_val)))
            except Exception:
                continue

            trading_day, local_dt = _row_trading_day(row, tz)
            if run_dt is not None:
                local_dt = run_dt
                trading_day = run_dt.date()
            if _within_suppressed_window(local_dt, cfg):
                continue

            market_time = local_dt.timetz() if hasattr(local_dt, "timetz") else local_dt.time()
            is_eod = False
            if market_time:
                try:
                    is_eod = (market_time.hour > 15) or (market_time.hour == 15 and market_time.minute >= 25)
                except Exception:
                    is_eod = False

            state = repo_alerts.get_state(symbol, RULE_CODE)
            prev_run_id, meta = _parse_run_meta(state.last_fired_run_id)
            passes = int(meta.get("passes", 0))
            cooloff = int(meta.get("cooloff", 0))
            last_action = meta.get("last_action")
            last_alert_score = meta.get("last_alert_score")

            gating_pass, action_code, reason_codes, debug_refs = _evaluate_candidate(row, score, cfg)

            if cooloff > 0:
                cooloff -= 1
                gating_pass = False

            if gating_pass:
                passes += 1
            else:
                passes = 0

            persistence_ok = (passes >= cfg.persistence_runs) or is_eod
            if not persistence_ok:
                _persist_state(repo_alerts, state, score, meta, passes, cooloff, last_action, last_alert_score, prev_run_id)
                continue

            if not gating_pass:
                _persist_state(repo_alerts, state, score, meta, passes, cooloff, last_action, last_alert_score, prev_run_id)
                continue

            same_day = state.last_fired_local_date == trading_day
            action_rank = ACTION_ORDER.get(action_code, 0)
            last_action_rank = ACTION_ORDER.get(last_action, 0)
            allow_realert = not same_day
            if same_day:
                upgrade = action_rank > last_action_rank
                jump = (last_alert_score is not None) and (score - int(last_alert_score) >= cfg.score_jump_realert)
                allow_realert = upgrade or jump

            if not allow_realert:
                _persist_state(repo_alerts, state, score, meta, passes, cooloff, last_action, last_alert_score, prev_run_id)
                continue

            channels_payload = {
                "reason_codes": reason_codes,
                "next_action": action_code,
                "score": score,
                "refs": debug_refs,
            }

            _send_notifications(symbol, score, action_code, run_id, cfg, channels_payload)

            fired += 1
            meta.update({
                "passes": 0,
                "cooloff": cfg.cooloff_runs_after_alert,
                "last_action": action_code,
                "last_alert_score": score,
            })
            repo_alerts.log_event(
                run_id=run_id or "",
                symbol=symbol,
                rule_code=RULE_CODE,
                score=score,
                channels_sent=channels_payload,
            )
            repo_alerts.upsert_state(
                symbol,
                RULE_CODE,
                last_score=score,
                last_fired_at_utc=now_utc,
                last_fired_local_date=trading_day,
                last_fired_run_id=_format_run_meta(run_id, meta),
            )

        session.commit()
    finally:
        try:
            session_gen.close()
        except Exception:
            pass
    return fired


def _evaluate_candidate(row: Dict[str, Any], score: int, cfg: AlertsConfig) -> Tuple[bool, str, List[str], Dict[str, Any]]:
    reason_codes: List[str] = []
    refs: Dict[str, Any] = {}

    if not global_pre_gates(row):
        return False, "NONE", ["gates:fail"], refs

    action = compute_next_action(price=row.get("last"), indicators=row, position={})
    action_code = action.get("code", "NONE")
    if action_code not in {"BUY_BREAKOUT", "BUY_PULLBACK", "BUY_STARTER"}:
        reason_codes.extend(action.get("reason_codes") or [])
        reason_codes.append(f"action:{action_code}")
        return False, action_code, reason_codes, refs

    reason_codes.extend(action.get("reason_codes") or [])
    regime = str(row.get("nifty_regime") or "").upper()
    min_score = cfg.min_score
    if regime == "DOWN":
        min_score = cfg.regime_down_min_score
        if cfg.block_starter_in_down and action_code == "BUY_STARTER":
            reason_codes.append("regime_block:starter")
            return False, action_code, reason_codes, refs
    if score < min_score:
        reason_codes.append(f"score<{min_score}")
        return False, action_code, reason_codes, refs

    if action_code == "BUY_BREAKOUT" and not _breadth_allows_breakout(row, cfg):
        reason_codes.append("breadth:weak")
        return False, action_code, reason_codes, refs

    recent_fail = bool(row.get("recent_failed_breakout_10d"))
    pivot_clear = _f(row.get("pivot_clear_pct"))
    if action_code == "BUY_BREAKOUT" and recent_fail and (pivot_clear is None or pivot_clear < 1.0):
        reason_codes.append("recent_fail_block")
        return False, action_code, reason_codes, refs

    asm_flags = row.get("asm_gsm_flags")
    if asm_flags:
        reason_codes.append("asm_gsm_block")
        return False, action_code, reason_codes, refs

    uc_hits = _f(row.get("upper_circuit_hits_60d"))
    if uc_hits is not None and uc_hits > cfg.max_upper_circuit_hits:
        reason_codes.append("uc_hits_block")
        return False, action_code, reason_codes, refs

    reason_codes.extend(row.get("reason_codes") or [])
    refs.update(action.get("refs") or {})
    refs["score"] = score
    return True, action_code, reason_codes, refs


def _persist_state(repo: AlertsRepo, state: AlertStateDTO, score: int, meta: Dict[str, Any], passes: int,
                   cooloff: int, last_action: Optional[str], last_alert_score: Optional[int],
                   prev_run_id: Optional[str]) -> None:
    meta.update({
        "passes": passes,
        "cooloff": cooloff,
        "last_action": last_action,
        "last_alert_score": last_alert_score,
    })
    repo.upsert_state(
        state.symbol,
        RULE_CODE,
        last_score=score,
        last_fired_at_utc=state.last_fired_at_utc,
        last_fired_local_date=state.last_fired_local_date,
        last_fired_run_id=_format_run_meta(prev_run_id, meta),
    )


def _send_notifications(symbol: str, score: int, action_code: str, run_id: Optional[str],
                        cfg: AlertsConfig, payload: Dict[str, Any]) -> None:
    title = f"{action_code}: {symbol}"
    body_lines = [
        f"Score: {score}",
        f"Action: {action_code}",
        f"Run: {run_id or 'latest'}",
        f"Reasons: {', '.join(payload.get('reason_codes', [])[:5])}",
    ]
    body = "\n".join(body_lines)

    channels_sent: Dict[str, Any] = {}
    if cfg.channels.get("ntfy", True):
        if os.getenv("NTFY_TOPIC"):
            ok = bool(notify_ntfy(title=title, body=body, tags="chart_with_upwards_trend"))
            channels_sent["ntfy"] = ok
        else:
            log.warning("ntfy_topic_missing", extra={"symbol": symbol})
            channels_sent["ntfy"] = False
    if cfg.channels.get("telegram", False) or cfg.channels.get("desktop", False):
        notify_tg_toast(
            title=title,
            body=body,
            severity="success",
            dedupe_tag=f"alert:{symbol}:{action_code}",
            enable_telegram=cfg.channels.get("telegram", False),
            enable_desktop=cfg.channels.get("desktop", False),
        )
        channels_sent["telegram"] = cfg.channels.get("telegram", False)
        channels_sent["desktop"] = cfg.channels.get("desktop", False)
    payload["channels_sent"] = channels_sent


def run_id_to_iso(run_id: str) -> str:
    if "T" in run_id:
        if run_id.endswith("Z"):
            return run_id
        return f"{run_id}Z"
    # assume YYYYMMDDHHMMSS
    if len(run_id) >= 14:
        return f"{run_id[0:4]}-{run_id[4:6]}-{run_id[6:8]}T{run_id[8:10]}:{run_id[10:12]}:{run_id[12:14]}Z"
    return f"{run_id}Z"


# Lazily import DB session generator to avoid circular import
def get_session():
    from app.core.db import get_session as _get_session

    return _get_session()


__all__ = ["evaluate_momentum_crossups"]
