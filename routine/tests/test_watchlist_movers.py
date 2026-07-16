"""Watchlist (near-miss + regime-blocked) and movers sections."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from routine import digest, fetch, movers, routine_config, screen
from routine.regime import RegimeState


def _surging_ohlcv(n=300) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    base = 100 * np.cumprod(1 + rng.normal(0.0015, 0.004, n))
    close = base.copy()
    close[-5:] = close[-6] * np.cumprod([1.012, 1.015, 1.012, 1.01, 1.012])
    vol = np.full(n, 1_000_000.0)
    vol[-4:] = 5_200_000.0
    d0 = date(2025, 1, 1)
    return pd.DataFrame(
        {
            "date": [d0 + timedelta(days=i) for i in range(n)],
            "open": close * 0.998, "high": close * 1.012, "low": close * 0.99,
            "close": close, "adj_close": close, "volume": vol,
        }
    )


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(routine_config, "OHLCV_DIR", tmp_path)
    monkeypatch.setattr(routine_config, "ROUTINE_DATA", tmp_path)
    monkeypatch.setattr(routine_config, "OUT_DIR", tmp_path)
    fetch.save_ohlcv("SURG", _surging_ohlcv())
    flat = _surging_ohlcv()
    flat["close"] = 100.0
    flat["volume"] = 100.0  # illiquid
    fetch.save_ohlcv("DEAD", flat)
    slid = _surging_ohlcv()
    slid["close"] = slid["close"].iloc[0] * 2 - slid["close"]  # mirrored: down day
    slid["volume"] = 2_000_000.0
    fetch.save_ohlcv("SLID", slid)
    return tmp_path


UNI = pd.DataFrame(
    {"symbol": ["SURG", "DEAD", "SLID"], "name": ["Surger", "Dead", "Slider"], "sector": ["X", "Y", "Z"]}
)


def test_near_miss_lands_on_watchlist_not_ideas(store):
    # impossible PBSS gate -> nothing qualifies; SURG is a near-miss via watchlist floor
    cfg = routine_config.DailyConfig(
        pbss_watch=99, pbss_conviction=99, min_score=0, watchlist_pbss_min=13, watchlist_score_min=101
    )
    reg = RegimeState("RISK_ON", 1.0, True, "test")
    res = screen.run_screen(UNI, reg, cfg=cfg)
    assert res.ideas == []
    syms = [w.symbol for w in res.watchlist]
    assert "SURG" in syms and "DEAD" not in syms
    w = next(x for x in res.watchlist if x.symbol == "SURG")
    assert not w.qualified and w.plan is None and "forming" in w.note


def test_regime_blocked_idea_shows_on_watchlist(store):
    cfg = routine_config.DailyConfig(pbss_watch=13, pbss_conviction=16, min_score=0)
    off = RegimeState("RISK_OFF", 0.0, False, "test")
    res = screen.run_screen(UNI, off, cfg=cfg)
    assert res.ideas == []  # regime gate holds
    w = next(x for x in res.watchlist if x.symbol == "SURG")
    assert w.qualified and w.plan is None and "regime" in w.note


def test_movers_liquid_only(store):
    cfg = routine_config.DailyConfig()
    mov = movers.compute_movers(UNI, cfg=cfg)
    gsyms = [m["symbol"] for m in mov["gainers"]]
    lsyms = [m["symbol"] for m in mov["losers"]]
    assert "SURG" in gsyms          # +1.2% up day, liquid
    assert "DEAD" not in gsyms + lsyms   # illiquid excluded
    assert "SLID" in lsyms          # down day, liquid
    assert all(m["chg_pct"] > 0 for m in mov["gainers"])
    assert all(m["chg_pct"] < 0 for m in mov["losers"])


def test_digest_renders_watchlist_and_movers(store):
    cfg = routine_config.DailyConfig(pbss_watch=13, pbss_conviction=16, min_score=0)
    off = RegimeState("RISK_OFF", 0.0, False, "Nifty -2.6% vs 200DMA")
    res = screen.run_screen(UNI, off, cfg=cfg)
    mov = movers.compute_movers(UNI)
    html = digest.render_html(
        today=date(2026, 7, 11), regime=off, screen_res=res, exit_events=[],
        open_positions=[], outcome=None, data_date=date(2026, 7, 11), movers=mov,
    )
    assert "Watchlist" in html and "NOT buys" in html
    assert "SURG" in html
    assert "Top gainers" in html and "Top losers" in html
    assert "context, not signals" in html
    # no leaked Python None values in cells (the prose "None " no-ideas line is fine)
    assert ">None<" not in html and "None</td>" not in html
    # subject mentions watching when no ideas
    subj = digest.render_subject(date(2026, 7, 11), res, [], off)
    assert "watching" in subj
