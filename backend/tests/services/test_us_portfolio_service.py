from datetime import date, datetime, timezone

import pytest

from app.services import us_portfolio_service as service


def _buy(txn_id: str, quantity: float, price: float, fees: float = 0.0):
    return service.BuyTransaction(
        id=txn_id,
        instrument_id="qqq",
        purchased_at=datetime(2026, 7, 1, 14, 30, tzinfo=timezone.utc),
        quantity=quantity,
        price_usd=price,
        fees_usd=fees,
    )


def test_summary_includes_fees_in_weighted_average():
    result = service.calculate_holding([_buy("a", 1, 400, 2), _buy("b", 2, 430, 3)], 450)
    assert result["total_units"] == 3
    assert result["total_invested_usd"] == 1265
    assert result["average_buy_price_usd"] == pytest.approx(421.6667)
    assert result["current_value_usd"] == 1350
    assert result["unrealized_gain_usd"] == 85


def test_repository_round_trip_and_validation(tmp_path):
    repo = service.TransactionRepository(tmp_path / "transactions.csv")
    saved = repo.add(_buy("a", 0.5, 500))
    assert repo.list_for("qqq") == [saved]
    before = repo.path.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        repo.add(_buy("b", 0, 500))
    assert repo.path.read_text(encoding="utf-8") == before


def test_history_includes_exact_purchase_and_average(monkeypatch, tmp_path):
    repo = service.TransactionRepository(tmp_path / "transactions.csv")
    repo.add(_buy("a", 1, 400, 2))
    monkeypatch.setattr(service, "fetch_price_history", lambda *_a, **_k: [
        (date(2026, 7, 1), 405.0), (date(2026, 7, 2), 410.0)
    ])
    result = service.build_history("qqq", "1m", repo=repo)
    assert result["points"][-1] == {"date": "2026-07-02", "price": 410.0}
    assert result["purchases"][0]["price_usd"] == 400
    assert result["average_buy_price_usd"] == 402


def test_overview_keeps_costs_when_prices_fail(monkeypatch, tmp_path):
    repo = service.TransactionRepository(tmp_path / "transactions.csv")
    repo.add(_buy("a", 1, 400))
    monkeypatch.setattr(service, "fetch_price_history", lambda *_a, **_k: [])
    row = service.build_overview(repo=repo)["instruments"][0]
    assert row["holding"]["total_invested_usd"] == 400
    assert row["holding"]["current_value_usd"] is None
    assert row["market_data_error"]
