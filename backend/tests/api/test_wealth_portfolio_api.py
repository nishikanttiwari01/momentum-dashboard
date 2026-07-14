from tests.fixtures.wealth_workbook_factory import make_workbook_bytes


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_preview_then_commit_and_read_summary(client):
    preview = client.post(
        "/api/v1/wealth-portfolio/imports/preview",
        files={"workbook": ("investment.xlsx", make_workbook_bytes(), XLSX_MIME)},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["counts"]["assets"] == 1
    committed = client.post(
        f"/api/v1/wealth-portfolio/imports/{body['preview_token']}/commit"
    )
    assert committed.status_code == 201
    summary = client.get("/api/v1/wealth-portfolio/summary")
    assert summary.status_code == 200
    assert summary.json()["net_worth_market_value_inr"] == 520000


def test_preview_rejects_wrong_extension(client):
    response = client.post(
        "/api/v1/wealth-portfolio/imports/preview",
        files={"workbook": ("notes.csv", b"x", "text/csv")},
    )
    assert response.status_code == 422


def test_commit_rejects_preview_with_blocking_errors(client):
    preview = client.post(
        "/api/v1/wealth-portfolio/imports/preview",
        files={"workbook": ("bad.xlsx", make_workbook_bytes(invalid_transaction_date=True), XLSX_MIME)},
    ).json()
    response = client.post(
        f"/api/v1/wealth-portfolio/imports/{preview['preview_token']}/commit"
    )
    assert response.status_code == 409
