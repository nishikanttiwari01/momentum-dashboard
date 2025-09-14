def test_universe_list(client):
    r = client.get("/api/v1/universe?preset=NIFTY50&page=1&per_page=20")
    assert r.status_code == 200, r.text
    js = r.json()
    assert "items" in js and "pagination" in js
    assert js["pagination"]["page"] == 1

def test_universe_sectors(client):
    r = client.get("/api/v1/universe/sectors?preset=NIFTY500")
    assert r.status_code == 200, r.text
    js = r.json()
    assert js["items"][0]["sector"] == "ALL"
    assert js["items"][0]["count"] > 0
