
# backend/app/services/alerts.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, Iterable, Optional
import logging
import os

from app.repos.sql.alerts_repo import AlertsRepo
from app.repos.sql.alerts_repo import AlertState as AlertStateDTO
from app.repos.parquet.scores_repo import ScoresRepo
from app.notifs.telegram_toast import notify as notify_tg_toast
from app.notifs.ntfy import notify as notify_ntfy

log = logging.getLogger(__name__)

try:
    from app.core.db import get_session
except Exception:
    get_session = None

RULE_MOMENTUM_GTE = "momentum_score_gte"


@dataclass
class AlertsConfig:
    enabled: bool = True
    threshold_raw: float = 800.0
    repeat_policy: str = "once_per_day"
    throttle_min_minutes: int = 60
    tz_name: str = "Asia/Singapore"
    channels: Dict[str, bool] = None  # kept as-is

    @staticmethod
    def from_settings(cfg: Dict[str, Any]) -> "AlertsConfig":
        alerts = cfg.get("alerts", {}) if cfg else {}
        rules = alerts.get("rules", alerts)
        rule = rules.get(RULE_MOMENTUM_GTE, rules.get("momentum_score_gte", {}))

        thr = None
        rep = "once_per_day"
        if isinstance(rule, dict):
            thr = rule.get("threshold", rule.get("value", rule.get("threshold_raw")))
            rep = rule.get("repeat_policy", rep)
        else:
            thr = rule

        if thr is None:
            thr = 800
        if isinstance(thr, str):
            try:
                thr = float(thr.strip())
            except Exception:
                thr = 800.0
        thr = float(thr)

        # Normalize: allow 800 -> 80, but accept 70/80 directly too
        normalized = thr / 10.0 if thr >= 100 else thr

        channels = alerts.get("channels", {})
        return AlertsConfig(
            enabled=bool(alerts.get("enabled", True)),
            threshold_raw=normalized,
            repeat_policy=rep,
            throttle_min_minutes=int(alerts.get("throttle", {}).get("min_minutes_between", 60)),
            tz_name=cfg.get("app", {}).get("timezone", alerts.get("timezone", "Asia/Singapore")),
            channels={
                "telegram": bool(channels.get("telegram", False)),  # default off
                "desktop":  bool(channels.get("desktop",  False)),  # default off
                "ntfy":     bool(channels.get("ntfy",     True)),   # default ON
            },
        )


def _iter_scores_for_run(run_id: Optional[str]) -> Iterable[Dict[str, Any]]:
    """Fetch all scored rows for a given run (pagination-friendly signature)."""
    repo = ScoresRepo()
    ymd = f"{run_id[:4]}-{run_id[4:6]}-{run_id[6:8]}" 
    items, *_ = repo.read(
        run_id=None,
        as_of_str=ymd,
        filters=None,
        sort=None,
        page=1,
        per_page=10_000,  # NOTE: repo expects per_page (not page_size)
    )
    # enable this log to see how many rows were loaded from Parquet
    #log.info("_iter_scores_for_run items=%s", items)
    return items


def evaluate_momentum_crossups(run_id: Optional[str], settings: Dict[str, Any]) -> int:
    run_short = (run_id or "")[:14]
    log.info("evaluate_momentum_crossups run_id=%s", run_short, extra={"run_id": run_short})
    cfg = AlertsConfig.from_settings(settings)
    if not cfg.enabled:
        return 0

    # Pull ntfy config from YAML and expose as env (so app.notifs.ntfy can read it)
    ntfy_cfg = (settings.get("alerts", {}) or {}).get("ntfy", {}) if isinstance(settings, dict) else {}
    if isinstance(ntfy_cfg, dict):
        os.environ.setdefault("NTFY_SERVER", str(ntfy_cfg.get("server", "")))
        os.environ.setdefault("NTFY_TOPIC",  str(ntfy_cfg.get("topic",  "")))
        os.environ.setdefault("NTFY_TOKEN",  str(ntfy_cfg.get("token",  "")))

    threshold = cfg.threshold_raw
    tz = ZoneInfo(cfg.tz_name or "Asia/Singapore")
    now_utc = datetime.now(timezone.utc)
    local_day = now_utc.astimezone(tz).date()

    items = list(_iter_scores_for_run(run_id))

    # ---- Diagnostics: how many rows would qualify on pure threshold (independent of cross-up/state)
    def _num(v):
        try:
            return float(v)
        except Exception:
            return float("nan")
    ge_cnt = sum(1 for r in items if _num(r.get("score")) >= threshold)
    try:
        max_score = max((_num(r.get("score")) for r in items), default=float("nan"))
    except Exception:
        max_score = float("nan")
    log.info("alerts_threshold_diagnostics max_score=%s", max_score,extra={
        "run_id": run_short, "loaded": len(items), "threshold": threshold,
        "ge_threshold_count": ge_cnt, "max_score": (None if max_score != max_score else max_score),
    })

    if not items:
        return 0

    if not get_session:
        raise RuntimeError("get_session() not available")

    fired = 0

    # Borrow a Session from the FastAPI generator (same approach as scheduler)
    gen = get_session()
    s = next(gen)
    try:
        repo = AlertsRepo(s)

        for row in items:
            symbol = str(row.get("symbol") or row.get("Symbol") or "").upper()
            if not symbol:
                continue

            score_val = row.get("score") or row.get("score_total_0_100") or row.get("Score")
            try:
                score = int(round(float(score_val)))
            except Exception:
                continue

            state: AlertStateDTO = repo.get_state(symbol, RULE_MOMENTUM_GTE)
            prev = state.last_score if state.last_score is not None else 0

            crossed_up = (prev < threshold) and (score >= threshold)
            '''
            if not crossed_up:
                # Persist last_score so future crosses evaluate correctly
                repo.upsert_state(
                    symbol,
                    RULE_MOMENTUM_GTE,
                    last_score=score,
                    last_fired_at_utc=state.last_fired_at_utc,
                    last_fired_local_date=state.last_fired_local_date,
                    last_fired_run_id=state.last_fired_run_id,
                )
                continue

            '''
            # MINIMAL FIX: only alert if today's score meets the threshold
            if score < threshold:
                repo.upsert_state(
                    symbol,
                    RULE_MOMENTUM_GTE,
                    last_score=score,
                    last_fired_at_utc=state.last_fired_at_utc,
                    last_fired_local_date=state.last_fired_local_date,
                    last_fired_run_id=state.last_fired_run_id,
                )
                continue
            # Once-per-day guard
            if state.last_fired_local_date == local_day:
                repo.upsert_state(
                    symbol,
                    RULE_MOMENTUM_GTE,
                    last_score=score,
                    last_fired_at_utc=state.last_fired_at_utc,
                    last_fired_local_date=state.last_fired_local_date,
                    last_fired_run_id=state.last_fired_run_id,
                )
                continue

            # Build notification body
            title = f"Momentum >={int(threshold)}: {symbol}"
            price = row.get("last") or row.get("close") or row.get("price")
            run_str = run_short
            body_lines = [
                f"Score: {score}",
                f"Last: {price:.2f}" if isinstance(price, (float, int)) else f"Last: {price}",
                f"Run: {run_str}",
                f"Crossed up from {prev} -> {score}",
            ]
            body = "\n".join([l for l in body_lines if l])

            # Send notifications and record truthfully
            channels_sent: Dict[str, Any] = {}
            try:
                # NTFY (warn loudly if topic missing)
                if cfg.channels.get("ntfy", True):
                    log.info("ntfy about to send", extra={"symbol": symbol, "run_id": run_str, "title": title})
                    if not os.getenv("NTFY_TOPIC"):
                        log.warning(
                            "ntfy disabled: NTFY_TOPIC not set; skipping send",
                            extra={"symbol": symbol, "run_id": run_str},
                        )
                        channels_sent["ntfy"] = False
                    else:
                        ok = bool(notify_ntfy(title=title, body=body, tags="chart_with_upwards_trend,rocket"))
                        channels_sent["ntfy"] = ok

                # Telegram/Desktop toast (optional)
                if cfg.channels.get("telegram", False) or cfg.channels.get("desktop", False):
                    notify_tg_toast(
                        title=title,
                        body=body,
                        severity="success",
                        dedupe_tag=f"mom80:{symbol}:{local_day.isoformat()}",
                        enable_telegram=cfg.channels.get("telegram", False),
                        enable_desktop=cfg.channels.get("desktop", False),
                    )
                    channels_sent["telegram"] = cfg.channels.get("telegram", False)
                    channels_sent["desktop"] = cfg.channels.get("desktop", False)

            except Exception as e:
                # Capture any send errors in the event record
                channels_sent = {"error": str(e)}
                log.exception("alert send failed", extra={"symbol": symbol, "run_id": run_str})

            # Persist event + update state
            repo.log_event(
                run_id=run_id or "",
                symbol=symbol,
                rule_code=RULE_MOMENTUM_GTE,
                score=score,
                channels_sent=channels_sent,
            )
            repo.upsert_state(
                symbol,
                RULE_MOMENTUM_GTE,
                last_score=score,
                last_fired_at_utc=now_utc,
                last_fired_local_date=local_day,
                last_fired_run_id=run_id,
            )
            fired += 1
        s.commit()
    finally:
        try:
            gen.close()
        except Exception:
            pass

    # FIXED: proper final log (remove stray %s placeholders)
    log.info("alerts evaluated", extra={"run_id": run_short, "fired": fired, "threshold": threshold, "loaded": len(items)})
    return fired
