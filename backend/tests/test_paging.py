"""Paging and filters on the two big lists, and the cache that keeps the shell's polls cheap."""

from sqlmodel import Session, select

from app.db import engine
from app.services import ttl_cache


def test_jobs_page_matches_the_unpaged_list(client) -> None:
    everything = client.get("/api/jobs", params={"stage": "all"}).json()
    assert everything["total"] == len(everything["items"]) > 3
    first = client.get("/api/jobs", params={"stage": "all", "limit": 3}).json()
    second = client.get("/api/jobs", params={"stage": "all", "limit": 3, "offset": 3}).json()
    assert first["total"] == second["total"] == everything["total"]  # total = the filtered count
    assert [i["id"] for i in first["items"] + second["items"]] == \
        [i["id"] for i in everything["items"][:6]]  # same order, nothing repeated or lost


def test_jobs_filters_still_apply_with_a_page(client) -> None:
    scored = client.get("/api/jobs", params={"stage": "all", "min_score": 70}).json()
    paged = client.get("/api/jobs", params={"stage": "all", "min_score": 70, "limit": 2}).json()
    assert paged["total"] == scored["total"] and len(paged["items"]) <= 2
    assert all((i["fit"] or {}).get("score", 0) >= 70 for i in scored["items"])
    newest = client.get("/api/jobs", params={"stage": "all", "sort": "newest"}).json()["items"]
    dates = [i["posted_at"] or i["discovered_at"] for i in newest]
    assert dates == sorted(dates, reverse=True)


def test_applications_default_to_open_stages_and_page(client) -> None:
    open_ = client.get("/api/applications")
    stages = {c["stage"] for c in open_.json()}
    assert stages and not stages & {"new", "closed"}
    assert int(open_.headers["x-total-count"]) == len(open_.json())
    everything = client.get("/api/applications", params={"stage": "all"})
    assert int(everything.headers["x-total-count"]) == len(everything.json()) > len(open_.json())
    new = client.get("/api/applications", params={"stage": "new", "limit": 2})
    assert len(new.json()) == 2 and {c["stage"] for c in new.json()} == {"new"}
    assert int(new.headers["x-total-count"]) > 2
    counts = client.get("/api/applications/counts").json()
    assert counts["new"] == int(new.headers["x-total-count"])
    assert sum(counts.values()) == len(everything.json())
    assert client.get("/api/applications", params={"stage": "nonsense"}).status_code == 422


def test_the_count_cache_serves_polls_and_forgets_on_commit(client) -> None:
    from app.models import AppSetting

    first = client.get("/api/scoring/status").json()
    assert client.get("/api/scoring/status").json() == first  # served from the cache
    assert any(key[0] == id(engine) for key in ttl_cache._store)
    with Session(engine) as s:  # any committed write forgets the cached counts
        s.add(AppSetting(key="cache-probe", value={}))
        s.commit()
        s.delete(s.exec(select(AppSetting).where(AppSetting.key == "cache-probe")).one())
        s.commit()
    assert not any(key[0] == id(engine) for key in ttl_cache._store)
