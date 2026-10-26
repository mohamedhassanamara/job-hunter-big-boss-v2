"""Settings the batch workflow added round-trip through Settings (no server-side meaning)."""


def test_open_next_listing_is_stored_with_the_tracking_setting(client) -> None:
    current = client.get("/api/settings").json()["values"]["tracking"]
    assert "open_next_listing" not in current  # unset means on (the page treats it as true)
    out = client.put("/api/settings/tracking", json={"value": {**current,
                                                                 "open_next_listing": False}})
    assert out.json()["values"]["tracking"]["open_next_listing"] is False
    client.put("/api/settings/tracking", json={"value": current})
