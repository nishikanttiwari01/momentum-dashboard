# backend/app/services/detail_service.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Iterable

log = logging.getLogger("services.detail")

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


@dataclass
class DetailDeps:
    scores_repo: Any
    indicators_repo: Any | None
    positions_repo: Any | None
    snapshot_pins_repo: Any | None


def _resolve_run_id(symbol: str, run_id: Optional[str], deps: DetailDeps) -> Tuple[Optional[str], Optional[str]]:
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
    sym_in = (symbol or "").upper()
    row, canon = _read_row_with_symbol_normalization(deps.scores_repo, run_id, sym_in)
    log.info("build: symbol=%s run_id=%s canon=%s has_row=%s", sym_in, run_id, canon, bool(row))
    if row:
        log.debug("build: row_keys=%s", sorted(list(row.keys())))

    # helpers
    _nn = lambda v, d: v if v is not None else d

    # top-level
    price_now = _f((row or {}).get("last"))
    name_snapshot = (row or {}).get("name")
    sector_snapshot = (row or {}).get("sector")
    name_fallback, sector_fallback = _enrich_meta(canon or sym_in)
    name = _nn(name_snapshot, _nn(name_fallback, sym_in))
    sector = _nn(sector_snapshot, _nn(sector_fallback, ""))
    pct_today = _f((row or {}).get("pct_today") or (row or {}).get("change_pct"))
    score_raw = (row or {}).get("score")
    score = _i(score_raw) if isinstance(score_raw, int) else _f(score_raw)
    as_of = _nn((row or {}).get("as_of"), "")

    # indicators via ema{N} columns
    ema_map = _extract_ema_periods(row or {})
    log.debug("build: ema_map=%s", ema_map)
    fast_n, slow_n = _pick_fast_slow_periods(ema_map)
    fast_val = ema_map.get(fast_n, price_now)
    slow_val = ema_map.get(slow_n, price_now)

    indicators: Dict[str, Any] = {
        "rsi14": _f((row or {}).get("rsi14") or (row or {}).get("rsi")),
        "adx14": _f((row or {}).get("adx14") or (row or {}).get("adx")),
        "adx_slope": _f((row or {}).get("adx_slope")),
        "ema_fast": fast_n,              # int
        "ema_fast_value": _f(fast_val),
        "ema_slow": slow_n,              # int
        "ema_slow_value": _f(slow_val),
        "relvol20": _f((row or {}).get("relvol20")),
        "proximity_52w_high_pct": _f((row or {}).get("proximity_52w_high_pct") or (row or {}).get("pct_from_52w_high")),
    }

    # position (try multiple keys)
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
    if deps.positions_repo:
        pos = None
        for key in _position_symbol_candidates(canon or sym_in):
            try:
                pos = deps.positions_repo.get(key)
            except Exception:
                pos = None
            if pos:
                log.info("build: positions hit for %s via key=%s", sym_in, key)
                break
        if pos:
            g = (lambda k: pos.get(k) if isinstance(pos, dict) else getattr(pos, k, None))
            position.update({
                "entry_price": _f(g("entry_price")),
                "entry_price_locked": _f(g("entry_price_locked")),
                "qty": _i(g("qty")),
                "trade_on": bool(g("trade_on")) if g("trade_on") is not None else False,
                "stop_now": _f(g("stop_now")),
                "exit_close_threshold": _f(g("exit_close_threshold")),
                "breakeven_active": bool(g("breakeven_active")) if g("breakeven_active") is not None else False,
                "euphoria_on": bool(g("euphoria_on")) if g("euphoria_on") is not None else False,
                "note": _nn(g("note"), ""),
            })
        else:
            log.info("build: no position row found for %s", sym_in)

    badges = (row or {}).get("badges")
    if not isinstance(badges, list):
        badges = []

    meters, next_action = _compute_meters_and_next(price_now, indicators, position)

    method_n = int(indicators["ema_fast"] if position["euphoria_on"] else indicators["ema_slow"])
    method_pill = f"EMA{method_n}" if method_n else "EMA"

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
        "badges": badges,
        "position": position,
        "method_pill": method_pill,
        "meters": meters,
        "next_action": next_action,
        "alert_templates": [],
        # IMPORTANT: some model versions typed Channels as Optional[str]/bools.
        # To avoid response-model 500s, omit 'channels' entirely; the schema default/alias handles it.
        # If your final model expects an object, add {"email": None, "desktop": None, "whatsapp": None}.
        # "channels": {"email": None, "desktop": None, "whatsapp": None},
    }
    log.debug("build: payload summary for %s@%s -> price=%s ema_fast=%s/%s ema_slow=%s/%s",
              sym_in, run_id, price_now, indicators["ema_fast"], indicators["ema_fast_value"],
              indicators["ema_slow"], indicators["ema_slow_value"])
    return payload


# ---------- helpers ----------
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
    for k, v in row.items():
        if not isinstance(k, str) or not k.startswith("ema"):
            continue
        # accept ema10 / ema50 / ema200 / ema10_value → take first number run
        num = ""
        for ch in k[3:]:
            if ch.isdigit():
                num += ch
            else:
                break
        if not num:
            continue
        try:
            n = int(num)
            out[n] = float(v)
        except Exception:
            continue
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

def _compute_meters_and_next(price_now: Optional[float],
                             ind: Dict[str, Any],
                             pos: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if _HAVE_RULES:
        meters_model = _rules_compute_meters(_to_ind_model(ind))
        next_model = _rules_resolve_next_action(price_now or 0.0, _to_ind_model(ind), _to_pos_model(pos))
        return _obj_to_dict(meters_model), _obj_to_dict(next_model)

    def _bucket_relvol(x):
        x = (float(x) if x is not None else None)
        if x is None: return "Medium"
        if x < 1.2: return "Low"
        if x < 1.8: return "Medium"
        return "High"

    def _bucket_euphoria(rsi, adx):
        r = float(rsi) if rsi is not None else 0.0
        a = float(adx) if adx is not None else 0.0
        s = r + 0.5 * a
        if s < 70: return "Low"
        if s < 90: return "Medium"
        return "High"

    meters = {
        "risk": {"level": _bucket_relvol(ind.get("relvol20")),
                 "basis": {"relvol20": float(ind.get("relvol20") or 0.0)}},
        "euphoria": {"level": _bucket_euphoria(ind.get("rsi14"), ind.get("adx14")),
                     "basis": {"rsi14": float(ind.get("rsi14") or 0.0),
                               "adx14": float(ind.get("adx14") or 0.0)}},
    }

    ema_n = int(ind.get("ema_slow") or ind.get("ema_fast") or 10)
    ema_val = float(ind.get("ema_slow_value") or ind.get("ema_fast_value") or (price_now or 0.0))

    if price_now is not None and ema_val and price_now >= ema_val:
        stop_now = pos.get("stop_now") or 0.0
        if stop_now:
            next_action = {
                "code": "HOLD_TRAIL",
                "text": f"Hold (trail stop at ₹{float(stop_now):,.1f})",
                "reasons": [f"Close ≥ EMA{ema_n}", "Momentum intact"],
                "refs": {"stop_now": float(stop_now), "ema_n": int(ema_n), "ema_value": float(ema_val)},
                "action": "HOLD",
            }
        else:
            next_action = {
                "code": "HOLD",
                "text": f"Hold (above EMA{ema_n})",
                "reasons": [f"Close ≥ EMA{ema_n}"],
                "refs": {"ema_n": int(ema_n), "ema_value": float(ema_val)},
                "action": "HOLD",
            }
    else:
        next_action = {
            "code": "WATCH",
            "text": "Watch (no clear signal)",
            "reasons": [],
            "refs": {"ema_n": int(ema_n), "ema_value": float(ema_val)},
            "action": "WATCH",
        }

    return meters, next_action

def _enrich_meta(symbol: str):
    candidates = ["app.repos.parquet.universe_repo", "app.repos.parquet.universe"]
    for mod_name in candidates:
        try:
            mod = __import__(mod_name, fromlist=["*"])
        except Exception:
            continue
        for cls_name in ("UniverseRepo", "Universe"):
            Repo = getattr(mod, cls_name, None)
            if not Repo:
                continue
            try:
                repo = Repo()
                for meth in ("get", "get_by_symbol", "read_one"):
                    if hasattr(repo, meth):
                        row = getattr(repo, meth)(symbol)
                        if not row:
                            continue
                        if isinstance(row, dict):
                            return row.get("name"), row.get("sector")
                        return getattr(row, "name", None), getattr(row, "sector", None)
            except Exception:
                continue
    return None, None

def _to_ind_model(ind: Dict[str, Any]):
    class _I:
        rsi14 = ind.get("rsi14"); adx14 = ind.get("adx14")
        ema_fast = ind.get("ema_fast"); ema_slow = ind.get("ema_slow")
        ema_fast_value = ind.get("ema_fast_value"); ema_slow_value = ind.get("ema_slow_value")
        relvol20 = ind.get("relvol20"); proximity_52w_high_pct = ind.get("proximity_52w_high_pct")
        ret_1m = ind.get("ret_1m"); ret_3m = ind.get("ret_3m"); ret_6m = ind.get("ret_6m"); ret_12_1m = ind.get("ret_12_1m")
    return _I()

def _to_pos_model(pos: Dict[str, Any]):
    class _P:
        stop_now = pos.get("stop_now"); exit_close_threshold = pos.get("exit_close_threshold")
        breakeven_active = bool(pos.get("breakeven_active")) if pos.get("breakeven_active") is not None else False
        euphoria_on = bool(pos.get("euphoria_on")) if pos.get("euphoria_on") is not None else False
        entry_price = pos.get("entry_price"); entry_price_locked = pos.get("entry_price_locked")
    return _P()

def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    out: Dict[str, Any] = {}
    for k in dir(obj):
        if k.startswith("_"): continue
        v = getattr(obj, k)
        if callable(v): continue
        out[k] = v
    return out

def _i(x) -> int:
    try: return int(x)
    except Exception: return 0

def _f(x) -> float:
    try: return float(x)
    except Exception: return 0.0
