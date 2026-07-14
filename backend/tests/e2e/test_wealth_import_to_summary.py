from tests.fixtures.wealth_workbook_factory import make_real_layout_workbook_bytes


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_workbook_import_produces_latest_summary(client):
    preview_response = client.post(
        "/api/v1/wealth-portfolio/imports/preview",
        files={"workbook": ("investment.xlsx", make_real_layout_workbook_bytes(), XLSX_MIME)},
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["blocking_error_count"] == 0

    committed = client.post(
        f"/api/v1/wealth-portfolio/imports/{preview['preview_token']}/commit"
    ).json()
    latest = client.get("/api/v1/wealth-portfolio/snapshots/latest").json()
    summary = client.get("/api/v1/wealth-portfolio/summary").json()

    assert latest["snapshot_id"] == committed["snapshot_id"]
    assert summary["snapshot_id"] == committed["snapshot_id"]
    assert summary["net_worth_market_value_inr"] == 493000
    assert summary["invested_capital_inr"] == 405000
    assert summary["data_health"] == "fresh"
