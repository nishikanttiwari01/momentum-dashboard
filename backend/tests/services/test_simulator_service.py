from __future__ import annotations

from datetime import date

from app.services.simulator_service import DailyBar, SimulationParams, SimulatorService


def _base_params(**overrides):
    params = SimulationParams(
        min_score=70,
        min_adx=20,
        atr_pct_min=0.0,
        atr_pct_max=20.0,
        prox52w_min_pct=-20.0,
        pivot_clear_min_pct=-5.0,
        pivot_clear_max_pct=10.0,
        base_len_min_bars=3,
        relvol20_min=1.0,
        day_change_max_pct=10.0,
        liquidity_min=1.0,
        stop_loss_pct=0.05,
        take_profit_pct=0.10,
        round_trip_cost_pct=0.0,
        max_hold_days=10,
    )
    for key, value in overrides.items():
        setattr(params, key, value)
    return params


def test_simulator_enters_on_next_bar_and_uses_intraday_target(monkeypatch):
    service = SimulatorService()
    params = _base_params()

    candidate_map = {
        date(2025, 1, 2): [{"symbol": "AAA.NS", "price": 100.0}],
        date(2025, 1, 3): [],
    }
    bar_map = {
        date(2025, 1, 2): {"AAA.NS": DailyBar(open=100.0, high=101.0, low=99.0, close=100.0)},
        date(2025, 1, 3): {"AAA.NS": DailyBar(open=105.0, high=116.0, low=104.0, close=110.0)},
    }

    monkeypatch.setattr(service, "_candidate_rows_for_day", lambda day, _params: candidate_map.get(day, []))
    monkeypatch.setattr(
        service,
        "_bar_map_for_day",
        lambda day, symbols=None: {
            sym: bar
            for sym, bar in bar_map.get(day, {}).items()
            if symbols is None or sym in {s.upper() for s in symbols}
        },
    )
    monkeypatch.setattr(service, "_build_price_cache_from_prices", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_series_from_cache", lambda *_args, **_kwargs: {})

    run = service.simulate(date(2025, 1, 2), date(2025, 1, 3), params)

    assert len(run.trades) == 1
    trade = run.trades[0]
    assert trade.entry_date == date(2025, 1, 3)
    assert trade.entry_price == 105.0
    assert trade.exit_date == date(2025, 1, 3)
    assert trade.exit_price == 115.5
    assert trade.notes == "target"


def test_simulator_uses_intraday_stop_and_applies_costs(monkeypatch):
    service = SimulatorService()
    params = _base_params(round_trip_cost_pct=0.01)

    candidate_map = {
        date(2025, 1, 2): [{"symbol": "AAA.NS", "price": 100.0}],
        date(2025, 1, 3): [],
    }
    bar_map = {
        date(2025, 1, 2): {"AAA.NS": DailyBar(open=100.0, high=101.0, low=99.0, close=100.0)},
        date(2025, 1, 3): {"AAA.NS": DailyBar(open=100.0, high=101.0, low=94.0, close=99.0)},
    }

    monkeypatch.setattr(service, "_candidate_rows_for_day", lambda day, _params: candidate_map.get(day, []))
    monkeypatch.setattr(
        service,
        "_bar_map_for_day",
        lambda day, symbols=None: {
            sym: bar
            for sym, bar in bar_map.get(day, {}).items()
            if symbols is None or sym in {s.upper() for s in symbols}
        },
    )
    monkeypatch.setattr(service, "_build_price_cache_from_prices", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_series_from_cache", lambda *_args, **_kwargs: {})

    run = service.simulate(date(2025, 1, 2), date(2025, 1, 3), params)

    assert len(run.trades) == 1
    trade = run.trades[0]
    assert trade.entry_price == 100.0
    assert trade.exit_price == 95.0
    assert trade.notes == "stop"
    assert round(trade.pnl_pct, 2) == -6.0
    assert run.summary["assumed_round_trip_cost_pct"] == 1.0
