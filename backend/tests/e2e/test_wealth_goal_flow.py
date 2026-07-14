import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.db import (
    dispose_engine,
    get_engine,
    get_session,
    get_sessionmaker,
    init_sqlite,
)
from app.main import app
from tests.fixtures.wealth_workbook_factory import make_real_layout_workbook_bytes


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def isolated_client(tmp_path: Path):
    original_db_path = get_settings().storage.sqlite_path
    missing_override = object()
    previous_override = app.dependency_overrides.get(get_session, missing_override)
    isolated_engine = None
    isolated_session = None
    override_installed = False
    test_client = None
    try:
        dispose_engine()
        isolated_engine = init_sqlite(str(tmp_path / "wealth-goal-flow.db"))
        isolated_sessionmaker = get_sessionmaker()

        dispose_engine()
        init_sqlite(str(original_db_path))

        def isolated_session():
            with isolated_sessionmaker() as session:
                yield session

        app.dependency_overrides[get_session] = isolated_session
        override_installed = True
        test_client = TestClient(app)
        yield test_client
    finally:
        if test_client is not None:
            test_client.close()
        if (
            override_installed
            and app.dependency_overrides.get(get_session) is isolated_session
        ):
            if previous_override is missing_override:
                app.dependency_overrides.pop(get_session, None)
            else:
                app.dependency_overrides[get_session] = previous_override
        if isolated_engine is not None:
            isolated_engine.dispose()
        dispose_engine()
        init_sqlite(str(original_db_path))


def test_isolated_client_restores_global_state_when_client_setup_fails(
    monkeypatch, request
):
    original_db_path = get_settings().storage.sqlite_path
    missing_override = object()
    original_override = app.dependency_overrides.get(get_session, missing_override)

    def fail_client_setup(*args, **kwargs):
        raise RuntimeError("client setup failed")

    monkeypatch.setattr(sys.modules[__name__], "TestClient", fail_client_setup)
    with pytest.raises(RuntimeError, match="client setup failed"):
        request.getfixturevalue("isolated_client")

    assert get_engine().url.database == str(original_db_path)
    restored_override = app.dependency_overrides.get(get_session, missing_override)
    assert restored_override is original_override


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
