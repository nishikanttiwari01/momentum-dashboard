"""The one daily email. Formatted numbers, real statistics, complete plans.

Sections: regime header, exit instructions (open trades), 0-3 entry ideas
with full trade plans, live outcome tracker, data freshness, measured stats.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from . import routine_config
from .regime import RegimeState
from .screen import Idea, ScreenResult
from .state import ExitEvent

CSS = """
body{font-family:Segoe UI,Arial,sans-serif;color:#1a1a1a;max-width:720px;margin:auto}
h2{font-size:18px;border-bottom:2px solid #333;padding-bottom:4px}
h3{font-size:15px;margin:18px 0 6px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border:1px solid #ccc;padding:6px 8px;text-align:right}
th:first-child,td:first-child{text-align:left}
th{background:#f0f0f0}
.regime-RISK_ON{color:#0a7a2f;font-weight:bold}
.regime-CAUTION{color:#b8860b;font-weight:bold}
.regime-RISK_OFF{color:#b22222;font-weight:bold}
.regime-UNKNOWN{color:#666;font-weight:bold}
.exit{background:#fff3f3}
.small{color:#666;font-size:12px}
.warn{background:#fff3cd;padding:8px;border:1px solid #e0c060}
"""


def _pct(v: Optional[float], signed: bool = True) -> str:
    if v is None:
        return "—"
    return f"{v:+.1f}%" if signed else f"{v:.1f}%"


def _rs(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"₹{v:,.2f}" if v < 1000 else f"₹{v:,.0f}"


def render_html(
    today: date,
    regime: RegimeState,
    screen_res: ScreenResult,
    exit_events: List[ExitEvent],
    open_positions: List[Dict],
    outcome: Optional[Dict],
    data_date: Optional[date],
    fetch_failures: int = 0,
    movers: Optional[Dict] = None,
    dips: Optional[List] = None,
) -> str:
    cfg = routine_config.DAILY
    parts: List[str] = [f"<html><head><style>{CSS}</style></head><body>"]
    parts.append(f"<h2>Momentum Digest — {today.strftime('%a %d %b %Y')}</h2>")

    # freshness warning first: never trade on stale data silently
    if data_date is None:
        parts.append("<div class='warn'>NO PRICE DATA FOUND — do not act on this email.</div>")
    else:
        age = (today - data_date).days
        if age > cfg.stale_data_max_age_days:
            parts.append(
                f"<div class='warn'>STALE DATA: newest bar is {data_date.isoformat()} "
                f"({age} days old). Signals below are unreliable.</div>"
            )
    if fetch_failures:
        parts.append(f"<p class='small'>note: {fetch_failures} symbols failed to update today.</p>")

    parts.append(
        f"<p>Market: <span class='regime-{regime.label}'>{regime.label.replace('_', '-')}</span>"
        f" — {regime.description}. Position sizing ×{regime.size_multiplier:.1f}"
        f"{'' if regime.allow_new_buys else ' — NO NEW BUYS'}.</p>"
    )

    # ---- exits (most important) ----
    if exit_events:
        parts.append("<h3>Action required — open positions</h3><table class='exit'>")
        parts.append("<tr><th>Symbol</th><th>Signal</th><th>Action</th><th>Close</th><th>P/L</th><th>Why</th></tr>")
        for e in exit_events:
            parts.append(
                f"<tr><td>{e.symbol}</td><td>{e.reason}</td><td>{e.action.replace('_', ' ')}</td>"
                f"<td>{_rs(e.price)}</td><td>{_pct(e.pnl_pct)}</td><td style='text-align:left'>{e.detail}</td></tr>"
            )
        parts.append("</table>")
    elif open_positions:
        parts.append("<h3>Open positions — no action needed</h3><table>")
        parts.append("<tr><th>Symbol</th><th>Entry</th><th>Qty</th><th>Stop</th><th>T1</th><th>T2</th></tr>")
        for t in open_positions:
            parts.append(
                f"<tr><td>{t['symbol']}</td><td>{_rs(t['entry_price'])}</td><td>{t['qty']}</td>"
                f"<td>{_rs(t['stop'])}</td><td>{_rs(t['t1'])}</td><td>{_rs(t['t2'])}</td></tr>"
            )
        parts.append("</table>")

    # ---- ideas ----
    if screen_res.ideas:
        parts.append(f"<h3>New ideas ({len(screen_res.ideas)})</h3>")
        for i in screen_res.ideas:
            p = i.plan
            parts.append(
                f"<table><tr><th colspan='6' style='text-align:left'>{i.symbol} — {i.name}"
                f" &nbsp;<span class='small'>{i.sector} | PBSS {i.pbss} ({i.conviction})"
                f" | score {i.score if i.score is not None else '—'}</span></th></tr>"
                f"<tr><th>Entry</th><th>Stop</th><th>T1</th><th>T2</th><th>Qty</th><th>Risk</th></tr>"
                f"<tr><td>{_rs(p.entry)}</td><td>{_rs(p.stop)}</td><td>{_rs(p.t1)}</td>"
                f"<td>{_rs(p.t2)}</td><td>{p.qty}</td><td>{_rs(p.risk_rupees)}</td></tr>"
                f"<tr><td colspan='6' style='text-align:left' class='small'>{'; '.join(i.reasons)}."
                f" Position {_rs(p.position_rupees)} ({p.position_rupees / routine_config.DAILY.capital_rupees * 100:.0f}% of capital)</td></tr></table><br>"
            )
    else:
        reason = "no new buys in this regime" if not regime.allow_new_buys else \
            f"nothing above PBSS {cfg.pbss_watch} today (scanned {screen_res.scanned})"
        parts.append(f"<h3>New ideas</h3><p>None — {reason}. Cash is a position.</p>")

    # ---- watchlist: forming setups, explicitly NOT buys ----
    if screen_res.watchlist:
        parts.append(f"<h3>Watchlist — forming setups ({len(screen_res.watchlist)}) · NOT buys</h3><table>")
        parts.append("<tr><th>Symbol</th><th>PBSS</th><th>Score</th><th>Close</th><th>Status</th></tr>")
        for w in screen_res.watchlist:
            score_disp = w.score if w.score is not None else "—"
            parts.append(
                f"<tr><td>{w.symbol} <span class='small'>{w.name}</span></td>"
                f"<td>{w.pbss}</td><td>{score_disp}</td>"
                f"<td>{_rs(w.close)}</td><td style='text-align:left' class='small'>{w.note}</td></tr>"
            )
        parts.append("</table>")
        parts.append("<p class='small'>Watchlist = closest to triggering the alert rule, or blocked by "
                     "the regime gate. No trade plans on purpose: the measured edge only exists at the full rule.</p>")

    # ---- movers: context, never signals ----
    if movers and (movers.get("gainers") or movers.get("losers")):
        parts.append("<h3>Today's movers · context, not signals</h3>")
        for label, key in (("Top gainers", "gainers"), ("Top losers", "losers")):
            items = movers.get(key) or []
            if not items:
                continue
            parts.append(f"<table><tr><th>{label}</th><th>Close</th><th>Day</th><th>Vol vs 20d</th></tr>")
            for m in items:
                parts.append(
                    f"<tr><td>{m['symbol']} <span class='small'>{m.get('name', '')}</span></td>"
                    f"<td>{_rs(m['close'])}</td><td>{m['chg_pct']:+.1f}%</td><td>{m.get('relvol') or 0:.1f}x</td></tr>"
                )
            parts.append("</table>")
        parts.append(f"<p class='small'>{routine_config.MOVERS_NOTE}</p>")

    # ---- index dip: measured mean-reversion, separate capital ----
    if dips:
        parts.append("<h3>Index dip (ETF mean reversion) · separate capital</h3><table>")
        parts.append("<tr><th>Index</th><th>ETF</th><th>RSI2</th><th>vs 200DMA</th><th>Status</th><th style='text-align:left'>Action</th></tr>")
        for d in dips:
            rsi_disp = d.rsi2 if d.rsi2 is not None else "—"
            gap_disp = f"{d.dma_gap_pct:+.1f}%" if d.dma_gap_pct is not None else "—"
            if d.label == "BUY_TODAY":
                action = f"BUY at close {_rs(d.close)} — exit first close above entry, max hold applies"
            elif d.label == "HOLD":
                action = f"HOLD (entry {_rs(d.entry)}, day {d.days_held}) — exit first close above entry"
            elif d.label == "EXIT_TODAY":
                action = f"SELL — {d.note}"
            elif d.label == "OFF_SEASON":
                action = "stand aside — " + d.note
            elif d.label == "NO_DATA":
                action = d.note
            else:
                action = d.note
            parts.append(
                f"<tr><td>{d.index_name}</td><td>{d.etf}</td><td>{rsi_disp}</td><td>{gap_disp}</td>"
                f"<td>{d.label.replace('_', ' ')}</td><td style='text-align:left' class='small'>{action}</td></tr>"
            )
        parts.append("</table>")
        parts.append(f"<p class='small'>{routine_config.INDEX_DIP_STATS}</p>")

    # ---- live outcome tracker ----
    parts.append("<h3>How past alerts actually did</h3>")
    if outcome and outcome.get("n"):
        parts.append(
            f"<p>{outcome['n']} labeled alerts so far: avg 21-day return "
            f"<b>{_pct(outcome['avg_fwd21'])}</b>, win rate {outcome['win_pct']:.0f}%, "
            f"≥10% hits {outcome['hit10_pct']:.0f}%.</p>"
        )
    else:
        parts.append("<p class='small'>No labeled outcomes yet (labels arrive 21 trading days after each alert).</p>")

    # ---- measured backtest stats (the honest table) ----
    parts.append("<h3 class='small'>Backtest reference (2025-06 → 2026-06, costs excluded)</h3><table>")
    parts.append("<tr><th>Rule</th><th>n</th><th>21d mean</th><th>21d median</th><th>win</th><th>≥10%</th></tr>")
    for rule, n, mean, med, win, hit in routine_config.MEASURED_STATS:
        parts.append(f"<tr><td>{rule}</td><td>{n:,}</td><td>{mean}</td><td>{med}</td><td>{win}</td><td>{hit}</td></tr>")
    parts.append("</table>")
    parts.append(
        "<p class='small'>Signals are systematic, not advice. Data: Yahoo Finance EOD. "
        f"Scanned {screen_res.scanned} symbols; {screen_res.candidates_above_watch} above threshold "
        f"before cooldown/ranking.</p>"
    )
    parts.append("</body></html>")
    return "".join(parts)


def render_subject(today: date, screen_res: ScreenResult, exit_events: List[ExitEvent],
                   regime: RegimeState, dips: Optional[List] = None) -> str:
    bits = []
    if exit_events:
        bits.append(f"{len(exit_events)} EXIT")
    for d in dips or []:
        if d.label in ("BUY_TODAY", "EXIT_TODAY"):
            bits.append(f"{d.etf} dip {'BUY' if d.label == 'BUY_TODAY' else 'SELL'}")
    if screen_res.ideas:
        top = screen_res.ideas[0]
        bits.append(f"{len(screen_res.ideas)} idea(s): {top.symbol} PBSS {top.pbss}")
    elif screen_res.watchlist:
        bits.append(f"{len(screen_res.watchlist)} watching")
    if not bits:
        bits.append("no action")
    return f"[Momentum {today.isoformat()}] {' | '.join(bits)} ({regime.label.replace('_', '-')})"
