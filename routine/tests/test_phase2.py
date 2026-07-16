"""Fetch merge logic, regime classification, screen pipeline, digest rendering."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from routine import fetch, regime, routine_config, screen, sizing, digest
from routine.regime import RegimeState
from routine.screen import ScreenResult
from routine.state import ExitEvent

# Screening tests pin their own thresholds: they verify the PIPELINE
# (indicators -> PBSS -> plan -> ranking), not the production threshold,
# which is a config choice validated by the Phase-1 backtest.
TCFG = routine_config.DailyConfig(pbss_watch=13, pbss_conviction=16, min_score=0)


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

def _bars(start: str, closes):
    d0 = date.fromisoformat(start)
    return pd.DataFrame(
        {
            "date": [d0 + timedelta(days=i) for i in range(len(closes))],
            "open": closes, "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes], "close": closes,
            "adj_close": closes, "volume": [1000] * len(closes),
        }
    )


def test_merge_new_bars_dedupes_and_sorts():
    a = _bars("2026-01-01", [10, 11, 12])
    b = _bars("2026-01-03", [12.5, 13])  # overlaps last day of a
    m = fetch.merge_new_bars(a, b)
    assert len(m) == 4
    assert m["close"].tolist() == [10, 11, 12.5, 13]  # overlap: new wins


def test_update_symbols_incremental(tmp_path, monkeypatch):
    monkeypatch.setattr(routine_config, "OHLCV_DIR", tmp_path)
    monkeypatch.setattr(routine_config, "ROUTINE_DATA", tmp_path)
    monkeypatch.setattr(routine_config, "OUT_DIR", tmp_path)
    calls = []

    def fake_downloader(tickers, start):
        calls.append((tuple(tickers), start))
        return {t: _bars(start.isoformat(), [100, 101]) for t in tickers}

    today = date(2026, 1, 10)
    res = fetch.update_symbols(["AAA"], downloader=fake_downloader, backfill_days=5, today=today)
    assert res["AAA"] == 2
    # second run: starts after last stored bar
    res2 = fetch.update_symbols(["AAA"], downloader=fake_downloader, today=today)
    assert calls[-1][1] > calls[0][1]

    def broken(tickers, start):
        raise RuntimeError("network down")

    res3 = fetch.update_symbols(["AAA", "BBB"], downloader=broken, today=date(2026, 3, 1))
    assert res3["AAA"] == -1 and res3["BBB"] == -1  # loud, per-symbol failure


# ---------------------------------------------------------------------------
# regime
# ---------------------------------------------------------------------------

def test_regime_classification():
    r = regime._classify(close=110, dma200=100, slope20=1.0, vix=12.0)
    assert r.label == "RISK_ON" and r.size_multiplier == 1.0
    r = regime._classify(close=110, dma200=100, slope20=-1.0, vix=None)
    assert r.label == "CAUTION" and r.size_multiplier == 0.5
    r = regime._classify(close=90, dma200=100, slope20=-1.0, vix=None)
    assert r.label == "RISK_OFF" and not r.allow_new_buys
    # VIX shock downgrades RISK_ON -> CAUTION
    r = regime._classify(close=110, dma200=100, slope20=1.0, vix=25.0)
    assert r.label == "CAUTION"


# ---------------------------------------------------------------------------
# screen (end-to-end on synthetic OHLCV)
# ---------------------------------------------------------------------------

def _surging_ohlcv(n=300) -> pd.DataFrame:
    """Uptrend into a high-volume accumulation burst near 52w high."""
    rng = np.random.default_rng(7)
    base = 100 * np.cumprod(1 + rng.normal(0.0015, 0.004, n))
    close = base.copy()
    close[-5:] = close[-6] * np.cumprod([1.012, 1.015, 1.012, 1.01, 1.012])
    vol = np.full(n, 1_000_000.0)
    vol[-4:] = 5_200_000.0  # z-score & relvol blowout
    d0 = date(2025, 1, 1)
    return pd.DataFrame(
        {
            "date": [d0 + timedelta(days=i) for i in range(n)],
            "open": close * 0.998, "high": close * 1.012, "low": close * 0.99,
            "close": close, "adj_close": close, "volume": vol,
        }
    )


@pytest.fixture
def stocked_store(tmp_path, monkeypatch):
    monkeypatch.setattr(routine_config, "OHLCV_DIR", tmp_path)
    monkeypatch.setattr(routine_config, "ROUTINE_DATA", tmp_path)
    monkeypatch.setattr(routine_config, "OUT_DIR", tmp_path)
    fetch.save_ohlcv("SURG", _surging_ohlcv())
    flat = _surging_ohlcv()
    flat["close"] = 100.0
    flat["volume"] = 100.0  # illiquid too
    fetch.save_ohlcv("DEAD", flat)
    return tmp_path


def test_screen_finds_the_surger(stocked_store):
    reg = RegimeState("RISK_ON", 1.0, True, "test")
    uni = pd.DataFrame({"symbol": ["SURG", "DEAD"], "name": ["Surger", "Dead"], "sector": ["X", "Y"]})
    res = screen.run_screen(uni, reg, cfg=TCFG)
    assert res.scanned == 2
    assert [i.symbol for i in res.ideas] == ["SURG"]
    idea = res.ideas[0]
    assert idea.pbss >= TCFG.pbss_watch
    assert idea.plan.qty >= 1 and idea.plan.stop < idea.plan.entry < idea.plan.t1 < idea.plan.t2
    assert idea.reasons  # human-readable reasons present


def test_screen_respects_cooldown_and_regime(stocked_store):
    uni = pd.DataFrame({"symbol": ["SURG"], "name": ["Surger"], "sector": ["X"]})
    reg = RegimeState("RISK_ON", 1.0, True, "test")
    res = screen.run_screen(uni, reg, recent_alert_symbols={"SURG"}, cfg=TCFG)
    assert res.ideas == [] and res.candidates_above_watch == 1
    # RISK_OFF: no plan can be built (multiplier 0) -> no ideas
    off = RegimeState("RISK_OFF", 0.0, False, "test")
    res2 = screen.run_screen(uni, off, cfg=TCFG)
    assert res2.ideas == []


# ---------------------------------------------------------------------------
# digest
# ---------------------------------------------------------------------------

def _sample_result(stocked_store):
    reg = RegimeState("RISK_ON", 1.0, True, "Nifty +2.1% vs 200DMA, 20d slope +")
    uni = pd.DataFrame({"symbol": ["SURG"], "name": ["Surger Ltd"], "sector": ["Auto"]})
    return reg, screen.run_screen(uni, reg, cfg=TCFG)


def test_digest_renders_clean_html(stocked_store):
    reg, res = _sample_result(stocked_store)
    exits = [ExitEvent("OLDPOS", "STOP", "SELL_ALL", 95.2, -4.8, "close 95.20 <= stop 96.00")]
    html = digest.render_html(
        today=date(2026, 7, 6), regime=reg, screen_res=res, exit_events=exits,
        open_positions=[], outcome={"n": 12, "avg_fwd21": 3.4, "hit10_pct": 25.0, "win_pct": 58.0},
        data_date=date(2026, 7, 6),
    )
    assert "None" not in html            # the old app's 'Sector: None' disease
    assert "SURG" in html and "OLDPOS" in html
    assert "-4.8%" in html               # signed, 1-decimal formatting
    assert "PBSS" in html and "₹" in html
    assert "STALE DATA" not in html


def test_digest_stale_data_warning(stocked_store):
    reg, res = _sample_result(stocked_store)
    html = digest.render_html(
        today=date(2026, 7, 6), regime=reg, screen_res=res, exit_events=[],
        open_positions=[], outcome=None, data_date=date(2026, 6, 20),
    )
    assert "STALE DATA" in html


def test_digest_subject(stocked_store):
    reg, res = _sample_result(stocked_store)
    subj = digest.render_subject(date(2026, 7, 6), res, [], reg)
    assert "SURG" in subj and "RISK-ON" in subj
    empty = ScreenResult(ideas=[], scanned=10)
    subj2 = digest.render_subject(date(2026, 7, 6), empty, [], reg)
    assert "no action" in subj2
