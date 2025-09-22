# backend/app/services/detail_service.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, List
from datetime import datetime, date
from zoneinfo import ZoneInfo

log = logging.getLogger("app.services.detail")

_TZ_DEFAULT = "Asia/Singapore"

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
    from app.domain.rules.next_action import (
        compute_meters as _rules_compute_meters,
        resolve_next_action as _rules_resolve_next_action,
    )
    _HAVE_RULES = True
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
    from app.domain.next_action import compute_next_action as _domain_compute_next
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


def build_drawer_detail(symbol: str, run_id: str | None, deps: DetailDeps) -> Dict[str, Any]:
    """
    Build drawer detail using **new parquet layout only**:
      - If run_id is provided: try intraday at that run_id for the symbol; if not found, fall back to daily (as_of).
      - If run_id is None: rely on repo.new-layout resolution (intraday(today) → daily(≤today)) for the symbol.
    """
    sym_in = (symbol or "").upper()
    # Read one row using the repo's new-layout resolver (intraday → daily), filtered by symbol.
    row, canon, rid_used, as_of_used = _read_row_new_layout(deps.scores_repo, sym_in, run_id_hint=run_id)

    log.info(
        "build: symbol=%s canon=%s req_run_id=%s kind=%s resolved_run_id=%s resolved_as_of=%s has_row=%s",
        sym_in, canon, run_id,
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
    as_of = (row or {}).get("as_of") or as_of_used or ""
    pct_today = _f((row or {}).get("pct_today") or (row or {}).get("change_pct"))
    score_raw = (row or {}).get("score")
    score = score_raw if isinstance(score_raw, int) else _f(score_raw)

    trading_day = _derive_trading_day(as_of)

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

    atr_pct = indicators["atr14_pct"]
    atr_abs = price_now * (atr_pct / 100.0) if atr_pct else 0.0

    # --- positions (unchanged behavior) ---
    position: Dict[str, Any] = {
        "entry_price": 0.0,
        "entry_price_locked": 0.0,
        "qty": 0,
        "trade_on": False,
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
    if needs_suggestion and entry_suggestion.get("price"):
        position["entry_price"] = float(entry_suggestion["price"])

    # --- meters + next action (unchanged) ---
    meters, next_action = _compute_meters_and_next(price_now, indicators, position)
    meters = _normalize_meters_to_contract(meters, indicators)

    if isinstance(next_action, dict):
        refs = next_action.get("refs") or {}
        numeric_refs = {k: float(v) for k, v in refs.items() if _is_number(v)}
        if entry_suggestion:
            for k in ("price", "low", "high"):
                v = entry_suggestion.get(k)
                if _is_number(v):
                    numeric_refs[f"entry_{k if k!='price' else 'suggested'}"] = float(v)
        next_action["refs"] = numeric_refs

    method_pill = f"EMA{int(indicators['ema_slow'])}" if indicators["ema_slow"] else "EMA"

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
    prices_30d, ema10_30d = _sparkline_from_repos(deps.indicators_repo, canon or sym_in, run_id_for_spark, row or {})
    sparkline = {
        "prices_30d": prices_30d if prices_30d else [price_now],
        "ema10_30d": ema10_30d if ema10_30d else None,
    }

    trend_rank = _trend_rank_from_adx(indicators["adx14"])
    breakout_quality = _breakout_quality(indicators.get("proximity_52w_high_pct"), (row or {}).get("pivot_clear_pct"), (row or {}).get("base_len_bars"))
    score_breakdown = {
        "score_total_0_100": int(score) if score is not None else 0,
        "score_source": (row or {}).get("score_source"),
        "score_basic": (row or {}).get("score_basic"),
        "score_basic_normalized": (row or {}).get("score_basic_normalized"),
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

    eup_on = bool(next_action.get("code") in ("HOLD_TIGHT",)) or bool(position.get("euphoria_on"))
    exit_thr = _choose_exit_threshold(indicators, eup_on)
    action_block = {
        "stop_now": _f(position.get("stop_now")),
        "stop_method": "ATRxK",
        "exit_close_threshold": _f(exit_thr),
        "breakeven_state": "Active" if bool(position.get("breakeven_active")) else "Pending",
        "euphoria_state": True if eup_on else False,
    }

    diagnostics = {
        "reason": (row or {}).get("reason") or "",
        "reason_text": (row or {}).get("reason") or None,
        "rules_version": (row or {}).get("rules_version") or "scores_v2",
        "blocked_reason": None,
    }

    payload = {
        "drawer_contract_version": "1.0.0",
        "scoring_rules_version": (row or {}).get("rules_version") or "scores_v2",
        "symbol": sym_in,
        "trading_day": _derive_trading_day(as_of),
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

        # FE compatibility fields (kept)
        "run_id": rid_used or (run_id or ""),
        "as_of": as_of,
        "name": name,
        "sector": sector,
        "price": price_now,
        "pct_today": pct_today,
        "score": score,
        "indicators": indicators,
        "badges": (row or {}).get("badges") if isinstance((row or {}).get("badges"), list) else [],
        "method_pill": method_pill,
        "alert_templates": [],
        "channels": None,
        "symbol_canon": (canon or sym_in),
    }

    # Ensure tz-aware 'as_of' (works for either intraday ISO or daily YYYY-MM-DD)
    payload["as_of"] = _coerce_as_of(payload.get("as_of"), run_id=rid_used or run_id, tz_name=_TZ_DEFAULT)

    log.info("build: payload %s@%s as_of=%s price=%s", sym_in, payload["run_id"], payload["as_of"], payload["price"])
    return payload


# ---------- New-layout read helper (no legacy) ----------

def _read_row_new_layout(scores_repo: Any, symbol: str, *, run_id_hint: Optional[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str], Optional[str]]:
    """
    Read exactly one row for `symbol` from **new layout**:
      - If run_id_hint provided → try intraday(date=today, run_id=hint). If not found, fall back to daily (≤ today).
      - If run_id_hint not provided → use repo's latest resolution (intraday(today) → daily(≤ today)).
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
            from app.repos.parquet import datasets  # for today's UTC date
            today = datetime.now(ZoneInfo("UTC")).date().isoformat()
            # Try intraday run folder: read(date=today, run_id=hint) for this symbol
            # ScoresRepo exposes a helper that scans intraday partition by date+run, but we use its public read API:
            items, total, rid_used, as_of_used = scores_repo.read(
                run_id=run_id_hint,     # repo.read will interpret this against new layout (intraday) via its resolver
                as_of_str=None,
                filters={( "symbol", "eq"): symbol.upper()},
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

    # 1) Ask repo for latest (intraday → daily)
    rid_latest, as_of_latest = None, None
    try:
        rid_latest, as_of_latest = scores_repo.latest_run()
        log.info("read_new_layout: latest_run → rid=%s as_of=%s", rid_latest, as_of_latest)
    except Exception:
        log.exception("read_new_layout: latest_run failed")

    # 2) Read by symbol with repo's resolver (no run_id param)
    for cand in candidates:
        try:
            items, total, rid_used, as_of_used = scores_repo.read(
                run_id=None,
                as_of_str=None,
                filters={( "symbol", "eq"): cand},
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
            # Very old signature support (page_size)
            items, total, rid_used, as_of_used = scores_repo.read(
                run_id=None,
                as_of_str=None,
                filters={( "symbol", "eq"): cand},
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

def _sparkline_from_repos(ind_repo: Any, symbol: str, run_id: str, row: Dict[str, Any]) -> Tuple[List[float], Optional[List[float]]]:
    prices: List[float] = []
    ema10: Optional[List[float]] = None
    if not ind_repo:
        return prices, ema10
    for meth in ("last_n_closes", "last_n_prices", "get_prices_30d", "get_sparkline"):
        if hasattr(ind_repo, meth):
            try:
                fn = getattr(ind_repo, meth)
                if "n" in fn.__code__.co_varnames:
                    data = fn(symbol=symbol, run_id=run_id, n=30)
                else:
                    data = fn(symbol=symbol, run_id=run_id)
                if isinstance(data, dict):
                    if "prices" in data and isinstance(data["prices"], list):
                        prices = [float(x) for x in data["prices"] if x is not None]
                    if "ema10" in data and isinstance(data["ema10"], list):
                        ema10 = [float(x) for x in data["ema10"] if x is not None]
                elif isinstance(data, list):
                    prices = [float(x) for x in data if x is not None]
                if prices:
                    break
            except Exception:
                log.exception("sparkline fetch via %s failed", meth)
    return prices, ema10

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
