"""Daily screen: OHLCV -> indicators -> score -> PBSS -> ranked trade ideas.

Thresholds are the backtest-validated ones (PLAN.md). Every idea ships with a
complete TradePlan (entry/stop/T1/T2/qty) or it doesn't ship at all.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from . import fetch, indicators, pbss, routine_config, scoring, sizing
from .regime import RegimeState

log = logging.getLogger(__name__)


@dataclass
class Idea:
    symbol: str
    name: str
    sector: str
    pbss: int
    score: Optional[int]
    close: float
    plan: Optional[sizing.TradePlan] = None   # None => informational only (watchlist)
    conviction: str = "WATCH"                 # WATCH | HIGH
    reasons: List[str] = field(default_factory=list)
    features: Dict[str, float] = field(default_factory=dict)
    qualified: bool = True     # passed the full alert rule (PBSS & score gates)
    note: str = ""             # watchlist context: what is missing / what blocks it


@dataclass
class ScreenResult:
    ideas: List[Idea]
    watchlist: List[Idea] = field(default_factory=list)  # forming setups, NOT buys
    scanned: int = 0
    skipped_short_history: int = 0
    skipped_illiquid: int = 0
    candidates_above_watch: int = 0


def _last_row_inputs(ind: pd.DataFrame, close: float) -> Dict:
    row = ind.iloc[-1]

    def g(col: str):
        v = row.get(col)
        return None if pd.isna(v) else float(v)

    return {
        "close": close,
        "ema10": g("ema10"),
        "ema50": g("ema50"),
        "ema200": g("ema200"),
        "rsi14": g("rsi14"),
        "adx14": g("adx14"),
        "adx_slope_pos": bool(g("adx_slope_pos") or 0),
        "relvol20": g("relvol20"),
        "vol_z20": g("vol_z20"),
        "obv_above_ma": bool(g("obv_above_ma") or 0),
        "obv_slope_10": g("obv_slope_10"),
        "proximity_52w_high_pct": g("proximity_52w_high_pct"),
        "pivot_clear_pct": g("pivot_clear_pct"),
        "n_consecutive_up": g("n_consecutive_up"),
        "ret_5d": g("ret_5d"),
        "ret_1m": g("ret_1m"),
        "ret_3m": g("ret_3m"),
        "gap_up_pct": g("gap_up_pct"),
        "close_pos_in_bar": g("close_pos_in_bar"),
        "atr14_pct": g("atr14_pct"),
        "pivot_high_20": g("pivot_high_20"),
        "median_traded_value_20d": g("median_traded_value_20d"),
    }


def _reasons(inp: Dict, pbss_val: int) -> List[str]:
    out = []
    if (inp.get("vol_z20") or 0) >= 2.0:
        out.append(f"volume {inp['vol_z20']:.1f} std above normal")
    if (inp.get("relvol20") or 0) >= 1.8:
        out.append(f"{inp['relvol20']:.1f}x average volume")
    if inp.get("obv_above_ma"):
        out.append("OBV accumulation")
    prox = inp.get("proximity_52w_high_pct")
    if prox is not None and prox >= -8:
        out.append(f"{abs(prox):.1f}% from 52w high")
    r5 = inp.get("ret_5d")
    if r5 is not None and r5 >= 3:
        out.append(f"{r5:+.1f}% in 5 days")
    if not out:
        out.append(f"PBSS {pbss_val} composite signal")
    return out[:3]


def screen_symbol(symbol: str, meta: Dict[str, str], regime: RegimeState,
                  cfg: Optional[routine_config.DailyConfig] = None) -> Optional[Idea]:
    cfg = cfg or routine_config.DAILY
    df = fetch.load_ohlcv(symbol)
    if len(df) < cfg.min_history_rows:
        return None
    ind = indicators.compute_indicator_frame(df.set_index("date"))
    close = float(pd.to_numeric(df["close"], errors="coerce").iloc[-1])
    inp = _last_row_inputs(ind, close)

    liq = inp.get("median_traded_value_20d")
    if liq is None or liq < cfg.liquidity_floor_rupees:
        return None

    bundle = scoring.compute_score(inp)
    score_val = bundle.score_full if bundle.score_full is not None else bundle.score_basic
    inp["score"] = score_val
    pbss_val = pbss.compute_pbss_row(inp)

    def _mk(plan, qualified, note, conviction="WATCH"):
        return Idea(
            symbol=symbol,
            name=meta.get("name") or symbol,
            sector=meta.get("sector") or "—",
            pbss=pbss_val,
            score=score_val,
            close=close,
            plan=plan,
            conviction=conviction,
            reasons=_reasons(inp, pbss_val),
            features={k: v for k, v in inp.items() if isinstance(v, (int, float)) and v is not None},
            qualified=qualified,
            note=note,
        )

    # Full alert rule: PBSS gate AND composite-score gate (backtest: the
    # combination PBSS>=18 & score>=79 carries the edge; either alone is
    # marginal-to-negative. PLAN.md).
    qualified = pbss_val >= cfg.pbss_watch and (
        not cfg.min_score or (score_val is not None and score_val >= cfg.min_score)
    )
    if not qualified:
        # near-miss: strong enough to watch, not strong enough to trade
        if pbss_val >= cfg.watchlist_pbss_min or (score_val or 0) >= cfg.watchlist_score_min:
            return _mk(None, False,
                       f"forming: PBSS {pbss_val} / score {score_val if score_val is not None else 0} "
                       f"(rule needs {cfg.pbss_watch} & {cfg.min_score})")
        return None

    plan = sizing.build_plan(
        close=close,
        atr_pct=inp.get("atr14_pct") or 0.0,
        capital=cfg.capital_rupees,
        risk_pct=cfg.risk_pct_per_trade,
        stop_atr_mult=cfg.stop_atr_mult,
        t1_gain_pct=cfg.t1_gain_pct,
        t2_gain_pct=cfg.t2_gain_pct,
        pivot=inp.get("pivot_high_20"),
        size_multiplier=regime.size_multiplier if regime.allow_new_buys else 0.0,
    )
    conviction = "HIGH" if pbss_val >= cfg.pbss_conviction else "WATCH"
    if plan is None:
        # passes the alert rule but no tradeable plan: regime gate or bad ATR
        blocked = ("regime blocks new buys" if not regime.allow_new_buys or regime.size_multiplier <= 0
                   else "no tradeable plan (ATR/qty)")
        return _mk(None, True, "passes alert rule — " + blocked, conviction)
    return _mk(plan, True, "", conviction)


def run_screen(universe_df: pd.DataFrame, regime: RegimeState,
               recent_alert_symbols: Optional[set] = None,
               cfg: Optional[routine_config.DailyConfig] = None) -> ScreenResult:
    cfg = cfg or routine_config.DAILY
    recent = {s.upper() for s in (recent_alert_symbols or set())}
    res = ScreenResult(ideas=[])
    candidates: List[Idea] = []
    watch: List[Idea] = []
    for row in universe_df.itertuples():
        sym = str(row.symbol).upper()
        if sym.startswith("^"):
            continue
        res.scanned += 1
        try:
            idea = screen_symbol(
                sym,
                {"name": getattr(row, "name", sym), "sector": getattr(row, "sector", "")},
                regime,
                cfg,
            )
        except Exception as exc:
            log.warning("screen failed for %s: %s", sym, exc)
            continue
        if idea is None:
            continue
        if not idea.qualified:
            watch.append(idea)
            continue
        res.candidates_above_watch += 1
        if idea.plan is None:
            watch.append(idea)  # passes rule, blocked (regime/plan): show, don't trade
            continue
        if sym in recent:
            continue  # cooldown: already alerted recently
        candidates.append(idea)

    candidates.sort(key=lambda i: (i.pbss, i.features.get("vol_z20", 0)), reverse=True)
    res.ideas = candidates[: cfg.max_ideas]
    # overflow (qualified beyond max_ideas) also worth watching
    watch = candidates[cfg.max_ideas:] + watch
    watch.sort(key=lambda i: (i.pbss, i.score or 0), reverse=True)
    res.watchlist = watch[: cfg.watchlist_size]
    return res
