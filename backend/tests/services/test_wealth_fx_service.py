from datetime import date, datetime, timezone

import httpx

from app.repos.models import PortfolioFxRate
from app.services.wealth_fx_service import get_usd_inr


class StaticClient:
    def get(self, url, params=None, timeout=None):
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(200, request=request, json={"date": "2026-07-14", "rates": {"INR": 86.25}})


class FailingClient:
    def get(self, url, params=None, timeout=None):
        raise httpx.ConnectError("offline")


def test_current_rate_is_persisted(session):
    result = get_usd_inr(session, date(2026, 7, 14), client=StaticClient())
    assert result.rate == 86.25
    assert result.is_fallback is False
    assert session.query(PortfolioFxRate).count() == 1


def test_network_failure_uses_latest_cached_rate(session):
    session.add(PortfolioFxRate(
        base_currency="USD", quote_currency="INR", effective_on=date(2026, 7, 13),
        rate=86.1, source="frankfurter", fetched_at=datetime.now(timezone.utc).replace(tzinfo=None),
    ))
    session.commit()
    result = get_usd_inr(session, date(2026, 7, 14), client=FailingClient())
    assert result.rate == 86.1
    assert result.is_fallback is True
