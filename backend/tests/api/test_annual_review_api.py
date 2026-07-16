from datetime import date


def test_annual_review_override_round_trip(client):
    year = date.today().year
    saved = client.put(
        f"/api/v1/wealth-portfolio/annual-reviews/{year}",
        json={"rent_received_inr": 600000, "investment_xirr_pct": 11.25, "notes": "Annual check"},
    )
    assert saved.status_code == 200
    assert saved.json()["rent_received_inr"]["source"] == "manual"
    assert saved.json()["investment_xirr_pct"]["value"] == 11.25

    fetched = client.get(f"/api/v1/wealth-portfolio/annual-reviews/{year}")
    assert fetched.status_code == 200
    assert fetched.json()["notes"] == "Annual check"
    assert any(item["year"] == year for item in client.get("/api/v1/wealth-portfolio/annual-reviews").json())

    deleted = client.delete(f"/api/v1/wealth-portfolio/annual-reviews/{year}")
    assert deleted.status_code == 200
    assert deleted.json()["rent_received_inr"]["source"] == "missing"


def test_annual_review_rejects_invalid_year_and_negative_cash(client):
    assert client.get("/api/v1/wealth-portfolio/annual-reviews/1999").status_code == 422
    response = client.put(
        f"/api/v1/wealth-portfolio/annual-reviews/{date.today().year}",
        json={"contributions_inr": -1},
    )
    assert response.status_code == 422
