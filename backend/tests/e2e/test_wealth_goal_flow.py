from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.db import dispose_engine, get_session, get_sessionmaker, init_sqlite
from app.main import app
from tests.fixtures.wealth_workbook_factory import make_real_layout_workbook_bytes


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def isolated_client(tmp_path: Path):
    original_db_path = get_settings().storage.sqlite_path
    dispose_engine()
    init_sqlite(str(tmp_path / "wealth-goal-flow.db"))
    isolated_sessionmaker = get_sessionmaker()

    def isolated_session():
        with isolated_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = isolated_session
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()
        app.dependency_overrides.pop(get_session, None)
        dispose_engine()
        init_sqlite(str(original_db_path))


def test_imported_wealth_drives_persisted_goal_projections(isolated_client):
    preview_response = isolated_client.post(
        "/api/v1/wealth-portfolio/imports/preview",
        files={
            "workbook": (
                "investment.xlsx",
                make_real_layout_workbook_bytes(),
                XLSX_MIME,
            )
        },
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["blocking_error_count"] == 0

    commit_response = isolated_client.post(
        f"/api/v1/wealth-portfolio/imports/{preview['preview_token']}/commit"
    )
    assert commit_response.status_code == 201
    snapshot_id = commit_response.json()["snapshot_id"]

    summary_before = isolated_client.get("/api/v1/wealth-portfolio/summary").json()
    initial_goal = isolated_client.get(
        "/api/v1/wealth-portfolio/goals/primary"
    ).json()
    assert initial_goal["snapshot_id"] == snapshot_id
    assert initial_goal["current_value_inr"] == 493_000
    assert initial_goal["current_value_inr"] == summary_before[
        "net_worth_market_value_inr"
    ]

    deadline = date.today() + timedelta(days=365 * 5)
    payload = {
        "goal": {
            "name": "Financial freedom",
            "target_amount_inr": 20_000_000,
            "deadline": deadline.isoformat(),
        },
        "scenarios": [
            {
                "scenario_key": "conservative",
                "annual_return_pct": 7,
                "monthly_contribution_inr": 50_000,
            },
            {
                "scenario_key": "expected",
                "annual_return_pct": 11,
                "monthly_contribution_inr": 100_000,
            },
            {
                "scenario_key": "optimistic",
                "annual_return_pct": 15,
                "monthly_contribution_inr": 150_000,
            },
        ],
    }
    update_response = isolated_client.put(
        "/api/v1/wealth-portfolio/goals/primary", json=payload
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    reloaded = isolated_client.get("/api/v1/wealth-portfolio/goals/primary").json()

    assert reloaded["goal"] == payload["goal"]
    assert [item["settings"] for item in reloaded["scenario_projections"]] == payload[
        "scenarios"
    ]
    assert reloaded["snapshot_id"] == snapshot_id
    assert reloaded["current_value_inr"] == 493_000
    assert reloaded["required_trajectory"]
    assert all(item["trajectory"] for item in reloaded["scenario_projections"])
    for update_projection, reload_projection in zip(
        updated["scenario_projections"], reloaded["scenario_projections"], strict=True
    ):
        assert reload_projection["projected_deadline_value_inr"] == pytest.approx(
            update_projection["projected_deadline_value_inr"]
        )

    summary_after = isolated_client.get("/api/v1/wealth-portfolio/summary").json()
    assert summary_after == summary_before
