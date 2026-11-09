"""Settings → Candidate → Visibility on documents (output_visibility)."""
from app.services import visibility


def test_default_is_everything_shown(client) -> None:
    values = client.get("/api/settings").json()["values"]
    assert values["output_visibility"] == {"show_phone": True, "show_location": True,
                                           "show_graduation_year": False}


def test_normalize_treats_missing_as_default() -> None:
    base = {"show_phone": True, "show_location": True, "show_graduation_year": False}
    assert visibility.normalize(None) == base
    assert visibility.normalize({"show_phone": False}) == {**base, "show_phone": False}
    assert visibility.normalize({"show_graduation_year": True})["show_graduation_year"] is True
    # the graduation year is on only for an explicit True
    assert visibility.normalize({"show_graduation_year": "yes"})["show_graduation_year"] is False


def test_graduation_year_round_trip(client) -> None:
    ok = client.put("/api/settings/output_visibility",
                    json={"value": {"show_graduation_year": True}})
    assert ok.status_code == 200
    assert ok.json()["values"]["output_visibility"]["show_graduation_year"] is True
    assert client.put("/api/settings/output_visibility",
                      json={"value": {"show_graduation_year": "no"}}).status_code == 422
    client.put("/api/settings/output_visibility", json={"value": {"show_graduation_year": False}})


def test_round_trip_and_validation(client) -> None:
    ok = client.put("/api/settings/output_visibility",
                    json={"value": {"show_phone": False, "show_location": True}})
    assert ok.status_code == 200
    assert ok.json()["values"]["output_visibility"]["show_phone"] is False
    for bad in ({"show_phone": "no", "show_location": True}, {"other": True}, []):
        assert client.put("/api/settings/output_visibility",
                          json={"value": bad}).status_code == 422
    client.put("/api/settings/output_visibility",
               json={"value": {"show_phone": True, "show_location": True}})


def test_saving_it_does_not_recompute_scores(client, monkeypatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr("app.api.settings.recompute_all", lambda *_a, **_k: calls.append(1))
    client.put("/api/settings/output_visibility",
               json={"value": {"show_phone": False, "show_location": False}})
    assert calls == []
    client.put("/api/settings/output_visibility",
               json={"value": {"show_phone": True, "show_location": True}})
