from datetime import date

import pandas as pd
import pytest

from app.services.market_index_service import (
    MarketIndexPoint,
    MarketIndexService,
    MarketIndexUnavailable,
)


def test_build_history_maps_sensex_and_normalizes_points():
    calls = []

    def fake_loader(symbol: str, period: str):
        calls.append((symbol, period))
        return pd.DataFrame(
            {"Close": [80_000.0, float("nan"), 79_223.11, float("inf")]},
            index=pd.to_datetime(
                ["2026-01-03", "2026-01-04", "2026-01-02", "2026-01-05"]
            ),
        )

    result = MarketIndexService(loader=fake_loader).build_history("sensex", "1y")

    assert calls == [("^BSESN", "1y")]
    assert result.symbol == "^BSESN"
    assert result.points == [
        MarketIndexPoint(on=date(2026, 1, 2), close=79_223.11),
        MarketIndexPoint(on=date(2026, 1, 3), close=80_000.0),
    ]
    assert result.latest_value == 80_000.0
    assert result.change == pytest.approx(776.89)
    assert result.change_pct == pytest.approx(776.89 / 79_223.11 * 100.0)


@pytest.mark.parametrize("key, range_", [("dow", "1y"), ("sensex", "10y")])
def test_build_history_rejects_unknown_market_and_range(key, range_):
    service = MarketIndexService(loader=lambda _symbol, _period: None)

    with pytest.raises(ValueError):
        service.build_history(key, range_)


@pytest.mark.parametrize(
    "loaded",
    [
        None,
        pd.DataFrame(),
        pd.DataFrame({"Open": [1.0]}, index=pd.to_datetime(["2026-01-02"])),
        pd.DataFrame(
            {"Close": [float("nan"), float("inf")]},
            index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
        ),
    ],
)
def test_build_history_raises_typed_error_for_unavailable_data(loaded):
    service = MarketIndexService(loader=lambda _symbol, _period: loaded)

    with pytest.raises(MarketIndexUnavailable):
        service.build_history("sp500", "6m")


def test_build_history_wraps_loader_failure_as_unavailable():
    def failing_loader(_symbol: str, _period: str):
        raise RuntimeError("upstream failed")

    with pytest.raises(MarketIndexUnavailable):
        MarketIndexService(loader=failing_loader).build_history("sensex", "1m")
