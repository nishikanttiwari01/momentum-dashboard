from datetime import date

import pytest

from app.services import portfolio_service as service


CONFIG = {
    "instruments": [{"id": "axis_midcap", "type": "mutual_fund"}],
    "holdings_config": [{"instrument_id": "axis_midcap", "account_id": "nre_primary"}],
}


def test_amount_and_nav_derive_units():
    row = service.normalize_buy({"instrument_id": "axis_midcap", "date": "2026-07-14", "amount": 10000, "nav": 250, "fees": 10}, CONFIG)
    assert row.units == 40
    assert row.account_id == "nre_primary"


def test_units_and_nav_derive_amount():
    row = service.normalize_buy({"instrument_id": "axis_midcap", "date": "2026-07-14", "units": 40, "nav": 250}, CONFIG)
    assert row.amount == 10000


def test_inconsistent_amount_and_units_are_rejected():
    with pytest.raises(ValueError, match="do not match"):
        service.normalize_buy({"instrument_id": "axis_midcap", "date": "2026-07-14", "amount": 9000, "units": 40, "nav": 250}, CONFIG)


def test_combined_summary_includes_fees_across_accounts():
    rows = [
        service.Txn(date(2026, 1, 1), "axis_midcap", "nre", "BUY", 1000, 10, 100, 5),
        service.Txn(date(2026, 2, 1), "axis_midcap", "nro", "SIP", 600, 5, 120, 0),
    ]
    result = service.calculate_fund_holding(rows, 130)
    assert result["total_units"] == 15
    assert result["total_invested"] == 1605
    assert result["average_nav"] == 107
    assert result["gain"] == 345
