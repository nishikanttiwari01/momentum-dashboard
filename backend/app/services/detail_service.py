from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger("app.services.detail")

try:
    # Optional rule engine (if present, we will use it for meters/next-action)
    from app.domain.rules.next_action import (
        compute_meters as _rules_compute_meters,
        resolve_next_action as _rules_resolve_next_action,
    )
    _HAVE_RULES = True
except Exception:  # pragma: no cover
    _HAVE_RULES = False
    _rules_compute_meters = None
    _rules_resolve_next_action = None


@dataclass
class DetailDeps:
    scores_repo: Any
    indicators_repo: Any | None
    positions_repo: Any | None
    snapshot_pins_repo: Any | None


def _resolve_run_id(symbol: str, run_id: Optional[str], deps: DetailDeps) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve run_id: query param → pinned → latest (scores_repo).
    Returns (run_id, as_of).
    """
    rid = (run_id or "").strip() or None
    as_of: Optional[str] = None

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
        except Exception:
            log.exception("resolve_run_id: pin lookup failed for %s", symbol)

    if not rid and deps.scores_repo and hasattr(deps.scores_repo, "latest_run"):
        try:
            rid2, as_of2 = deps.scores_repo.latest_run()
            rid = rid or rid2
            as_of = as_of2 or as_of
        except Exception:
            log.exception("resolve_run_id: latest_run() failed")

    log.info("resolve_run_id: symbol=%s → rid=%s as_of=%s", symbol, rid, as_of)
    if not rid:
        return None, None
    return rid, as_of


def build_drawer_detail(symbol: str, run_id: str, deps: DetailDeps) -> Dict[str, Any]:
    """
    Build the drawer payload by merging:
      • market snapshot (parquet via scores_repo)
      • locked state (positions_repo), if any
      • system Entry Suggestion (Req §3.4) when no locked entry exists
      • meters + next-action (rule engine if available, else fallback)
    """
    sym_in = (symbol or "").upper()
    row, canon = _read_row_with_symbol_normalization(deps.scores_repo, run_id, sym_in)
    log.info("build: symbol=%s run_id=%s canon=%s has_row=%s", sym_in, run_id, canon, bool(row))
    if row:
        log.info("build: row keys: %s", sorted(list(row.keys())))

    # --- top-level snapshot fields ---
    price_now = _f((row or {}).get("last"))
    name_snapshot = (row or {}).get("name")
    sector_snapshot = (row or {}).get("sector")
    name = name_snapshot if name_snapshot not in (None, "") else sym_in
    sector = sector_snapshot if sector_snapshot is not None else ""
    as_of = (row or {}).get("as_of") or ""
    pct_today = _f((row or {}).get("pct_today") or (row or {}).get("change_pct"))
    score_raw = (row or {}).get("score")
    score = score_raw if isinstance(score_raw, int) else _f(score_raw)

    # --- indicators / EMAs ---
    ema_map = _extract_ema_periods(row or {})
    log.info("build: ema_map=%s", ema_map)
    fast_n, slow_n = _pick_fast_slow_periods(ema_map)
    fast_val = ema_map.get(fast_n, price_now)
    slow_val = ema_map.get(slow_n, price_now)

    indicators: Dict[str, Any] = {
        "rsi14": _f((row or {}).get("rsi14") or (row or {}).get("rsi")),
        "adx14": _f((row or {}).get("adx14") or (row or {}).get("adx")),
        "adx_slope": _f((row or {}).get("adx_slope")),
        "ema_fast": int(fast_n),
        "ema_fast_value": _f(fast_val),
        "ema_slow": int(slow_n),
        "ema_slow_value": _f(slow_val),
        "relvol20": _f((row or {}).get("relvol20")),
        "proximity_52w_high_pct": _f((row or {}).get("proximity_52w_high_pct") or (row or {}).get("pct_from_52w_high")),
    }

    # ATR% (if present) → absolute ATR in currency
    atr_pct = _f((row or {}).get("atr14_pct") or (row or {}).get("atr_pct"))
    atr_abs = price_now * (atr_pct / 100.0) if atr_pct else 0.0

    # --- locked position (if any) ---
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

    # --- Entry Suggestion (Req §3.4) when no locked entry exists ---
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
        # Show the suggested entry as "entry_price" until user locks it.
        position["entry_price"] = float(entry_suggestion["price"])

    # --- meters + next-action ---
    meters, next_action = _compute_meters_and_next(price_now, indicators, position)

    # Add suggestion details for FE copy (“Buy on pullback (A–B)”)
    if entry_suggestion:
        refs = next_action.get("refs") or {}
        refs.update({
            "entry_suggested": entry_suggestion.get("price"),
            "entry_low": entry_suggestion.get("low"),
            "entry_high": entry_suggestion.get("high"),
            "entry_type": entry_suggestion.get("type"),
            "entry_reason": entry_suggestion.get("reason"),
        })
        next_action["refs"] = refs

    # method pill (EMA slow by default; rule-engine may override elsewhere)
    method_pill = f"EMA{int(indicators['ema_slow'])}" if indicators["ema_slow"] else "EMA"

    payload = {
        "run_id": run_id,
        "as_of": as_of,
        "symbol": sym_in,
        "symbol_canon": (canon or sym_in),
        "name": name,
        "sector": sector,
        "price": price_now,
        "pct_today": pct_today,
        "score": score,
        "indicators": indicators,
        "badges": (row or {}).get("badges") if isinstance((row or {}).get("badges"), list) else [],
        "position": position,
        "method_pill": method_pill,
        "meters": meters,
        "next_action": next_action,
        "alert_templates": [],
        "channels": None,
    }

    log.info(
        "build: payload %s@%s price=%s ema_fast=%s/%s ema_slow=%s/%s entry=%s qty=%s",
        sym_in, run_id, payload["price"],
        indicators["ema_fast"], indicators["ema_fast_value"],
        indicators["ema_slow"], indicators["ema_slow_value"],
        position["entry_price"], position["qty"]
    )
    return payload


# ------------- helpers -------------

def _compute_entry_suggestion(
    *,
    price_now: float,
    ema_fast_n: int,
    ema_fast_val: float,
    ema_slow_n: int,
    ema_slow_val: float,
    rsi14: float,
    adx14: float,
    relvol20: float,
    prox52: float,
    atr_abs: float,
) -> Dict[str, Any]:
    """
    Heuristic entry logic mapped from the requirements:
      • If momentum is strong and near 52W high → “Buy on breakout now” at market (price_now).
      • If strong but extended above EMA → “Buy on pullback” into a band near EMA_fast.
      • If moderate trend emerging → “Starter (½ size)” slightly above EMA_slow.
      • Else → “Watch only”.
    Returns dict with keys: type, price, low, high, reason.
    """
    def strong_momo():
        return (rsi14 >= 60 and adx14 >= 25) or (prox52 >= -1.0)

    def extended():
        gap = price_now - ema_slow_val
        return ema_slow_val > 0 and (gap / ema_slow_val * 100.0) >= 3.0

    if strong_momo() and price_now >= ema_slow_val:
        if not extended():
            return {
                "type": "BREAKOUT",
                "price": float(price_now),
                "low": None,
                "high": None,
                "reason": f"Price ≥ EMA{ema_slow_n} and near 52W high / strong momentum",
            }
        else:
            # Pullback band to EMA_fast: [EMA_fast − 0.5×ATR, EMA_fast]
            low = float(max(ema_fast_val - 0.5 * atr_abs, 0.0)) if atr_abs else float(ema_fast_val * 0.995)
            high = float(ema_fast_val)
            price = float(min(price_now, high))
            return {
                "type": "PULLBACK",
                "price": price,
                "low": low,
                "high": high,
                "reason": f"Extended; prefer pullback to EMA{ema_fast_n}",
            }

    # Moderate setup → Starter (½ size) near slow EMA
    if rsi14 >= 55 and adx14 >= 20 and price_now >= ema_slow_val * 0.99:
        starter = float(max(ema_slow_val, price_now))
        return {
            "type": "STARTER",
            "price": starter,
            "low": None,
            "high": None,
            "reason": f"Momentum building; starter near EMA{ema_slow_n}",
        }

    # Watch only
    return {
        "type": "WATCH",
        "price": float(price_now) if price_now else 0.0,
        "low": None,
        "high": None,
        "reason": "No clear entry; watch only",
    }


def _compute_meters_and_next(price_now: Optional[float], ind: Dict[str, Any], pos: Dict[str, Any]):
    # Prefer rule engine if available
    if _HAVE_RULES:
        try:
            meters = _rules_compute_meters(price_now, ind, pos)
            next_action = _rules_resolve_next_action(price_now, ind, pos)
            return meters, next_action
        except Exception:
            log.exception("rules engine failed; falling back")

    # Fallback buckets
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
        "risk": {"level": _risk(ind.get("relvol20")), "basis": {"relvol20": float(ind.get("relvol20") or 0.0)}},
        "euphoria": {"level": _euph(ind.get("rsi14"), ind.get("adx14")),
                     "basis": {"rsi14": float(ind.get("rsi14") or 0.0), "adx14": float(ind.get("adx14") or 0.0)}},
    }
    ema_n = int(ind.get("ema_slow") or ind.get("ema_fast") or 10)
    ema_val = float(ind.get("ema_slow_value") or ind.get("ema_fast_value") or (price_now or 0.0))
    if price_now is not None and ema_val and price_now >= ema_val:
        stop_now = pos.get("stop_now") or 0.0
        if stop_now:
            next_action = {"code": "HOLD_TRAIL", "text": f"Hold (trail stop at ₹{float(stop_now):,.1f})",
                           "reasons": [f"Close ≥ EMA{ema_n}", "Momentum intact"],
                           "refs": {"stop_now": float(stop_now), "ema_n": int(ema_n), "ema_value": float(ema_val)},
                           "action": "HOLD"}
        else:
            next_action = {"code": "HOLD", "text": f"Hold (above EMA{ema_n})",
                           "reasons": [f"Close ≥ EMA{ema_n}"],
                           "refs": {"ema_n": int(ema_n), "ema_value": float(ema_val)}, "action": "HOLD"}
    else:
        next_action = {"code": "WATCH", "text": "Watch (no clear signal)", "reasons": [],
                       "refs": {"ema_n": int(ema_n), "ema_value": float(ema_val)}, "action": "WATCH"}
    return meters, next_action


def _read_row_with_symbol_normalization(scores_repo: Any, run_id: str, symbol: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not scores_repo or not hasattr(scores_repo, "read_one"):
        return None, None
    for cand in _symbol_candidates(symbol):
        try:
            row = scores_repo.read_one(symbol=cand, run_id=run_id)
            if row:
                return row, cand
        except Exception:
            continue
    return None, None

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
    for k, v in (row.items() if isinstance(row, dict) else []):
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

def _i(x) -> int:
    try: return int(x)
    except Exception: return 0
def _f(x) -> float:
    try: return float(x)
    except Exception: return 0.0
