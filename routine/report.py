"""Render backtest results to console, CSV, and markdown."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from . import config
from .backtest import BacktestResult


def _fmt(df) -> str:
    if df is None or df.empty:
        return "(no rows)"
    return df.to_string(index=False)


def render_text(res: BacktestResult) -> str:
    cfg = res.config_used or config.DEFAULT_CONFIG
    lines = []
    lines.append("=" * 78)
    lines.append("PBSS / SCORE BACKTEST")
    lines.append(f"period: {res.date_range}   trading_days: {res.n_days}   rows: {res.n_rows:,}")
    for n in res.notes:
        lines.append(f"note: {n}")
    lines.append(
        f"definitions: hit = close-to-close >= {cfg.hit_gain_pct:.0f}% after {max(cfg.fwd_windows)} TD; "
        f"surge = max close within {cfg.surge_window} TD >= {cfg.surge_gain_pct:.0f}%; "
        f"liquidity floor = Rs {cfg.liquidity_floor_rupees:,.0f}/day"
    )
    lines.append("")
    lines.append("--- PBSS buckets (all eligible symbol-days) " + "-" * 30)
    lines.append(_fmt(res.bucket_stats))
    lines.append("")
    lines.append(f"--- Alert rules (first trigger per episode, cooldown={cfg.cooldown_days} TD) ---")
    lines.append(_fmt(res.threshold_stats))
    lines.append("")
    lines.append("--- Regime split (breadth-based, computed from the panel) " + "-" * 15)
    lines.append(_fmt(res.regime_stats))
    lines.append("")
    lines.append("--- App composite score bands " + "-" * 44)
    lines.append(_fmt(res.score_band_stats))
    lines.append("")
    lines.append("READ ME BEFORE TRUSTING:")
    lines.append(" * 'surge' uses the max close in the window — you cannot reliably sell the top;")
    lines.append("   fwd21_mean/median is closer to what a real exit rule would capture.")
    lines.append(" * Compare every rule row against the ALL(baseline) row; edge = difference, not the raw number.")
    lines.append(" * Costs/slippage are NOT included; subtract ~0.3-0.5% per round trip for NSE retail.")
    return "\n".join(lines)


def save(res: BacktestResult, out_dir: Optional[Path] = None) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = (out_dir or config.reports_dir()) / f"backtest_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    res.bucket_stats.to_csv(out / "pbss_buckets.csv", index=False)
    res.threshold_stats.to_csv(out / "alert_rules.csv", index=False)
    res.regime_stats.to_csv(out / "regime_split.csv", index=False)
    res.score_band_stats.to_csv(out / "score_bands.csv", index=False)
    (out / "report.txt").write_text(render_text(res), encoding="utf-8")
    return out
