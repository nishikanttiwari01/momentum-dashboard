from __future__ import annotations

from copy import deepcopy
from datetime import date

import pytest
from sqlalchemy import delete

from app.api.v1 import wealth_portfolio
from app.core.db import get_sessionmaker
from app.repos.models import PortfolioAsset, PortfolioImport, PortfolioSnapshot
from app.services import family_wealth_plan_service
from app.services.family_wealth_plan_service import (
    FamilyPlanNotFound,
    InvalidFamilyPlan,
)
from app.services.family_wealth_projection import UnsafeProjection


URL = "/api/v1/wealth-portfolio/goals/family-plan"


@pytest.fixture(autouse=True)
def reset_family_plan(client):
    with get_sessionmaker()() as session:
        session.execute(delete(PortfolioAsset))
        session.execute(delete(PortfolioSnapshot))
        session.execute(delete(PortfolioImport))
        family_wealth_plan_service.restore_family_plan_defaults(
            session, today=date(2026, 7, 15)
        )
        session.commit()
    yield
    with get_sessionmaker()() as session:
        session.rollback()
        session.execute(delete(PortfolioAsset))
        session.execute(delete(PortfolioSnapshot))
        session.execute(delete(PortfolioImport))
        family_wealth_plan_service.restore_family_plan_defaults(
            session, today=date(2026, 7, 15)
        )
        session.commit()


def _configuration(client) -> dict:
    body = client.get(URL).json()
    return {
        "assumptions": body["assumptions"],
        "scenarios": [item["settings"] for item in body["scenario_projections"]],
        "goals": body["goals"],
    }


def _seed_snapshot(*, currency="INR", asset_type="cash", value=50_000_000):
    with get_sessionmaker()() as session:
        session.add(PortfolioImport(
            id="family-api-import", source_sha256="f" * 64,
            filename="family.xlsx", status="committed", issue_counts={},
        ))
        session.add(PortfolioSnapshot(
            id="family-api-snapshot", import_id="family-api-import",
            as_of=date(2026, 7, 15),
        ))
        session.add(PortfolioAsset(
            id="family-api-asset", snapshot_id="family-api-snapshot",
            source_key="asset", asset_type=asset_type, name="Asset",
            market="India", currency=currency, invested_amount=value,
            market_value=value, source_ref={},
        ))
        session.commit()


def test_get_family_plan_returns_defaults_and_snapshot_projections(client):
    _seed_snapshot()

    response = client.get(URL)

    assert response.status_code == 200
    body = response.json()
    assert body["primary_goal"]["goal"]["target_amount_inr"] == 150_000_000
    assert body["assumptions"]["monthly_contribution_inr"] == 600_000
    assert len(body["goals"]) == 6
    assert [p["settings"]["scenario_key"] for p in body["scenario_projections"]] == [
        "conservative", "expected", "optimistic",
    ]
    assert all(p["annual_points"] for p in body["scenario_projections"])
    assert all(p["passive_income"] is not None for p in body["scenario_projections"])


def test_get_empty_family_plan_does_not_invent_current_wealth(client):
    body = client.get(URL).json()

    assert body["data_health"] == "empty"
    assert body["snapshot_id"] is None
    assert body["primary_goal"]["current_value_inr"] is None
    assert len(body["scenario_projections"]) == 3
    assert all(p["ending_total_net_worth_inr"] >= 0 for p in body["scenario_projections"])


def test_put_persists_complete_family_configuration(client):
    payload = _configuration(client)
    payload["assumptions"]["monthly_contribution_inr"] = 725_000
    payload["scenarios"][1]["annual_return_pct"] = 11
    payload["goals"][0]["name"] = "University fund"

    response = client.put(URL, json=payload)

    assert response.status_code == 200
    reloaded = _configuration(client)
    assert reloaded == payload


@pytest.mark.parametrize(
    ("mutate", "loc"),
    [
        (lambda p: p["assumptions"].update(withdrawal_rate_pct=0), ["body", "assumptions", "withdrawal_rate_pct"]),
        (lambda p: p["goals"][0].update(funding_treatment="income_target"), ["body", "goals", 0, "funding_treatment"]),
        (lambda p: p["goals"].append(deepcopy(p["goals"][0])), ["body", "goals"]),
    ],
)
def test_put_validation_uses_standard_problem_with_stable_location(client, mutate, loc):
    payload = _configuration(client)
    mutate(payload)

    response = client.put(URL, json=payload)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["errors"][0]["loc"] == loc


def test_enabled_past_target_date_maps_to_stable_validation_location(client):
    payload = _configuration(client)
    payload["goals"][0]["target_date"] = "2020-01-01"

    response = client.put(URL, json=payload)

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == [
        "body", "goals", 0, "target_date",
    ]


@pytest.mark.parametrize(
    ("method", "error", "status"),
    [
        ("get_family_plan_response", FamilyPlanNotFound("private database state"), 404),
        ("get_family_plan_response", InvalidFamilyPlan("private projection state"), 422),
        ("get_family_plan_response", UnsafeProjection("private numeric state"), 409),
    ],
)
def test_domain_failures_map_to_safe_standard_problems(client, monkeypatch, method, error, status):
    def fail(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(wealth_portfolio, method, fail)

    response = client.get(URL)

    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "private" not in str(response.json())


def test_derived_response_failure_rolls_back_put_atomically(client, monkeypatch):
    before = _configuration(client)
    payload = deepcopy(before)
    payload["assumptions"]["monthly_contribution_inr"] = 999_000

    def fail_projection(_data):
        raise UnsafeProjection("forced derived response failure")

    monkeypatch.setattr(family_wealth_plan_service, "project_family_wealth", fail_projection)
    response = client.put(URL, json=payload)
    monkeypatch.undo()

    assert response.status_code == 422
    assert _configuration(client) == before


def test_restore_defaults_after_edit(client):
    defaults = _configuration(client)
    edited = deepcopy(defaults)
    edited["assumptions"]["monthly_rent_inr"] = 99_000
    assert client.put(URL, json=edited).status_code == 200

    response = client.post(f"{URL}/restore-defaults")

    assert response.status_code == 200
    assert _configuration(client) == defaults


def test_restore_failure_leaves_configuration_unchanged(client, monkeypatch):
    edited = _configuration(client)
    edited["assumptions"]["monthly_rent_inr"] = 99_000
    client.put(URL, json=edited)

    def fail(*_args, **_kwargs):
        raise InvalidFamilyPlan("forced restore failure")

    monkeypatch.setattr(wealth_portfolio, "restore_family_plan_defaults", fail)
    response = client.post(f"{URL}/restore-defaults")
    monkeypatch.undo()

    assert response.status_code == 422
    assert _configuration(client) == edited


def test_unavailable_usd_fx_returns_warning_instead_of_500(client, monkeypatch):
    _seed_snapshot(currency="USD", asset_type="us_holdings", value=100)
    monkeypatch.setattr(
        family_wealth_plan_service, "get_usd_inr",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            family_wealth_plan_service.FxUnavailable("offline")
        ),
    )

    response = client.get(URL)

    assert response.status_code == 200
    assert response.json()["data_health"] in {"warning", "unavailable"}


def test_primary_goal_route_remains_explicit_and_unchanged(client):
    response = client.get("/api/v1/wealth-portfolio/goals/primary")

    assert response.status_code == 200
    assert response.json()["goal"]["target_amount_inr"] == 150_000_000
