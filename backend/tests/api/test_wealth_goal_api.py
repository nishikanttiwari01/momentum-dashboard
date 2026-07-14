from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete, select

from app.core.db import get_sessionmaker
from app.repos.models import (
    PortfolioAsset,
    PortfolioImport,
    PortfolioSnapshot,
    WealthGoal,
    WealthGoalScenario,
)


DEFAULT_GOAL_ID = "00000000-0000-0000-0000-000000000015"


@pytest.fixture(autouse=True)
def reset_primary_goal(client):
    with get_sessionmaker()() as session:
        session.execute(delete(PortfolioAsset))
        session.execute(delete(PortfolioSnapshot))
        session.execute(delete(PortfolioImport))
        goal = session.get(WealthGoal, DEFAULT_GOAL_ID)
        goal.name = "₹15 Cr by 2029"
        goal.target_amount_inr = 150_000_000
        goal.deadline = date(2029, 12, 31)
        defaults = {
            "conservative": (7, 0, 0),
            "expected": (10, 0, 1),
            "optimistic": (13, 0, 2),
        }
        scenarios = session.scalars(
            select(WealthGoalScenario).where(WealthGoalScenario.goal_id == goal.id)
        ).all()
        for scenario in scenarios:
            rate, monthly, order = defaults[scenario.scenario_key]
            scenario.annual_return_pct = rate
            scenario.monthly_contribution_inr = monthly
            scenario.display_order = order
        session.commit()
    yield
    with get_sessionmaker()() as session:
        session.execute(delete(PortfolioAsset))
        session.execute(delete(PortfolioSnapshot))
        session.execute(delete(PortfolioImport))
        session.commit()


def configuration(*, target=200_000_000, deadline="2035-12-31", expected=11):
    return {
        "goal": {
            "name": "Financial freedom",
            "target_amount_inr": target,
            "deadline": deadline,
        },
        "scenarios": [
            {
                "scenario_key": "conservative",
                "annual_return_pct": 8,
                "monthly_contribution_inr": 100_000,
            },
            {
                "scenario_key": "expected",
                "annual_return_pct": expected,
                "monthly_contribution_inr": 150_000,
            },
            {
                "scenario_key": "optimistic",
                "annual_return_pct": 14,
                "monthly_contribution_inr": 200_000,
            },
        ],
    }


def seed_inr_snapshot(value: float):
    with get_sessionmaker()() as session:
        session.add(
            PortfolioImport(
                id="goal-api-import",
                source_sha256="a" * 64,
                filename="goal.xlsx",
                status="committed",
                issue_counts={},
            )
        )
        session.add(
            PortfolioSnapshot(
                id="goal-api-snapshot",
                import_id="goal-api-import",
                as_of=date(2026, 7, 14),
            )
        )
        session.add(
            PortfolioAsset(
                id="goal-api-asset",
                snapshot_id="goal-api-snapshot",
                source_key="cash",
                asset_type="cash",
                name="Cash",
                market="India",
                currency="INR",
                invested_amount=value,
                market_value=value,
                source_ref={},
            )
        )
        session.commit()


def test_get_primary_goal_returns_seeded_settings_and_empty_calculations(client):
    response = client.get("/api/v1/wealth-portfolio/goals/primary")

    assert response.status_code == 200
    body = response.json()
    assert body["goal"]["target_amount_inr"] == 150_000_000
    assert [
        item["settings"]["scenario_key"] for item in body["scenario_projections"]
    ] == [
        "conservative",
        "expected",
        "optimistic",
    ]
    assert body["data_health"] == "empty"
    assert body["snapshot_id"] is None
    for field in (
        "current_value_inr",
        "achieved_pct",
        "remaining_inr",
        "required_monthly_contribution_inr",
    ):
        assert body[field] is None
    assert body["required_trajectory"] == []
    assert all(item["trajectory"] == [] for item in body["scenario_projections"])


def test_get_primary_goal_uses_consolidated_snapshot_value(client):
    seed_inr_snapshot(50_000_000)

    body = client.get("/api/v1/wealth-portfolio/goals/primary").json()

    assert body["snapshot_id"] == "goal-api-snapshot"
    assert body["current_value_inr"] == 50_000_000
    assert body["achieved_pct"] == pytest.approx(100 / 3)
    assert body["remaining_inr"] == 100_000_000
    assert body["required_monthly_contribution_inr"] > 0
    assert body["required_trajectory"]
    assert len(body["scenario_projections"]) == 3
    for projection in body["scenario_projections"]:
        assert projection["projected_deadline_value_inr"] is not None
        assert projection["surplus_or_shortfall_inr"] is not None
        assert isinstance(projection["on_track"], bool)
        assert projection["trajectory"]


def test_put_primary_goal_persists_complete_configuration_and_reloads(client):
    seed_inr_snapshot(75_000_000)

    response = client.put(
        "/api/v1/wealth-portfolio/goals/primary", json=configuration(expected=11)
    )

    assert response.status_code == 200
    assert response.json()["goal"]["target_amount_inr"] == 200_000_000
    reloaded = client.get("/api/v1/wealth-portfolio/goals/primary").json()
    assert reloaded["goal"]["name"] == "Financial freedom"
    assert reloaded["scenario_projections"][1]["settings"]["annual_return_pct"] == 11
    with get_sessionmaker()() as session:
        scenarios = session.scalars(
            select(WealthGoalScenario)
            .where(WealthGoalScenario.goal_id == DEFAULT_GOAL_ID)
            .order_by(WealthGoalScenario.display_order)
        ).all()
        assert len(scenarios) == 3
        assert [row.scenario_key for row in scenarios] == [
            "conservative",
            "expected",
            "optimistic",
        ]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["scenarios"].reverse(),
        lambda value: value["scenarios"].pop(),
        lambda value: value["scenarios"][0].update(annual_return_pct=12),
        lambda value: value["scenarios"][0].update(annual_return_pct=-26),
        lambda value: value["scenarios"][1].update(monthly_contribution_inr=-1),
        lambda value: value["goal"].update(target_amount_inr=0),
        lambda value: value["goal"].update(deadline="2020-01-01"),
    ],
)
def test_put_rejects_invalid_configuration_without_partial_update(client, mutate):
    payload = configuration()
    mutate(payload)

    response = client.put("/api/v1/wealth-portfolio/goals/primary", json=payload)

    assert response.status_code == 422
    body = client.get("/api/v1/wealth-portfolio/goals/primary").json()
    assert body["goal"]["target_amount_inr"] == 150_000_000
    assert body["scenario_projections"][1]["settings"]["annual_return_pct"] == 10


def test_deadline_validation_has_field_location_and_rolls_back(client):
    payload = configuration(deadline="2020-01-01")

    response = client.put("/api/v1/wealth-portfolio/goals/primary", json=payload)

    assert response.status_code == 422
    issue = response.json()["errors"][0]
    assert issue["loc"] == ["body", "goal", "deadline"]
    assert issue["msg"] == "Goal deadline must be after the calculation date"
    reloaded = client.get("/api/v1/wealth-portfolio/goals/primary").json()
    assert reloaded["goal"]["target_amount_inr"] == 150_000_000


def test_scenario_return_order_validation_identifies_offending_rate(client):
    payload = configuration()
    payload["scenarios"][1]["annual_return_pct"] = 7

    response = client.put("/api/v1/wealth-portfolio/goals/primary", json=payload)

    assert response.status_code == 422
    issue = response.json()["errors"][0]
    assert issue["loc"] == ["body", "scenarios", 1, "annual_return_pct"]
    assert "conservative <= expected <= optimistic" in issue["msg"]
    reloaded = client.get("/api/v1/wealth-portfolio/goals/primary").json()
    assert reloaded["scenario_projections"][1]["settings"]["annual_return_pct"] == 10


def test_deadline_beyond_fifty_year_horizon_is_rejected_before_mutation(client):
    payload = configuration(deadline="9999-12-31")
    payload["scenarios"][2]["annual_return_pct"] = 50

    response = client.put("/api/v1/wealth-portfolio/goals/primary", json=payload)

    assert response.status_code == 422
    issue = response.json()["errors"][0]
    assert issue["loc"] == ["body", "goal", "deadline"]
    assert issue["msg"] == "Goal deadline cannot exceed 600 monthly periods"
    reloaded = client.get("/api/v1/wealth-portfolio/goals/primary").json()
    assert reloaded["goal"]["name"] == "₹15 Cr by 2029"
    assert reloaded["goal"]["target_amount_inr"] == 150_000_000


def test_already_funded_goal_requires_no_monthly_contribution(client):
    seed_inr_snapshot(250_000_000)

    body = client.put(
        "/api/v1/wealth-portfolio/goals/primary", json=configuration(target=200_000_000)
    ).json()

    assert body["achieved_pct"] == 125
    assert body["remaining_inr"] == 0
    assert body["required_monthly_contribution_inr"] == 0
