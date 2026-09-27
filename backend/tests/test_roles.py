"""Roles/tracks come only from Settings; variants and matching work across languages."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models.enums import RemoteType, Source
from app.providers.base import ProfileSpec, RawJob
from app.providers.sources import wttj
from app.services.prefilter import prefilter
from app.services.roles import (
    match_track,
    query_phrases,
    suggest_variants,
    with_suggested_variants,
)

TRACKS = with_suggested_variants([
    {"name": "Mobile", "years_experience": 2.5,
     "roles": [{"title": "Flutter Developer"}, {"title": "Mobile Developer"}]},
    {"name": "Data/AI", "years_experience": 2.5,
     "roles": [{"title": "Data Engineer"}, {"title": "AI Engineer"}]},
])


def test_variants_cover_the_target_languages() -> None:
    v = suggest_variants("Flutter Developer")
    assert "Développeur Flutter" in v["fr"]
    assert "Desarrollador Flutter" in v["es"]
    assert "Flutter-Entwickler" in v["de"]
    assert "Sviluppatore Flutter" in v["it"]
    assert "Flutter Engineer" in v["en"]
    assert "Ingeniero de datos" in suggest_variants("Data Engineer")["es"]
    assert suggest_variants("Product Owner") == {k: [] for k in v}  # unknown head: no guesses


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Développeur Flutter H/F", ("Mobile", "Flutter Developer")),
        ("Flutter-Entwickler (m/w/d)", ("Mobile", "Flutter Developer")),
        ("Sviluppatore Flutter Senior", ("Mobile", "Flutter Developer")),
        ("Desarrollador de aplicaciones móviles", ("Mobile", "Mobile Developer")),
        ("Senior Mobile Engineer (iOS/Android)", ("Mobile", "Mobile Developer")),
        ("Ingeniero de Datos", ("Data/AI", "Data Engineer")),
        ("Ingénieur IA", ("Data/AI", "AI Engineer")),
        ("Principal Data Center Mechanical Engineer", None),
        ("Account Executive", None),
    ],
)
def test_match_track(title: str, expected: tuple[str, str] | None) -> None:
    assert match_track(title, TRACKS) == expected


def test_first_track_wins_and_is_recorded_by_the_prefilter() -> None:
    profile = ProfileSpec(tracks=TRACKS, locations=["FR"], max_age_days=30)
    job = RawJob(source=Source.adzuna, external_id="1", url="https://x.test/1",
                 title="Développeur mobile Flutter", company="Acme", location="Paris",
                 country="FR", remote_type=RemoteType.hybrid)
    result = prefilter([job], profile)
    assert result.kept[0].matched_track == "Mobile"
    assert result.kept[0].matched_role == "Flutter Developer"


def test_query_phrases_follow_the_country_language() -> None:
    profile = ProfileSpec(tracks=TRACKS)
    fr = query_phrases(profile, "FR")
    assert fr[:4] == ["Flutter Developer", "Mobile Developer", "Data Engineer", "AI Engineer"]
    assert "Développeur Flutter" in fr[4:]  # every track's titles first, then translations
    assert not any("Entwickler" in p for p in fr)
    assert any("Entwickler" in p for p in query_phrases(profile, "DE"))
    assert query_phrases(profile, "AE") == [p for p in query_phrases(profile, "AE")
                                            if not re.search("[éíó]", p)]  # English only


def test_wttj_queries_use_settings_roles_and_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wttj, "MAX_PHRASES_PER_COUNTRY", 3)
    warnings: list[str] = []
    profile = ProfileSpec(tracks=TRACKS, locations=["FR"], max_age_days=30)
    queries = wttj.build_queries(profile, warnings=warnings)
    assert len(queries) == 3 + 3  # FR + remote, each capped
    assert warnings and "skipped" in warnings[0]


def test_saving_tracks_derives_roles_and_suggests_variants(client: TestClient) -> None:
    profile = client.get("/api/search-profile").json()
    body = {**profile, "tracks": [
        {"name": "Mobile", "years_experience": 2.5, "roles": [{"title": "Flutter Developer"}]},
        {"name": "Backend", "years_experience": 2, "roles": [
            {"title": "Backend Developer", "variants": {"fr": ["Développeur back-end"]}},
        ]},
    ]}
    saved = client.put("/api/search-profile", json=body).json()
    assert saved["roles"] == ["Flutter Developer", "Backend Developer"]
    mobile, backend = saved["tracks"]
    assert "Développeur Flutter" in mobile["roles"][0]["variants"]["fr"]  # suggested
    assert backend["roles"][0]["variants"] == {"fr": ["Développeur back-end"]}  # kept as edited
    dup = {**body, "tracks": [{"name": "A", "roles": []}, {"name": "a", "roles": []}]}
    assert client.put("/api/search-profile", json=dup).status_code == 422
    assert "Desarrollador Backend" in client.post(
        "/api/roles/suggest", json={"title": "Backend Developer"}
    ).json()["es"]
    client.put("/api/search-profile", json=profile)


def test_no_role_titles_are_hardcoded_outside_settings_and_fixtures() -> None:
    """Role lists live in Settings. Only the tour sandbox fixtures and tests may name roles."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    pattern = re.compile(
        r"\b(Data|AI|ML|Analytics|Flutter|Mobile|Backend) (Engineer|Developer)s?\b"
    )
    offenders = []
    for path in list((app_dir / "services").rglob("*.py")) + list(
        (app_dir / "providers").rglob("*.py")
    ) + list((app_dir / "prompts").glob("*.md")):
        if "mock" in path.parts or path.name == "cv_sample.py":  # fictional samples, not config
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            # Docstring/comment examples are fine; code and prompts are not.
            stripped = line.strip()
            if stripped.startswith("#") or "e.g." in line or "\"\"\"" in line or "→" in line:
                continue
            if pattern.search(line):
                offenders.append(f"{path.relative_to(app_dir)}:{n}: {stripped[:80]}")
    assert not offenders, "\n".join(offenders)
