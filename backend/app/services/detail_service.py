# backend/app/services/detail_service.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, List
from datetime import datetime, date
from zoneinfo import ZoneInfo

try:
    from app.core.config import load as load_settings
except Exception:  # pragma: no cover
    load_settings = None  # type: ignore

from app.domain.rules.next_action import euphoria_thresholds

log = logging.getLogger("app.services.detail")

def _settings():
    if load_settings is None:  # pragma: no cover
        return None
    try:
        return load_settings()
    except Exception:
        return None


def _rules_cfg():
    settings = _settings()
    if settings is None:  # pragma: no cover
        return None
    try:
        return settings.rules
    except Exception:
        return None

def _right_drawer_news_hours() -> int:
    default_hours = 168  # one week
    settings = _settings()
    if not settings:
        return default_hours
    try:
        features = getattr(settings, "features", {}) or {}
        if isinstance(features, dict):
            news_cfg = features.get("news") or {}
            if isinstance(news_cfg, dict):
                ui_cfg = news_cfg.get("ui") or {}
                if isinstance(ui_cfg, dict):
                    hours = ui_cfg.get("right_drawer_hours") or ui_cfg.get("drawer_hours")
                    if hours is not None:
                        try:
                            val = int(hours)
                            if val > 0:
                                return val
                        except Exception:
                            log.debug("detail.news_hours_invalid", extra={"value": hours})
    except Exception:
        log.exception("detail.news_hours_cfg_error")
    return default_hours


def _app_timezone_default() -> str:
    settings = _settings()
    if settings and getattr(settings.app, "timezone", None):
        return settings.app.timezone
    return "Asia/Singapore"


def _atr_init_default() -> float:
    rules = _rules_cfg()
    if rules and getattr(rules, "atr_init_mult", None) is not None:
        try:
            return float(rules.atr_init_mult)
        except Exception:
            return 2.0
    return 2.0


# --- Minimal stop helpers (additive; safe) ---
def _atrxk_stop(entry: Optional[float], atr_pct: Optional[float], k: float) -> Optional[float]:
    """Compute ATR×K stop only when entry & ATR% exist; return None otherwise."""
    try:
        if entry is None or float(entry) <= 0: return None
        if atr_pct is None or float(atr_pct) <= 0: return None
        stop_val = float(entry) - float(entry) * (float(atr_pct) / 100.0) * float(k)
        return round(stop_val, 2)
    except Exception:
        log.exception("atrxk_stop: failed entry=%s atr_pct=%s k=%s", entry, atr_pct, k)
        return None

def _ratchet_stop(prev: Optional[float], now: Optional[float]) -> Optional[float]:
    """Never decrease stop; prefer the higher of (prev, now)."""
    try:
        if prev is None: return now
        if now is None: return prev
        return max(float(prev), float(now))
    except Exception:
        log.exception("ratchet_stop: failed prev=%s now=%s", prev, now)
        return now or prev
    
_TZ_DEFAULT = _app_timezone_default()

def _as_of_from_run_id(run_id: str, tz_name: str = _TZ_DEFAULT) -> datetime:
    """Parse 'YYYYMMDDHHMMSS' run_id to tz-aware datetime; fallback to now."""
    try:
        dt = datetime.strptime((run_id or "")[:14], "%Y%m%d%H%M%S")
    except Exception:
        return datetime.now(ZoneInfo(tz_name))
    return dt.replace(tzinfo=ZoneInfo(tz_name))

def _coerce_as_of(value, *, run_id: Optional[str], tz_name: str = _TZ_DEFAULT) -> datetime:
    """
    Accepts datetime/date/str/None and returns a tz-aware datetime.
    - date -> midnight local tz
    - 'YYYY-MM-DD' -> midnight local tz
    - naive datetime -> attach local tz
    - aware datetime -> return as-is
    - None/'' -> derive from run_id (if provided) else 'now'
    """
    if value in (None, "", " "):
        if run_id:
            return _as_of_from_run_id(run_id, tz_name)
        return datetime.now(ZoneInfo(tz_name))

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=ZoneInfo(tz_name))

    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=ZoneInfo(tz_name))

    s = str(value).strip()
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=ZoneInfo(tz_name))
    except Exception:
        pass

    try:
        d = datetime.strptime(s, "%Y-%m-%d").date()
        return datetime(d.year, d.month, d.day, tzinfo=ZoneInfo(tz_name))
    except Exception:
        pass

    # Last resort
    return _as_of_from_run_id(run_id or "", tz_name)


# Optional external rule engine (kept)
try:
    # The rules module exposes compute_next_action (not resolve_next_action)
    from app.domain.rules.next_action import compute_next_action as _rules_resolve_next_action
    _HAVE_RULES = True
    _rules_compute_meters = None  # rules module doesn't provide meters; keep symbol for compatibility
except Exception:  # pragma: no cover
    _HAVE_RULES = False
    _rules_compute_meters = None
    _rules_resolve_next_action = None


# Prefer domain implementations
try:
    from app.domain.meters import compute_meters as _domain_compute_meters
except Exception:
    _domain_compute_meters = None

try:
    from app.domain.rules.next_action import compute_next_action as _domain_compute_next
except Exception:
    _domain_compute_next = None


@dataclass
class DetailDeps:
    scores_repo: Any
    indicators_repo: Any | None
    positions_repo: Any | None
    snapshot_pins_repo: Any | None


def _resolve_run_id(symbol: str, run_id: Optional[str], deps: DetailDeps) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve a run context **without any legacy fallback**:
      1) Use pinned run_id if available.
      2) Else use repo.latest_run() (which prefers intraday(today) → daily(≤today)).
    Returns (run_id, as_of). For daily snapshots, run_id may be None and as_of non-empty.
    """
    rid = (run_id or "").strip() or None
    as_of: Optional[str] = None

    # 1) Pin (if present)
    if not rid and deps.snapshot_pins_repo:
        try:
            row = None
            for meth in ("get_pinned_run_id", "get_pin", "get"):
                if hasattr(deps.snapshot_pins_repo, meth):
                    row = getattr(deps.snapshot_pins_repo, meth)(symbol)
                    break
            if isinstance(row, str):
                rid = row
            elif isinstance(row, dict):
                rid = row.get("pinned_run_id") or row.get("run_id")
            elif row is not None and hasattr(row, "pinned_run_id"):
                rid = getattr(row, "pinned_run_id")
            if rid:
                log.info("resolve_run_id: pin HIT for %s → %s", symbol, rid)
        except Exception:
            log.exception("resolve_run_id: pin lookup failed for %s", symbol)

    # 2) Latest new-layout snapshot (intraday → daily)
    if not rid and deps.scores_repo and hasattr(deps.scores_repo, "latest_run"):
        try:
            rid2, as_of2 = deps.scores_repo.latest_run()
            rid = rid or rid2
            as_of = as_of2 or as_of
            log.info("resolve_run_id: latest_run() → run_id=%s as_of=%s", rid, as_of)
        except Exception:
            log.exception("resolve_run_id: latest_run() failed")

    log.info("resolve_run_id: final symbol=%s → rid=%s as_of=%s", symbol, rid, as_of)
    if not rid and not as_of:
        return None, None
    return rid, as_of

def _compute_entry_suggestion(
    *,
    price_now: float,
    ema_fast_n: int,
    ema_fast_val: Optional[float],
    ema_slow_n: int,
    ema_slow_val: Optional[float],
    rsi14: float,
    adx14: float,
    relvol20: float,   # kept for future use / logging parity
    prox52: float,
    atr_abs: float,
) -> Dict[str, Any]:
    """
    Simple, explainable entry suggestion used by the drawer when there's no locked entry.
    Returns a dict: {type, price, low, high, reason}
    """

    def _num_pos(x: Any) -> Optional[float]:
        """Return positive float or None."""
        try:
            v = float(x)
            return v if v > 0 else None
        except Exception:
            return None

    slow = _num_pos(ema_slow_val)   # may be None when not available
    fast = _num_pos(ema_fast_val)   # may be None when not available

    def strong_momo() -> bool:
        # bullish momentum OR very close to 52w high
        return (float(rsi14) >= 60 and float(adx14) >= 25) or (float(prox52) >= -1.0)

    def extended() -> bool:
        # % distance above slow EMA (only when we actually have slow)
        if slow is None:
            return False
        gap_pct = (price_now - slow) / slow * 100.0
        return gap_pct >= 3.0

    # 1) Breakout / Pullback logic
    # If slow is missing, treat the condition as satisfied for the purpose of suggesting momentum entries.
    if strong_momo() and (slow is None or price_now >= slow):
        if not extended():
            return {
                "type": "BREAKOUT",
                "price": float(price_now),
                "low": None,
                "high": None,
                "reason": f"Price ≥ EMA{ema_slow_n} and near 52W high / strong momentum" if slow is not None
                          else "Strong momentum / near 52W high (slow EMA unavailable)",
            }
        # extended → prefer pullback toward fast EMA band (fallback to price_now if fast missing)
        hi = float(fast if fast is not None else price_now)
        if atr_abs and fast is not None:
            lo = float(max(fast - 0.5 * atr_abs, 0.0))
        elif atr_abs:
            lo = float(max(price_now - 0.5 * atr_abs, 0.0))
        else:
            base = fast if fast is not None else price_now
            lo = float(base * 0.995)
        px = float(min(price_now, hi))
        return {
            "type": "PULLBACK",
            "price": px,
            "low": lo,
            "high": hi,
            "reason": f"Extended; prefer pullback to EMA{ema_fast_n}" if fast is not None
                      else "Extended; prefer pullback toward rising band",
        }

    # 2) Starter position if momentum is brewing and price is not far below slow EMA
    # If slow is missing, allow starter when momentum ok.
    if float(rsi14) >= 55 and float(adx14) >= 20 and (slow is None or price_now >= slow * 0.99):
        # Prefer current price for a starter; anchor remain “near EMA{n}” in the copy
        starter = float(price_now)
        return {
            "type": "STARTER",
            "price": starter,
            "low": None,
            "high": None,
            "reason": f"Momentum building; starter near EMA{ema_slow_n}" if slow is not None
                      else "Momentum building; starter (slow EMA unavailable)",
        }

    # 3) Default
    return {
        "type": "WATCH",
        "price": float(price_now) if price_now else 0.0,
        "low": None,
        "high": None,
        "reason": "No clear entry; watch only",
    }

# ---------- Helpers ----------

def _header_badges_from_row(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Map legacy parquet badges (code/text) to new header.Badge {category,label}.
    """
    out: List[Dict[str, Any]] = []
    badges = row.get("badges") or []
    for b in badges:
        code = (b or {}).get("code") or ""
        text = (b or {}).get("text") or ""
        category = None
        c = code.upper()
        if c in ("VERY_HIGH_BREAKOUT", "NEW_HIGH", "BREAKOUT", "HIGH_BREAKOUT"):
            category = "BREAKOUT"
        elif c in ("HIGH_MOMENTUM", "MOMENTUM"):
            category = "MOMENTUM"
        elif c in ("WATCH", "DATA_INCOMPLETE", "WATCH_INCOMPLETE"):
            category = "WATCH"
        elif c in ("IGNORE",):
            category = "IGNORE"
        # fallback by text
        if category is None:
            t = text.lower()
            if "breakout" in t or "new 52w" in t:
                category = "BREAKOUT"
            elif "momentum" in t:
                category = "MOMENTUM"
            elif "watch" in t:
                category = "WATCH"
        if category:
            out.append({"category": category, "label": text or code})
    return out

def _compute_meters_and_next(price_now: Optional[float], ind: Dict[str, Any], pos: Dict[str, Any]):
    # Prefer domain meters if available; else rules (if provided); else legacy
    meters = None
    if _domain_compute_meters:
        try:
            meters = _domain_compute_meters(indicators=ind, score_row={"atr14_pct": ind.get("atr14_pct"), "atr_pct": ind.get("atr14_pct")})
            log.info("meters: domain-computed")
        except Exception:
            log.exception("meters: domain failed; will fallback")
            meters = None
    if meters is None and _rules_compute_meters:
        try:
            meters = _rules_compute_meters(price_now, ind, pos)  # compatibility if you ever add it
            log.info("meters: rules-computed")
        except Exception:
            log.exception("meters: rules failed; will fallback")
            meters = None
    if meters is None:
        # Legacy meters (kept intact)
        def _risk(x):
            x = float(x) if x is not None else None
            if x is None: return "Medium"
            if x < 1.2:   return "Low"
            if x < 1.8:   return "Medium"
            return "High"
        def _euph(rsi, adx):
            r = float(rsi or 0); a = float(adx or 0); s = r + 0.5 * a
            if s < 70: return "Low"
            if s < 90: return "Medium"
            return "High"
        meters = {
            "risk": {"level": _risk(ind.get("atr14_pct")), "basis": {"atr_pct": float(ind.get("atr14_pct") or 0.0)}},
            "euphoria": {"level": _euph(ind.get("rsi14"), ind.get("adx14")),
                         "basis": {"rsi14": float(ind.get("rsi14") or 0.0), "adx14": float(ind.get("adx14") or 0.0)}},
        }
        log.info("meters: legacy-computed")

    # Compute next_action independently: prefer domain next → rules next → legacy
    next_action = None
    if _domain_compute_next:
        try:
            next_action = _domain_compute_next(price=price_now, indicators=ind, position=pos)
            log.info("next: domain-computed code=%s", (next_action or {}).get("code"))
        except Exception:
            log.exception("next: domain failed; will try rules/legacy")
            next_action = None

    if next_action is None and _HAVE_RULES and _rules_resolve_next_action:
        try:
            next_action = _rules_resolve_next_action(price=price_now, indicators=ind, position=pos)
            log.info("next: rules-computed code=%s", (next_action or {}).get("code"))
        except Exception:
            log.exception("next: rules failed; will use legacy")
            next_action = None

    if next_action is None:
        # Legacy fallback (kept)
        ema_n = int(ind.get("ema_slow") or ind.get("ema_fast") or 10)
        ema_val = float(ind.get("ema_slow_value") or ind.get("ema_fast_value") or (price_now or 0.0))
        if price_now is not None and ema_val and price_now >= ema_val:
            stop_now = pos.get("stop_now") or 0.0
            if stop_now:
                next_action = {"code": "HOLD", "text": f"Hold (trail stop at ₹{float(stop_now):,.1f})",
                               "reasons": [f"Close ≥ EMA{ema_n}", "Momentum intact"],
                               "refs": {"stop_now": float(stop_now), "ema_n": int(ema_n), "ema_value": float(ema_val)}}
            else:
                next_action = {"code": "HOLD", "text": f"Hold (above EMA{ema_n})",
                               "reasons": [f"Close ≥ EMA{ema_n}"],
                               "refs": {"ema_n": int(ema_n), "ema_value": float(ema_val)}}
        else:
            next_action = {"code": "WATCH", "text": "Watch (no clear signal)", "reasons": [],
                           "refs": {"ema_n": int(ema_n), "ema_value": float(ema_val)}}
        log.info("next: legacy-computed code=%s", next_action.get("code"))

    return meters, next_action




def build_drawer_detail(symbol: str, run_id: str | None, deps: DetailDeps, *, as_of: str | None = None) -> Dict[str, Any]:
    """
    Build drawer detail using **new parquet layout**:
      - If run_id is provided → try intraday at that run_id for the symbol; if not found, fall back to daily (date from run_id).
      - Else if as_of is provided → read that exact DAILY snapshot for the symbol.
      - Else → rely on repo resolver (EOD(today) > Intraday(today) > EOD(≤today)).
    """
    sym_in = (symbol or "").upper()
    # Read one row using the repo, filtered by symbol, honoring explicit hints first.
    row, canon, rid_used, as_of_used = _read_row_new_layout(
        deps.scores_repo,
        sym_in,
        run_id_hint=run_id,
        as_of_hint=as_of,
    )

    log.info(
        "build: symbol=%s canon=%s req_run_id=%s req_as_of=%s kind=%s resolved_run_id=%s resolved_as_of=%s has_row=%s",
        sym_in, canon, run_id, as_of,
        ("intraday" if rid_used else ("daily" if as_of_used else "none")),
        rid_used, as_of_used, bool(row)
    )
    if row:
        log.info("build: row keys: %s", sorted(list(row.keys())))

    # --- snapshot ---
    price_now = _f((row or {}).get("last"))
    name_snapshot = (row or {}).get("name")
    sector_snapshot = (row or {}).get("sector")
    name = name_snapshot if name_snapshot not in (None, "") else sym_in
    sector = sector_snapshot if sector_snapshot is not None else ""
    # Prefer the row's as_of; else the repo-resolved as_of; else None (fixed below)
    as_of_val = (row or {}).get("as_of") or as_of_used or ""
    pct_today = _f((row or {}).get("pct_today") or (row or {}).get("change_pct"))
    score_raw = (row or {}).get("score")
    score = score_raw if isinstance(score_raw, int) else _f(score_raw)

    trading_day = _derive_trading_day(as_of_val)

    # --- EMAs ---
    ema_map = _extract_ema_periods(row or {})
    fast_n, slow_n = _pick_fast_slow_periods(ema_map)
    fast_val = ema_map.get(fast_n, price_now)
    slow_val = ema_map.get(slow_n, price_now)

    indicators: Dict[str, Any] = {
        "rsi14": _f((row or {}).get("rsi14") or (row or {}).get("rsi")),
        "adx14": _f((row or {}).get("adx14") or (row or {}).get("adx")),
        "adx_slope_5": _f((row or {}).get("adx_slope_5") or (row or {}).get("adx_slope") or 0.0),
        "ema_fast": int(fast_n),
        "ema_fast_value": _f(fast_val),
        "ema_slow": int(slow_n),
        "ema_slow_value": _f(slow_val),
        "relvol20": _f((row or {}).get("relvol20")),
        "proximity_52w_high_pct": _f((row or {}).get("proximity_52w_high_pct") or (row or {}).get("pct_from_52w_high")),
        "ema10": _f((row or {}).get("ema10") or (slow_val if slow_n == 10 else 0.0)),
        "ema8": _f((row or {}).get("ema8") or (fast_val if fast_n == 8 else 0.0)),
        "atr14_pct": _f((row or {}).get("atr14_pct") or (row or {}).get("atr_pct")),
        "atr10_pct": _f((row or {}).get("atr10_pct")),
        "gap_up_pct": _f((row or {}).get("gap_up_pct")),
        "close_pos_in_bar": _f((row or {}).get("close_pos_in_bar")),
        "pivot_20d": _f((row or {}).get("pivot_20d")),
        "pivot_clear_pct": _f((row or {}).get("pivot_clear_pct")),
        "base_len_bars": _i((row or {}).get("base_len_bars")),
    }
    try:
        indicators["score"] = float(score) if score is not None else None
    except Exception:
        indicators["score"] = None

    # 👉 Normalize EMA placeholders: never keep zeros
    if indicators.get("ema8") == 0.0:
        indicators["ema8"] = None
    if indicators.get("ema10") == 0.0:
        indicators["ema10"] = None
    if indicators.get("ema_fast_value") == 0.0:
        indicators["ema_fast_value"] = None
    if indicators.get("ema_slow_value") == 0.0:
        indicators["ema_slow_value"] = None
    atr_pct = indicators["atr14_pct"]
    atr_abs = price_now * (atr_pct / 100.0) if atr_pct else 0.0

    # --- positions (unchanged behavior) ---
    position: Dict[str, Any] = {
        "entry_price": 0.0,
        "entry_price_locked": 0.0,
        "qty": 0,
        "trade_on": False,
        "sell_price": None,
        "sold_at": None,
        "realized_pl": None,
        "realized_pl_pct": None,
        "stop_now": 0.0,
        "exit_close_threshold": 0.0,
        "breakeven_active": False,
        "euphoria_on": False,
        "note": "",
    }

    pos = None
    if deps.positions_repo:
        tried = _position_symbol_candidates(canon or sym_in)
        log.info("build: positions lookup keys tried: %s", tried)
        for key in tried:
            try:
                pos = deps.positions_repo.get(key)
            except Exception:
                pos = None
            if pos:
                log.info("build: positions HIT via key=%s", key)
                break
        if not pos:
            log.info("build: positions MISS for %s", sym_in)

    if pos:
        g = (lambda k: pos.get(k) if isinstance(pos, dict) else getattr(pos, k, None))
        entry_locked = _f(g("entry_price_locked"))
        entry = g("entry_price")
        position.update({
            "entry_price": _f(entry if entry is not None and entry != 0 else entry_locked),
            "entry_price_locked": entry_locked,
            "qty": _i(g("qty")),
            "trade_on": bool(g("trade_on")) if g("trade_on") is not None else False,
            "sell_price": _f(g("sell_price")),
            "sold_at": g("sold_at"),
            "realized_pl": _f(g("realized_pl")),
            "realized_pl_pct": _f(g("realized_pl_pct")),
            "stop_now": _f(g("stop_now")),
            "exit_close_threshold": _f(g("exit_close_threshold")),
            "breakeven_active": bool(g("breakeven_active")) if g("breakeven_active") is not None else False,
            "euphoria_on": bool(g("euphoria_on")) if g("euphoria_on") is not None else False,
            "note": g("note") if g("note") is not None else "",
        })

    # --- entry suggestion ---
    needs_suggestion = (position["entry_price"] == 0.0 and position["entry_price_locked"] == 0.0)
    entry_suggestion = _compute_entry_suggestion(
        price_now=price_now,
        ema_fast_n=indicators["ema_fast"],
        ema_fast_val=indicators["ema_fast_value"],
        ema_slow_n=indicators["ema_slow"],
        ema_slow_val=indicators["ema_slow_value"],
        rsi14=indicators["rsi14"],
        adx14=indicators["adx14"],
        relvol20=indicators["relvol20"],
        prox52=indicators["proximity_52w_high_pct"],
        atr_abs=atr_abs,
    )
    log.info("build: entry_suggestion=%s", entry_suggestion)

    # --- stop computation (minimal additive; do not remove existing fields) ---
    default_k = _atr_init_default()
    try:
        k = float(position.get("k")) if position.get("k") is not None else default_k
    except Exception:
        k = default_k

    entry_locked_val = position.get("entry_price_locked") or None
    entry_locked_val = entry_locked_val if entry_locked_val and entry_locked_val > 0 else None

    prev_stop = position.get("stop_now") or None
    prev_stop = prev_stop if prev_stop and prev_stop > 0 else None

    computed_stop = _atrxk_stop(entry_locked_val, indicators.get("atr14_pct"), k)
    stop_final = _ratchet_stop(prev_stop, computed_stop) if entry_locked_val else None

    if entry_locked_val and computed_stop is not None:
        log.info("stop: computed ATRxK entry=%s atr_pct=%s k=%s -> calc=%s prev=%s final=%s",
                entry_locked_val, indicators.get("atr14_pct"), k, computed_stop, prev_stop, stop_final)
    else:
        log.info("stop: not computed (entry_locked=%s atr_pct=%s)", entry_locked_val, indicators.get("atr14_pct"))

    # Update position for downstream next_action / action_block
    position["stop_now"] = stop_final
    position["stop_method"] = "ATRxK" if stop_final is not None else None

    if needs_suggestion and entry_suggestion.get("price"):
        position["entry_price"] = float(entry_suggestion["price"])

    # ✅ Normalize entry lock to None when not set (prevents false in-position in resolver)
    position["entry_price_locked"] = entry_locked_val  # <-- minimal, critical fix

    # ---------- EOD flag so SELL_TOMORROW can trigger on daily snapshots ----------
    row_is_eod = bool((row or {}).get("is_eod"))
    if not row_is_eod:
        _asu = as_of_used if isinstance(as_of_used, str) else ""
        if not _asu:
            _asu = (row or {}).get("as_of") if isinstance((row or {}).get("as_of"), str) else ""
        row_is_eod = bool(_asu) and ("T" not in _asu) and (len(_asu) == 10)
    indicators["is_eod"] = row_is_eod
    indicators["market_closed"] = row_is_eod

    # --- meters + next action (unchanged) ---
    meters, next_action = _compute_meters_and_next(price_now, indicators, position)
    meters = _normalize_meters_to_contract(meters, indicators)

    valid_codes = {
        "SELL_NOW",
        "SELL_TOMORROW",
        "HOLD",
        "HOLD_BREAKEVEN",
        "HOLD_TIGHT",
        "BUY_BREAKOUT",
        "BUY_PULLBACK",
        "BUY_STARTER",
        "WATCH",
        "IGNORE",
    }

    if isinstance(next_action, dict):
        code = (next_action.get("code") or "").upper()
        if code not in valid_codes:
            log.warning("next: invalid code '%s' -> coercing to WATCH", code)
            code = "WATCH"
            next_action["code"] = code
            if not next_action.get("text"):
                next_action["text"] = "Watch (no clear signal)"
        else:
            next_action["code"] = code
        refs_in = next_action.get("refs") or {}
        numeric_refs = {k: float(v) for k, v in refs_in.items() if _is_number(v)}
        # Only attach entry bands/suggestion for pullback or starter
        if code in ("BUY_PULLBACK", "BUY_STARTER") and entry_suggestion:
            for k in ("price", "low", "high"):
                v = entry_suggestion.get(k)
                if _is_number(v):
                    key = "entry_suggested" if k == "price" else f"entry_{k}"
                    numeric_refs[key] = float(v)
        # For BREAKOUT: keep it crisp → ensure pivot 'level', drop pullback bands if any
        if code == "BUY_BREAKOUT":
            for k in ("entry_suggested", "entry_low", "entry_high"):
                numeric_refs.pop(k, None)
            if "level" not in numeric_refs and _is_number(indicators.get("pivot_20d")):
                numeric_refs["level"] = float(indicators["pivot_20d"])
        # For WATCH: strip any accidental entry refs
        if code == "WATCH":
            for k in ("entry_suggested", "entry_low", "entry_high"):
                numeric_refs.pop(k, None)
        next_action["refs"] = numeric_refs

    # --- euphoria from indicators → affects method pill & exits (even pre-entry, informational) ---
    thresholds = euphoria_thresholds()
    try:
        _rsi = float(indicators.get("rsi14") or 0.0)
        _adx = float(indicators.get("adx14") or 0.0)
        _slope = float(indicators.get("adx_slope_5") or 0.0)
        eup_on = (_rsi >= thresholds["rsi_min"] and _adx >= thresholds["adx_min"]) or (
            _rsi >= thresholds["alt_rsi_min"] and _adx >= thresholds["alt_adx_min"] and _slope > thresholds["adx_slope5_min"]
        )
    except Exception:
        eup_on = False
    method_pill = "EMA8" if eup_on else (f"EMA{int(indicators['ema_slow'])}" if indicators["ema_slow"] else "EMA")

    # --- header/sparkline (unchanged) ---
    header = {
        "name": name,
        "sector": sector or None,
        "price": price_now,
        "pct_1d": pct_today,
        "badges": _header_badges_from_row(row or {}),
    }

    # We pass the most specific run_id we have (intraday rid if present), else original hint
    run_id_for_spark = rid_used or (run_id or "")
    prices_30d, ema10_30d, dates_30d = _sparkline_from_repos(
        deps.indicators_repo, canon or sym_in, run_id_for_spark, row or {}
    )
    sparkline = {
        "prices_30d": prices_30d if prices_30d else [price_now],
        "ema10_30d": ema10_30d if ema10_30d else None,
        "dates_30d": dates_30d if dates_30d else None,
    }

    trend_rank = _trend_rank_from_adx(indicators["adx14"])
    breakout_quality = _breakout_quality(indicators.get("proximity_52w_high_pct"), (row or {}).get("pivot_clear_pct"), (row or {}).get("base_len_bars"))
    score_basic_raw = (row or {}).get("score_basic")
    if isinstance(score_basic_raw, str):
        try:
            score_basic_raw = float(score_basic_raw)
        except ValueError:
            score_basic_raw = None

    # Prefer normalized→12 mapping if raw appears to be 0..100
    score_basic_norm_raw = (row or {}).get("score_basic_normalized")
    if isinstance(score_basic_norm_raw, str):
        try:
            score_basic_norm_raw = float(score_basic_norm_raw)
        except ValueError:
            score_basic_norm_raw = None
    if isinstance(score_basic_raw, (int, float)) and float(score_basic_raw) <= 12:
        score_basic = max(0, min(int(score_basic_raw), 12))
    elif isinstance(score_basic_norm_raw, (int, float)):
        score_basic = max(0, min(int(round((float(score_basic_norm_raw) / 100.0) * 12.0)), 12))
    elif isinstance(score_basic_raw, (int, float)):
        # Fallback: raw > 12 but normalized missing — scale heuristically
        score_basic = max(0, min(int(round((float(score_basic_raw) / 100.0) * 12.0)), 12))
    else:
        score_basic = None
    # Normalized (0..100)
    if isinstance(score_basic_norm_raw, (int, float)):
        score_basic_normalized = max(0, min(float(score_basic_norm_raw), 100))
    elif isinstance(score_basic_raw, (int, float)) and float(score_basic_raw) > 12:
        score_basic_normalized = max(0, min(float(score_basic_raw), 100))
    else:
        score_basic_normalized = None

    if row is not None:
        row["score_basic"] = score_basic
        row["score_basic_normalized"] = score_basic_normalized

    score_breakdown = {
        "score_total_0_100": int(score) if score is not None else 0,
        "score_source": (row or {}).get("score_source"),
        "score_basic": score_basic,
        "score_basic_normalized": score_basic_normalized,
        "rsi14": indicators["rsi14"],
        "adx14": indicators["adx14"],
        "relvol20": indicators["relvol20"],
        "trend_rank": trend_rank,
        "breakout_quality": breakout_quality,
        "proximity_52w_high_pct": indicators["proximity_52w_high_pct"],
        "pivot_clear_pct": (row or {}).get("pivot_clear_pct"),
        "base_len_bars": _i((row or {}).get("base_len_bars")),
        "data_gaps": (row or {}).get("data_gaps") or None,
        "stale": bool((row or {}).get("stale")) if (row or {}).get("stale") is not None else None,
    }

    # Use the euphoria flag computed above for exit threshold
    exit_thr = _choose_exit_threshold(indicators, eup_on)
    action_block = {
        "stop_now": position.get("stop_now") if position.get("stop_now") not in (0, 0.0) else None,
        "stop_method": position.get("stop_method") if position.get("stop_now") else None,
        "exit_close_threshold": (exit_thr if exit_thr not in (0, 0.0) else None),
        "breakeven_state": "Active" if (
            (position.get("entry_price_locked") and position.get("stop_now") and position.get("stop_now") >= position.get("entry_price_locked"))
            or bool(position.get("breakeven_active"))
        ) else "Pending",
        "euphoria_state": bool(eup_on),
    }
    log.info("action_block=%s", action_block)

    diagnostics = {
        "reason": (row or {}).get("reason") or "",
        "reason_text": (row or {}).get("reason") or None,
        "rules_version": (row or {}).get("rules_version") or "scores_v2",
        "blocked_reason": None,
    }

    # Align diagnostics tone with BUY actions
    if isinstance(next_action, dict):
        _act = (next_action.get("code") or "").upper()
        _diag = (diagnostics.get("reason") or diagnostics.get("reason_text") or "").strip()
        if _act.startswith("BUY") and _diag.lower().startswith("no"):
            if _act == "BUY_BREAKOUT":
                diagnostics["reason"] = "Yes — breakout setup: pivot cleared, momentum/volume supportive"
            elif _act == "BUY_PULLBACK":
                diagnostics["reason"] = "Setup — extended; prefer pullback toward EMA band"
            elif _act == "BUY_STARTER":
                diagnostics["reason"] = "Setup — early strength; small starter size"
            diagnostics["reason_text"] = diagnostics["reason"]

    payload = {
        "drawer_contract_version": "1.0.0",
        "scoring_rules_version": (row or {}).get("rules_version") or "scores_v2",
        "symbol": sym_in,
        "trading_day": _derive_trading_day(as_of_val),
        "intraday_numerator_used": bool(rid_used),  # mark if we used an intraday snapshot
        "header": header,
        "sparkline": sparkline,
        "score_breakdown": score_breakdown,
        "position": {
            "entry_price_locked": position.get("entry_price_locked") or None,
            "qty": position.get("qty") or None
        },
        "action_block": action_block,
        "meters": meters,
        "next_action": next_action,
        "alerts": {"suggestions": []},
        "diagnostics": diagnostics,
        "news_recent_hours": _right_drawer_news_hours(),

        # FE compatibility fields (kept)
        "run_id": rid_used or (run_id or ""),
        "as_of": as_of_val,
        "name": name,
        "sector": sector,
        "price": price_now,
        "pct_today": pct_today,
        "score": score,
        "indicators": indicators,
        "badges": header["badges"],
        "method_pill": method_pill,
        "alert_templates": [],
        "channels": None,
        "symbol_canon": (canon or sym_in),
    }

    # Ensure tz-aware 'as_of' and serialize to ISO8601 string
    _asof_dt = _coerce_as_of(payload.get("as_of"), run_id=rid_used or run_id, tz_name=_TZ_DEFAULT)
    payload["as_of"] = _asof_dt.isoformat()

    log.info("build: payload %s@%s as_of=%s price=%s", sym_in, payload["run_id"], payload["as_of"], payload["price"])
    return payload


# ---------- New-layout read helper (no legacy) ----------
def _normalize_meters_to_contract(meters: Dict[str, Any], ind: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure meters have the quantitative fields required by the model:
    - score_0_100
    - thresholds
    Works with both upgraded domain meters and legacy meters.
    """
    def add_fields(kind: str, m: Dict[str, Any]) -> Dict[str, Any]:
        m = dict(m or {})
        # thresholds
        if "thresholds" not in m:
            m["thresholds"] = {"low_lt": 33, "medium_gte": 33, "high_gte": 66}
        # score
        if m.get("score_0_100") is None:
            if kind == "risk":
                atr = (m.get("basis", {}) or {}).get("atr14_pct")
                if atr is None:
                    atr = (m.get("basis", {}) or {}).get("atr_pct")
                try:
                    s = max(0.0, min(100.0, (float(atr) / 8.0) * 100.0)) if atr is not None else None
                except Exception:
                    s = None
                m["score_0_100"] = int(round(s)) if s is not None else 0
            else:
                rsi = ind.get("rsi14"); adx = ind.get("adx14"); slope = ind.get("adx_slope_5") or 0.0
                try:
                    rsi_part = max(0.0, min(70.0, ((float(rsi) - 55.0) / 25.0) * 70.0)) if rsi is not None else 0.0
                except Exception:
                    rsi_part = 0.0
                try:
                    adx_part = max(0.0, min(30.0, ((float(adx) - 20.0) / 25.0) * 30.0)) if adx is not None else 0.0
                except Exception:
                    adx_part = 0.0
                slope_bonus = 5.0 if (slope or 0.0) > 0 else 0.0
                # ✅ correct clamp: clamp the SUM between 0 and 100
                s = max(0.0, min(100.0, rsi_part + adx_part + slope_bonus))
                m["score_0_100"] = int(round(s))
        return m

    meters = dict(meters or {})
    meters["risk"] = add_fields("risk", meters.get("risk") or {"level": "Low", "basis": {}})
    meters["euphoria"] = add_fields("euphoria", meters.get("euphoria") or {"level": "Low", "basis": {}})
    return meters


def _read_row_new_layout(scores_repo: Any, symbol: str, *, run_id_hint: Optional[str], as_of_hint: Optional[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str], Optional[str]]:
    """
    Read exactly one row for `symbol` from **new layout**:
      - If run_id_hint provided → try intraday path first (symbol-filtered), else fallback to daily(date=run_id date).
      - If as_of_hint provided (and no run_id_hint) → read that exact DAILY snapshot (symbol-filtered).
      - Else → use repo's latest resolution (EOD(today) > Intraday(today) > EOD(≤ today)).
    Returns: (row, canonical_symbol, run_id_used, as_of_used)
    """
    if not scores_repo or not hasattr(scores_repo, "read") or not hasattr(scores_repo, "latest_run"):
        log.warning("read_new_layout: repo missing required interfaces")
        return None, None, None, None

    # Candidates for symbol normalization
    candidates = _symbol_candidates(symbol)
    log.info("read_new_layout: candidates=%s", candidates)

    # 0) If caller gave a run_id, try intraday path first (symbol-filtered)
    if run_id_hint:
        try:
            items, total, rid_used, as_of_used = scores_repo.read(
                run_id=run_id_hint,
                as_of_str=None,
                filters={("symbol", "eq"): symbol.upper()},
                sort=None,
                page=1,
                per_page=1,
            )
            log.info("read_new_layout: try intraday@%s total=%s rid_used=%s as_of=%s", run_id_hint, total, rid_used, as_of_used)
            if total and items:
                row = dict(items[0])
                return row, symbol.upper(), rid_used or run_id_hint, as_of_used or row.get("as_of")
        except Exception:
            log.exception("read_new_layout: intraday run_id search failed")

        # Fallback to daily using date derived from run_id
        try:
            as_of_from_rid = (run_id_hint or "")[:8]
            if len(as_of_from_rid) == 8:
                iso = f"{as_of_from_rid[0:4]}-{as_of_from_rid[4:6]}-{as_of_from_rid[6:8]}"
                items, total, rid_used, as_of_used = scores_repo.read(
                    run_id=None,
                    as_of_str=iso,
                    filters={("symbol", "eq"): symbol.upper()},
                    sort=None,
                    page=1,
                    per_page=1,
                )
                log.info("read_new_layout: fallback daily@%s rows=%s as_of=%s", iso, total, as_of_used)
                if total and items:
                    row = dict(items[0])
                    return row, symbol.upper(), rid_used, as_of_used or iso
        except Exception:
            log.exception("read_new_layout: daily fallback by run_id date failed")

    # 1) If caller provided an explicit as_of date, try that exact daily snapshot
    if as_of_hint and not run_id_hint:
        for cand in candidates:
            try:
                items, total, rid_used, as_of_used = scores_repo.read(
                    run_id=None,
                    as_of_str=as_of_hint,
                    filters={("symbol", "eq"): cand},
                    sort=None,
                    page=1,
                    per_page=1,
                    columns=None,
                )
                log.info("read_new_layout: explicit EOD %s cand=%s rows=%s", as_of_hint, cand, total)
                if total and items:
                    row = dict(items[0])
                    return row, cand, rid_used, as_of_used or as_of_hint
            except Exception:
                log.exception("read_new_layout: explicit as_of read failed for %s", cand)

    # 2) Ask repo for latest (EOD(today) > Intraday(today) > EOD(≤today))
    rid_latest, as_of_latest = None, None
    try:
        rid_latest, as_of_latest = scores_repo.latest_run()
        log.info("read_new_layout: latest_run → rid=%s as_of=%s", rid_latest, as_of_latest)
    except Exception:
        log.exception("read_new_layout: latest_run failed")

    # 3) Read by symbol with repo's resolver (no explicit hints)
    for cand in candidates:
        try:
            items, total, rid_used, as_of_used = scores_repo.read(
                run_id=None,
                as_of_str=None,
                filters={("symbol", "eq"): cand},
                sort=None,
                page=1,
                per_page=1,
                columns=None,
            )
            log.info("read_new_layout: read cand=%s → rows=%s rid_used=%s as_of=%s", cand, total, rid_used, as_of_used)
            if total and items:
                row = dict(items[0])
                # Prefer repo-returned run_id/as_of; otherwise use latest_run hints
                return row, cand, (rid_used or rid_latest), (as_of_used or row.get("as_of") or as_of_latest)
        except TypeError:
            items, total, rid_used, as_of_used = scores_repo.read(
                run_id=None,
                as_of_str=None,
                filters={("symbol", "eq"): cand},
                sort=None,
                page=1,
                page_size=1,
                columns=None,
            )
            log.info("read_new_layout: read(legacy sig) cand=%s → rows=%s rid_used=%s as_of=%s", cand, total, rid_used, as_of_used)
            if total and items:
                row = dict(items[0])
                return row, cand, (rid_used or rid_latest), (as_of_used or row.get("as_of") or as_of_latest)
        except Exception:
            log.exception("read_new_layout: repo.read failed for cand=%s", cand)

    log.warning("read_new_layout: MISS for symbol=%s", symbol)
    return None, None, rid_latest, as_of_latest


# ---------- Helpers (unchanged below) ----------

def _symbol_candidates(symbol: str):
    s = (symbol or "").upper()
    cands = {s}
    if not s.endswith(".NS"):
        cands.add(f"{s}.NS")
    else:
        cands.add(s.replace(".NS", ""))
    cands.add(s.lower())
    if s.endswith(".NS"):
        cands.add(s[:-3].lower() + ".ns")
    return list(cands)

def _position_symbol_candidates(symbol: str):
    s = (symbol or "").upper()
    base = s[:-3] if s.endswith(".NS") else s
    return [s, base, base.lower(), s.lower(), f"{base}.NS"]

def _extract_ema_periods(row: Dict[str, Any]) -> Dict[int, float]:
    out: Dict[int, float] = {}
    if isinstance(row, dict):
        for k, v in row.items():
            if isinstance(k, str) and k.startswith("ema"):
                num = ""
                for ch in k[3:]:
                    if ch.isdigit():
                        num += ch
                    else:
                        break
                if num:
                    try:
                        out[int(num)] = float(v)
                    except Exception:
                        pass
    return out

def _pick_fast_slow_periods(emap: Dict[int, float]) -> Tuple[int, int]:
    if not emap:
        return 8, 10
    periods = sorted(emap.keys())
    slow = 10 if 10 in emap else min(periods, key=lambda p: abs(p - 10))
    if 8 in emap and 8 < slow:
        fast = 8
    else:
        below = [p for p in periods if p < slow]
        fast = min(below) if below else slow
    return int(fast), int(slow)

def _derive_trading_day(as_of_iso: str) -> str:
    if not as_of_iso or "T" not in as_of_iso:
        return (as_of_iso or "")[:10] or "1970-01-01"
    return as_of_iso.split("T", 1)[0]

def _trend_rank_from_adx(adx14: float) -> int:
    try:
        a = float(adx14 or 0.0)
    except Exception:
        a = 0.0
    if a <= 20: return 0
    if a >= 45: return 10
    return int(round((a - 20) / (45 - 20) * 10))

def _breakout_quality(prox52: Optional[float], pivot_clear_pct: Optional[float], base_len_bars: Optional[float]) -> int:
    try:
        p = float(prox52) if prox52 is not None else None
    except Exception:
        p = None
    try:
        pc = float(pivot_clear_pct) if pivot_clear_pct is not None else None
    except Exception:
        pc = None
    try:
        b = float(base_len_bars) if base_len_bars is not None else None
    except Exception:
        b = None

    score = 0
    if p is not None:
        if p >= 0: score += 4
        else:
            gap = abs(p)
            score += 0 if gap >= 5 else int(round(4 * (1 - gap/5.0)))
    if pc is not None and pc > 0:
        score += min(4, int(round(1 + 1.5 * min(pc, 2))))
    if b is not None:
        score += int(round(_clamp((b - 10) / (40 - 10), 0, 1) * 2))
    return int(_clamp(score, 0, 10))

def _choose_exit_threshold(ind: Dict[str, Any], eup_on: bool) -> float:
    if eup_on:
        v = ind.get("ema8") or ind.get("ema_fast_value")
        return _f(v)
    v = ind.get("ema10") or ind.get("ema_slow_value")
    return _f(v)

def _sparkline_from_repos(
    ind_repo: Any,
    symbol: str,
    run_id: str,
    row: Dict[str, Any]
) -> Tuple[List[float], Optional[List[float]], Optional[List[str]]]:
    prices: List[float] = []
    ema10: Optional[List[float]] = None
    dates: Optional[List[str]] = None

    if not ind_repo:
        log.info("sparkline: indicators_repo missing for %s", symbol)
        return prices, ema10, dates

    for meth in ("get_sparkline", "get_prices_30d"):
        if hasattr(ind_repo, meth):
            try:
                fn = getattr(ind_repo, meth)
                data = fn(symbol=symbol, run_id=run_id, n=30) if "n" in fn.__code__.co_varnames else fn(symbol=symbol, run_id=run_id)

                if isinstance(data, dict):
                    if "prices" in data and isinstance(data["prices"], list):
                        prices = [float(x) for x in data["prices"] if x is not None]
                    if not prices and "prices_30d" in data and isinstance(data["prices_30d"], list):
                        prices = [float(x) for x in data["prices_30d"] if x is not None]

                    if "ema10" in data and isinstance(data["ema10"], list):
                        ema10 = [float(x) for x in data["ema10"] if x is not None]
                    if ema10 is None and "ema10_30d" in data and isinstance(data["ema10_30d"], list):
                        ema10 = [float(x) for x in data["ema10_30d"] if x is not None]

                    if "dates" in data and isinstance(data["dates"], list):
                        dates = [str(x) for x in data["dates"] if x is not None]
                    if (dates is None) and "dates_30d" in data and isinstance(data["dates_30d"], list):
                        dates = [str(x) for x in data["dates_30d"] if x is not None]

                elif isinstance(data, list):
                    prices = [float(x) for x in data if x is not None]

                if prices:
                    log.info(
                        "sparkline: %s via %s → points=%d (ema=%s, dates=%s)",
                        symbol, meth, len(prices),
                        "yes" if (ema10 and len(ema10) == len(prices)) else "no",
                        "yes" if (dates and len(dates) == len(prices)) else "no",
                    )
                    break
            except Exception:
                log.exception("sparkline fetch via %s failed for %s", meth, symbol)

    return prices, ema10, dates


def _i(x) -> int:
    try: return int(x)
    except Exception: return 0
def _f(x) -> float:
    try: return float(x)
    except Exception: return 0.0
def _is_number(x) -> bool:
    try:
        float(x)
        return True
    except Exception:
        return False
def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
