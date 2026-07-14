# backend/app/services/portfolio_service.py
"""Mutual-fund portfolio module.

Reads static config from configs/portfolio.yaml and transactions from
data/portfolio_transactions.csv. Fetches NAV history per scheme from
api.mfapi.in (AMFI data), resolving scheme codes by fuzzy name match against
the AMFI NAVAll list when not configured. Computes per-fund performance,
holdings, XIRR, category allocation and simple dip/underweight accumulation
signals.

All network results are cached on disk (data/mf_cache/) so the dashboard
degrades to cached data when offline. Nothing here is investment advice; the
output is explicitly labelled with reasons so the user can judge.
"""
from __future__ import annotations

import csv
import json
import logging
import math
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

log = logging.getLogger(__name__)

AMFI_NAVALL_URL = "https://www.amfiindia.com/spages/NAVAll.txt"
MFAPI_URL = "https://api.mfapi.in/mf/{code}"

_REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = _REPO_ROOT / "configs" / "portfolio.yaml"
TRANSACTIONS_PATH = _REPO_ROOT / "data" / "portfolio_transactions.csv"
CACHE_DIR = _REPO_ROOT / "data" / "mf_cache"


# ----------------------------- config loading -----------------------------

def load_portfolio_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        log.exception("portfolio: failed to parse %s", CONFIG_PATH)
        return {}


@dataclass
class Txn:
    date: date
    instrument_id: str
    account_id: str
    type: str
    amount: Optional[float]
    units: Optional[float]
    nav: Optional[float]
    fees: float = 0.0


def load_transactions() -> List[Txn]:
    txns: List[Txn] = []
    if not TRANSACTIONS_PATH.exists():
        return txns
    try:
        with TRANSACTIONS_PATH.open("r", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(
                row for row in fh if not row.lstrip().startswith("#")
            )
            for row in reader:
                try:
                    d = datetime.strptime((row.get("date") or "").strip(), "%Y-%m-%d").date()
                except Exception:
                    continue
                def _f(key: str) -> Optional[float]:
                    v = (row.get(key) or "").strip()
                    if not v:
                        return None
                    try:
                        return float(v)
                    except ValueError:
                        return None
                amount, units, nav = _f("amount"), _f("units"), _f("nav")
                if units is None and amount is not None and nav:
                    units = amount / nav
                if amount is None and units is not None and nav:
                    amount = units * nav
                if amount is None and units is None:
                    continue
                txns.append(
                    Txn(
                        date=d,
                        instrument_id=(row.get("instrument_id") or "").strip(),
                        account_id=(row.get("account_id") or "").strip(),
                        type=(row.get("type") or "BUY").strip().upper(),
                        amount=amount,
                        units=units,
                        nav=nav,
                        fees=_f("fees") or 0.0,
                    )
                )
    except Exception:
        log.exception("portfolio: failed to read transactions csv")
    return txns


# ----------------------------- caching helpers -----------------------------

def _cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / name

def _cache_read(name: str, max_age_hours: Optional[float]) -> Optional[Any]:
    p = _cache_path(name)
    if not p.exists():
        return None
    if max_age_hours is not None:
        age = time.time() - p.stat().st_mtime
        if age > max_age_hours * 3600:
            return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def _cache_write(name: str, payload: Any) -> None:
    try:
        _cache_path(name).write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        log.exception("portfolio: cache write failed for %s", name)


# --------------------------- AMFI code resolution ---------------------------

def _norm_tokens(s: str) -> List[str]:
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    stop = {"fund", "plan", "-", "the", "of"}
    return [t for t in s.split() if t and t not in stop]


def _fetch_navall_lines(ttl_hours: float) -> List[str]:
    cached = _cache_read("amfi_navall.json", ttl_hours)
    if cached:
        return cached
    try:
        import requests

        resp = requests.get(AMFI_NAVALL_URL, timeout=20)
        resp.raise_for_status()
        lines = resp.text.splitlines()
        _cache_write("amfi_navall.json", lines)
        return lines
    except Exception:
        log.warning("portfolio: AMFI NAVAll fetch failed; trying stale cache")
        return _cache_read("amfi_navall.json", None) or []


def resolve_scheme_code(name_hint: str, ttl_hours: float = 24.0) -> Optional[Dict[str, Any]]:
    """Resolve an AMFI scheme code by fuzzy name match. Cached per hint."""
    key = "code_" + re.sub(r"[^a-z0-9]+", "_", name_hint.lower()) + ".json"
    cached = _cache_read(key, None)
    if cached:
        return cached

    lines = _fetch_navall_lines(ttl_hours)
    want = set(_norm_tokens(name_hint))
    if not want or not lines:
        return None

    best: Optional[Tuple[float, Dict[str, Any]]] = None
    for line in lines:
        parts = line.split(";")
        if len(parts) < 6 or not parts[0].strip().isdigit():
            continue
        scheme_name = parts[3]
        have = set(_norm_tokens(scheme_name))
        if not want.issubset(have):
            continue
        # prefer the tightest name (fewest extra tokens); require direct+growth
        lname = scheme_name.lower()
        if "direct" in " ".join(want) or "direct" in lname:
            if "direct" not in lname:
                continue
        if "growth" not in lname:
            continue
        if "idcw" in lname or "dividend" in lname:
            continue
        score = -len(have - want)
        cand = {
            "scheme_code": parts[0].strip(),
            "scheme_name": scheme_name.strip(),
            "isin_growth": (parts[2] or "").strip() or (parts[1] or "").strip(),
        }
        if best is None or score > best[0]:
            best = (score, cand)

    if best:
        _cache_write(key, best[1])
        return best[1]
    return None


# ------------------------------- NAV history -------------------------------

def fetch_nav_history(scheme_code: str, ttl_hours: float = 12.0) -> List[Tuple[date, float]]:
    """Full NAV history (newest first from mfapi; we return oldest->newest)."""
    key = f"nav_{scheme_code}.json"
    payload = _cache_read(key, ttl_hours)
    if payload is None:
        try:
            import requests

            resp = requests.get(MFAPI_URL.format(code=scheme_code), timeout=20)
            resp.raise_for_status()
            payload = resp.json()
            _cache_write(key, payload)
        except Exception:
            log.warning("portfolio: mfapi fetch failed for %s; trying stale cache", scheme_code)
            payload = _cache_read(key, None)
    if not payload:
        return []
    out: List[Tuple[date, float]] = []
    for row in payload.get("data") or []:
        try:
            d = datetime.strptime(row["date"], "%d-%m-%Y").date()
            v = float(row["nav"])
            if v > 0:
                out.append((d, v))
        except Exception:
            continue
    out.sort(key=lambda t: t[0])
    return out


def _nav_on_or_before(history: List[Tuple[date, float]], target: date) -> Optional[float]:
    val = None
    for d, v in history:
        if d <= target:
            val = v
        else:
            break
    return val


def compute_fund_performance(history: List[Tuple[date, float]]) -> Dict[str, Any]:
    if not history:
        return {}
    latest_date, latest_nav = history[-1]
    def ret(days: int) -> Optional[float]:
        past = _nav_on_or_before(history, latest_date - timedelta(days=days))
        if past is None or past <= 0:
            return None
        return round((latest_nav / past - 1.0) * 100.0, 2)

    year_ago = latest_date - timedelta(days=365)
    window = [(d, v) for d, v in history if d >= year_ago]
    high_1y = max((v for _, v in window), default=None)
    drawdown_1y = (
        round((latest_nav / high_1y - 1.0) * 100.0, 2) if high_1y else None
    )
    return {
        "latest_nav": latest_nav,
        "latest_nav_date": latest_date.isoformat(),
        "ret_1m_pct": ret(30),
        "ret_3m_pct": ret(91),
        "ret_6m_pct": ret(182),
        "ret_1y_pct": ret(365),
        "ret_3y_pct": ret(365 * 3),
        "high_1y": high_1y,
        "drawdown_from_1y_high_pct": drawdown_1y,
    }


# --------------------------- NAV history (chart) ---------------------------

_RANGE_DAYS: Dict[str, Optional[int]] = {
    "1m": 31,
    "6m": 183,
    "1y": 366,
    "5y": 1830,
    "max": None,  # since inception
}

_MAX_CHART_POINTS = 800  # downsample cap so 20y of daily NAVs stays light


def build_nav_history(scheme_code: str, range_key: str = "1y") -> Dict[str, Any]:
    """NAV series for one scheme, sliced to a UI range and downsampled.

    Returns {scheme_code, range, points: [{date, nav}], first/last stats}."""
    rk = (range_key or "1y").strip().lower()
    if rk not in _RANGE_DAYS:
        rk = "1y"

    history = fetch_nav_history(str(scheme_code).strip())
    if not history:
        return {"scheme_code": scheme_code, "range": rk, "points": [], "error": "no NAV history"}

    days = _RANGE_DAYS[rk]
    if days is not None:
        cutoff = history[-1][0] - timedelta(days=days)
        series = [(d, v) for d, v in history if d >= cutoff]
    else:
        series = history

    # Downsample uniformly, always keeping first and last points.
    n = len(series)
    if n > _MAX_CHART_POINTS:
        step = n / float(_MAX_CHART_POINTS)
        idxs = sorted({int(i * step) for i in range(_MAX_CHART_POINTS)} | {n - 1})
        series = [series[i] for i in idxs]

    first_d, first_v = series[0]
    last_d, last_v = series[-1]
    change_pct = round((last_v / first_v - 1.0) * 100.0, 2) if first_v > 0 else None
    return {
        "scheme_code": scheme_code,
        "range": rk,
        "points": [{"date": d.isoformat(), "nav": v} for d, v in series],
        "first_date": first_d.isoformat(),
        "last_date": last_d.isoformat(),
        "first_nav": first_v,
        "last_nav": last_v,
        "change_pct": change_pct,
        "inception_date": history[0][0].isoformat(),
    }


# ---------------------------------- XIRR ----------------------------------

def xirr(cashflows: List[Tuple[date, float]]) -> Optional[float]:
    """Annualised IRR via bisection. Outflows negative, inflows positive."""
    flows = [(d, a) for d, a in cashflows if a]
    if len(flows) < 2:
        return None
    if not (any(a < 0 for _, a in flows) and any(a > 0 for _, a in flows)):
        return None
    t0 = min(d for d, _ in flows)

    def npv(rate: float) -> float:
        total = 0.0
        for d, a in flows:
            yrs = (d - t0).days / 365.25
            total += a / ((1.0 + rate) ** yrs)
        return total

    lo, hi = -0.9999, 10.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2.0
        f_mid = npv(mid)
        if abs(f_mid) < 1e-7:
            break
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    rate = (lo + hi) / 2.0
    if not math.isfinite(rate):
        return None
    return round(rate * 100.0, 2)


# ------------------------------ overview build ------------------------------

def build_overview(force_refresh: bool = False) -> Dict[str, Any]:
    cfg = load_portfolio_config()
    if not cfg:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "configured": False,
            "error": "configs/portfolio.yaml missing or invalid",
            "instruments": [],
        }

    accumulation = cfg.get("accumulation") or {}
    ttl = 0.0 if force_refresh else float(accumulation.get("nav_cache_ttl_hours") or 12)
    watch_dd = float(accumulation.get("drawdown_watch_pct") or 5.0)
    tranche_dd = float(accumulation.get("drawdown_tranche_pct") or 10.0)

    instruments = {i["id"]: i for i in (cfg.get("instruments") or []) if i.get("id")}
    holdings_cfg = cfg.get("holdings_config") or []
    txns = load_transactions()
    today = date.today()

    # holdings: (instrument, account) -> aggregates
    txn_by_key: Dict[Tuple[str, str], List[Txn]] = {}
    for t in txns:
        txn_by_key.setdefault((t.instrument_id, t.account_id), []).append(t)

    out_instruments: List[Dict[str, Any]] = []
    total_value = 0.0
    total_invested = 0.0
    alloc_by_category: Dict[str, float] = {}
    portfolio_flows: List[Tuple[date, float]] = []

    for inst_id, inst in instruments.items():
        entry: Dict[str, Any] = {
            "id": inst_id,
            "name": inst.get("name"),
            "type": inst.get("type"),
            "category": inst.get("category"),
            "plan": inst.get("plan"),
            "benchmark": inst.get("benchmark"),
            "links": inst.get("links") or {},
            "scheme_code": inst.get("amfi_scheme_code"),
            "scheme_name_resolved": None,
            "performance": {},
            "holdings": [],
            "totals": None,
            "accumulation": None,
        }

        history: List[Tuple[date, float]] = []
        if inst.get("type") == "mutual_fund":
            code = inst.get("amfi_scheme_code")
            if not code and inst.get("amfi_name_hint"):
                resolved = resolve_scheme_code(str(inst["amfi_name_hint"]))
                if resolved:
                    code = resolved["scheme_code"]
                    entry["scheme_code"] = code
                    entry["scheme_name_resolved"] = resolved["scheme_name"]
            if code:
                history = fetch_nav_history(str(code), ttl_hours=ttl)
                entry["performance"] = compute_fund_performance(history)

        latest_nav = (entry["performance"] or {}).get("latest_nav")

        # holdings per account
        inst_units = 0.0
        inst_invested = 0.0
        inst_flows: List[Tuple[date, float]] = []
        for hc in holdings_cfg:
            if hc.get("instrument_id") != inst_id:
                continue
            acct = hc.get("account_id")
            key = (inst_id, acct)
            units = 0.0
            invested = 0.0
            flows: List[Tuple[date, float]] = []
            for t in txn_by_key.get(key, []):
                sign = 1.0 if t.type in ("BUY", "SIP") else -1.0
                if t.units:
                    units += sign * t.units
                if t.amount:
                    invested += sign * t.amount
                    flows.append((t.date, -sign * t.amount))
            value = units * latest_nav if (latest_nav and units > 0) else None
            h = {
                "account_id": acct,
                "sip_amount": hc.get("sip_amount") or 0,
                "target_portfolio_pct": hc.get("target_portfolio_pct"),
                "accumulation_enabled": bool(hc.get("accumulation_enabled")),
                "units": round(units, 4) if units else 0,
                "invested": round(invested, 2) if invested else 0,
                "current_value": round(value, 2) if value is not None else None,
                "xirr_pct": None,
            }
            if value is not None and flows:
                h["xirr_pct"] = xirr(flows + [(today, value)])
            entry["holdings"].append(h)
            inst_units += max(units, 0.0)
            inst_invested += max(invested, 0.0)
            inst_flows.extend(flows)

        inst_value = inst_units * latest_nav if (latest_nav and inst_units > 0) else None
        if inst_invested or inst_value:
            entry["totals"] = {
                "units": round(inst_units, 4),
                "invested": round(inst_invested, 2),
                "current_value": round(inst_value, 2) if inst_value is not None else None,
                "abs_return_pct": (
                    round((inst_value / inst_invested - 1.0) * 100.0, 2)
                    if inst_value is not None and inst_invested > 0
                    else None
                ),
                "xirr_pct": xirr(inst_flows + [(today, inst_value)]) if (inst_value and inst_flows) else None,
            }
            if inst_value is not None:
                total_value += inst_value
                cat = str(inst.get("category") or "OTHER")
                alloc_by_category[cat] = alloc_by_category.get(cat, 0.0) + inst_value
            total_invested += inst_invested
            portfolio_flows.extend(inst_flows)

        out_instruments.append(entry)

    # second pass: accumulation signals (needs total_value for weight calc)
    for entry in out_instruments:
        inst_id = entry["id"]
        if entry.get("type") != "mutual_fund":
            continue
        enabled = any(h.get("accumulation_enabled") for h in entry["holdings"])
        if not enabled:
            continue
        perf = entry.get("performance") or {}
        dd = perf.get("drawdown_from_1y_high_pct")
        totals = entry.get("totals") or {}
        cur_val = totals.get("current_value")
        weight_pct = (
            round(cur_val * 100.0 / total_value, 2)
            if (cur_val is not None and total_value > 0)
            else None
        )
        target_pct = None
        for h in entry["holdings"]:
            if h.get("target_portfolio_pct") is not None:
                target_pct = (target_pct or 0) + float(h["target_portfolio_pct"])

        status = "no_action"
        reasons: List[str] = []
        if dd is not None:
            dd_abs = abs(min(dd, 0.0))
            if dd_abs >= tranche_dd:
                status = "tranche_eligible"
                reasons.append(f"NAV {dd_abs:.1f}% below 1y high (>= {tranche_dd:.0f}% threshold)")
            elif dd_abs >= watch_dd:
                status = "watch"
                reasons.append(f"NAV {dd_abs:.1f}% below 1y high (>= {watch_dd:.0f}% watch level)")
        if target_pct is not None and weight_pct is not None:
            gap = target_pct - weight_pct
            if gap > 1.0:
                reasons.append(f"Underweight vs target ({weight_pct:.1f}% vs {target_pct:.1f}%)")
                if status == "no_action":
                    status = "watch"
        if dd is None:
            reasons.append("NAV history unavailable")

        entry["accumulation"] = {
            "status": status,
            "drawdown_from_1y_high_pct": dd,
            "portfolio_weight_pct": weight_pct,
            "target_portfolio_pct": target_pct,
            "reasons": reasons,
        }

    allocation = [
        {
            "category": cat,
            "value": round(val, 2),
            "weight_pct": round(val * 100.0 / total_value, 2) if total_value > 0 else None,
        }
        for cat, val in sorted(alloc_by_category.items(), key=lambda kv: -kv[1])
    ]

    portfolio_xirr = None
    if total_value > 0 and portfolio_flows:
        portfolio_xirr = xirr(portfolio_flows + [(today, total_value)])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configured": True,
        "has_transactions": bool(txns),
        "summary": {
            "total_invested": round(total_invested, 2) if total_invested else None,
            "total_value": round(total_value, 2) if total_value else None,
            "abs_return_pct": (
                round((total_value / total_invested - 1.0) * 100.0, 2)
                if total_invested > 0 and total_value > 0
                else None
            ),
            "xirr_pct": portfolio_xirr,
        },
        "allocation": allocation,
        "instruments": out_instruments,
        "notes": [
            "NAV data: AMFI via api.mfapi.in, cached locally.",
            "XIRR/allocation appear once data/portfolio_transactions.csv is filled.",
            "Signals are rule-based information, not investment advice.",
        ],
    }
