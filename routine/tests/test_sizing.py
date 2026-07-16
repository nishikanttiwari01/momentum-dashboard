from __future__ import annotations

from routine.sizing import build_plan, round_tick


def test_round_tick():
    assert round_tick(100.007) == 100.0
    assert round_tick(100.03) == 100.05
    assert round_tick(2891.52) == 2891.5


def test_basic_plan_math():
    # close 100, ATR 2% -> stop = 100 - 2*2 = 96; risk/share 4
    # capital 500k, risk 1% = 5000 -> qty 1250; position 125k < capital OK
    p = build_plan(close=100.0, atr_pct=2.0, capital=500_000, risk_pct=1.0)
    assert p is not None
    assert p.entry == 100.0 and p.stop == 96.0
    assert p.qty == 1250
    assert p.t1 == 110.0 and p.t2 == 120.0
    assert p.risk_rupees == 5000


def test_pivot_becomes_entry_trigger_when_close():
    p = build_plan(close=100.0, atr_pct=2.0, capital=500_000, risk_pct=1.0, pivot=102.0)
    assert p is not None
    assert p.entry > 102.0  # trigger just above resistance
    # far-away pivot ignored
    p2 = build_plan(close=100.0, atr_pct=2.0, capital=500_000, risk_pct=1.0, pivot=110.0)
    assert p2.entry == 100.0


def test_position_capped_at_capital():
    # tight stop => huge qty by risk; must be capped by capital
    p = build_plan(close=100.0, atr_pct=0.1, capital=50_000, risk_pct=2.0)
    assert p is not None
    assert p.position_rupees <= 50_000
    assert p.qty == 500


def test_regime_multiplier_halves_risk():
    full = build_plan(close=100.0, atr_pct=2.0, capital=500_000, risk_pct=1.0)
    half = build_plan(close=100.0, atr_pct=2.0, capital=500_000, risk_pct=1.0, size_multiplier=0.5)
    assert half.qty == full.qty // 2


def test_untradeable_returns_none():
    assert build_plan(close=0, atr_pct=2.0, capital=500_000, risk_pct=1.0) is None
    assert build_plan(close=100, atr_pct=0, capital=500_000, risk_pct=1.0) is None
    assert build_plan(close=100, atr_pct=2.0, capital=500_000, risk_pct=1.0, size_multiplier=0.0) is None
    # stop >= entry impossible here, but qty<1 case:
    assert build_plan(close=100_000.0, atr_pct=0.001, capital=1_000, risk_pct=0.1) is None
