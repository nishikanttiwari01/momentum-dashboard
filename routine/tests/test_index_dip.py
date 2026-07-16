"""Index dip signal: entry gate, hold/exit reconstruction, digest rendering."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from routine import digest, index_dip, routine_config
from routine.regime import RegimeState
from routine.screen import ScreenResult

CFG = routine_config.DailyConfig()


def _uptrend(n=260, drift=0.001):
    return list(100 * np.cumprod(1 + np.full(n, drift)))


def test_buy_today_on_oversold_above_200dma():
    c = _uptrend()
    c.append(c[-1] * 0.99)  # one sharp down close -> RSI2 ~9
    st = index_dip.evaluate_series(pd.Series(c), "NIFTY", "NIFTYBEES", CFG)
    assert st.label == "BUY_TODAY"
    assert st.rsi2 is not None and st.rsi2 < CFG.dip_rsi2_max
    assert st.above_200dma is True
    assert st.entry == round(c[-1], 2)


def test_hold_then_exit_on_first_up_close():
    c = _uptrend()
    c.append(c[-1] * 0.99)
    entry = c[-1]
    c.append(entry * 0.999)  # still below entry -> HOLD
    st = index_dip.evaluate_series(pd.Series(c), "NIFTY", "NIFTYBEES", CFG)
    assert st.label == "HOLD" and st.days_held == 1 and st.entry == round(entry, 2)
    c.append(entry * 1.004)  # first close above entry -> EXIT_TODAY
    st2 = index_dip.evaluate_series(pd.Series(c), "NIFTY", "NIFTYBEES", CFG)
    assert st2.label == "EXIT_TODAY" and "up-close" in st2.note


def test_timeout_exit():
    c = _uptrend()
    c.append(c[-1] * 0.99)
    entry = c[-1]
    for _ in range(CFG.dip_max_hold_td):
        c.append(entry * 0.995)  # never recovers
    st = index_dip.evaluate_series(pd.Series(c), "NIFTY", "NIFTYBEES", CFG)
    assert st.label == "EXIT_TODAY" and "timeout" in st.note


def test_off_season_below_200dma():
    c = list(100 * np.cumprod(1 + np.full(260, -0.002)))  # downtrend
    c += [c[-1] * 0.99, c[-1] * 0.981, c[-1] * 0.972]     # oversold too
    st = index_dip.evaluate_series(pd.Series(c), "NIFTY", "NIFTYBEES", CFG)
    assert st.label == "OFF_SEASON" and st.above_200dma is False


def test_no_data():
    st = index_dip.evaluate_series(pd.Series([100.0] * 50), "BANKNIFTY", "BANKBEES", CFG)
    assert st.label == "NO_DATA"


def test_digest_renders_dip_section_and_subject():
    c = _uptrend()
    c.append(c[-1] * 0.99)
    buy = index_dip.evaluate_series(pd.Series(c), "NIFTY", "NIFTYBEES", CFG)
    off = index_dip.DipStatus("BANKNIFTY", "BANKBEES", "OFF_SEASON", rsi2=8.0,
                              above_200dma=False, dma_gap_pct=-2.5, close=51000.0,
                              note="below 200DMA: dip-buying measured negative here")
    reg = RegimeState("RISK_OFF", 0.0, False, "test")
    res = ScreenResult(ideas=[], scanned=10)
    html = digest.render_html(
        today=date(2026, 7, 11), regime=reg, screen_res=res, exit_events=[],
        open_positions=[], outcome=None, data_date=date(2026, 7, 11),
        dips=[buy, off],
    )
    assert "Index dip" in html and "NIFTYBEES" in html and "BANKBEES" in html
    assert "BUY at close" in html and "stand aside" in html
    assert "Measured 2007-2026" in html
    assert ">None<" not in html and "None</td>" not in html
    subj = digest.render_subject(date(2026, 7, 11), res, [], reg, dips=[buy, off])
    assert "NIFTYBEES dip BUY" in subj
