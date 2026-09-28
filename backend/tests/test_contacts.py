"""Apollo import (dedupe, batches, resume), role ranking, three-tier resolution, lookups."""

from datetime import UTC, datetime, timedelta
from itertools import count

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import (
    Application,
    ApplicationEvent,
    Company,
    CompanyLookup,
    Contact,
    ContactImport,
    FitScore,
    Job,
)
from app.models.enums import ContactSource, ContactTier, EventKind, LookupStatus, Stage
from app.services import contacts, contacts_import
from app.services.contacts import DEFAULT_ROLE_RANKING, UNRANKED, rank
from app.services.contacts_import import detect_mapping, map_row, parse_csv

_n = count(1)


def csv_bytes(*rows: str, header: str = "First Name,Last Name,Title,Company,Email") -> bytes:
    return ("\n".join([header, *rows]) + "\n").encode()


def do_import(raw: bytes, name: str = "list.csv") -> ContactImport:
    headers, rows = parse_csv(raw)
    mapping = detect_mapping(headers)
    with Session(engine) as s:
        run = contacts_import.begin(s, name, contacts_import.sha256(raw), len(rows), mapping)
    return contacts_import.run_import(engine, run.id, rows, mapping)


def company_contacts(name: str) -> list[Contact]:
    from app.services.dedupe import normalize_company

    with Session(engine) as s:
        company = s.exec(select(Company).where(
            Company.normalized_name == normalize_company(name))).first()
        return list(s.exec(select(Contact).where(Contact.company_id == company.id))) if company \
            else []


# ------------------------------------------------------------------------------ parsing


def test_mapping_detects_apollo_headers_and_semicolons() -> None:
    headers, rows = parse_csv("﻿First Name;Last Name;Title;Company;Email\nAna;Ruiz;CTO;Acme;a@x.io\n"
                              .encode())
    mapping = detect_mapping(headers)
    assert mapping["first_name"] == "First Name" and mapping["email"] == "Email"
    assert mapping["full_name"] is None
    r = map_row(rows[0], mapping)
    assert r.full_name == "Ana Ruiz" and r.email == "a@x.io" and r.company == "Acme"


@pytest.mark.parametrize(("row", "reason"), [
    ({"First Name": "Ana", "Company": ""}, "no_company"),
    ({"Company": "Acme"}, "no_name_or_email"),
])
def test_rows_without_company_or_identity_are_skipped(row: dict, reason: str) -> None:
    mapping = detect_mapping(["First Name", "Last Name", "Title", "Company", "Email"])
    assert map_row(row, mapping) == reason


def test_invalid_email_is_dropped_but_the_contact_kept() -> None:
    mapping = detect_mapping(["First Name", "Last Name", "Title", "Company", "Email"])
    r = map_row({"First Name": "Ana", "Company": "Acme", "Email": "not-an-email"}, mapping)
    assert r.email is None and r.full_name == "Ana"


# ------------------------------------------------------------------------------- import


def test_import_dedupes_by_email_and_by_company_and_name(seeded: None) -> None:
    co = f"Dedupe Labs {next(_n)}"
    run = do_import(csv_bytes(
        f"Ana,Ruiz,CTO,{co} SL,Ana.Ruiz@Dedupe.io",
        f"Ana,Ruiz,CTO,{co},ana.ruiz@dedupe.io ",  # same email (case/space) → duplicate in file
        f"José,García,Recruiter,{co} S.L.,",  # no email: keyed by company + name
        f"Jose,Garcia,Recruiter,{co},",  # accents folded, legal suffix dropped → duplicate
        f"Bo,Li,,{co},bo@dedupe.io",
    ))
    assert (run.status, run.created, run.skipped) == ("done", 3, 2)
    assert run.skipped_reasons == {"duplicate_in_file": 2} and run.companies_created == 1
    people = company_contacts(co)
    assert sorted(c.full_name for c in people) == ["Ana Ruiz", "Bo Li", "José García"]
    ana = next(c for c in people if c.full_name == "Ana Ruiz")
    assert ana.email_normalized == "ana.ruiz@dedupe.io" and ana.role_rank == 0


def test_second_file_fills_missing_fields_and_never_duplicates(seeded: None) -> None:
    co = f"Fill Co {next(_n)}"
    do_import(csv_bytes(f"Jose,Garcia,,{co},"))
    run = do_import(csv_bytes(
        f"José,García,Head of Engineering,{co},jose@fill.io",  # same person → filled in
        f"Jose,Garcia,Head of Engineering,{co},jose@fill.io",  # duplicate in this file
    ), name="second.csv")
    assert (run.created, run.updated) == (0, 1)
    [jose] = company_contacts(co)
    assert jose.email == "jose@fill.io" and jose.title == "Head of Engineering"
    assert jose.role_rank == 1
    again = do_import(csv_bytes(f"Jose,Garcia,CTO,{co},jose@fill.io"), name="third.csv")
    assert again.skipped_reasons == {"already_known": 1}
    assert company_contacts(co)[0].title == "Head of Engineering"  # never overwritten


def test_an_imported_file_is_recognized_by_hash(seeded: None) -> None:
    raw = csv_bytes(f"Ana,Hash,CTO,Hash Co {next(_n)},ana@hash{next(_n)}.io")
    do_import(raw)
    with Session(engine) as s:
        assert contacts_import.already_imported(s, contacts_import.sha256(raw)) is not None


def test_batches_commit_progress_and_a_rerun_after_failure_completes(
        seeded: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(contacts_import, "BATCH", 2)
    co = f"Batch Co {next(_n)}"
    raw = csv_bytes(*[f"P{i},L{i},,{co},p{i}@batch{co[-2:].strip()}.io" for i in range(5)])
    headers, rows = parse_csv(raw)
    mapping = detect_mapping(headers)
    real_map = contacts_import.map_row
    calls = count()

    def flaky(row, m):  # noqa: ANN001, ANN202
        if next(calls) == 3:
            raise RuntimeError("disk full")
        return real_map(row, m)

    monkeypatch.setattr(contacts_import, "map_row", flaky)
    with Session(engine) as s:
        run = contacts_import.begin(s, "b.csv", "x" * 64, len(rows), mapping)
    failed = contacts_import.run_import(engine, run.id, rows, mapping)
    assert failed.status == "failed" and "disk full" in failed.error and failed.processed == 2
    assert len(company_contacts(co)) == 2  # the first batch stayed
    monkeypatch.setattr(contacts_import, "map_row", real_map)
    with Session(engine) as s:
        rerun = contacts_import.begin(s, "b.csv", "y" * 64, len(rows), mapping)
    done = contacts_import.run_import(engine, rerun.id, rows, mapping)
    assert done.status == "done" and (done.created, done.skipped) == (3, 2)
    assert len(company_contacts(co)) == 5


def test_backup_copies_the_database(tmp_path) -> None:  # noqa: ANN001
    path = contacts_import.backup_db(engine, "import", backups=tmp_path)
    assert path is not None and path.exists() and path.stat().st_size > 0


# ------------------------------------------------------------------------------ ranking


@pytest.mark.parametrize(("title", "expected"), [
    ("CTO & Co-founder", 0),
    ("Directeur Technique", 0),
    ("VP of Engineering", 1),
    ("Head of Engineering", 1),
    ("Head of Data & AI", 2),
    ("Responsable Data", 2),
    ("Engineering Manager, Data Platform", 3),
    ("Tech Lead Backend", 4),
    ("Senior Talent Acquisition Partner", 5),
    ("Responsable Recrutement", 5),
    ("Técnico de reclutamiento", 5),
    ("Fundador", 6),
    ("Sales Executive", UNRANKED),
    (None, UNRANKED),
])
def test_role_ranking(title: str | None, expected: int) -> None:
    assert rank(title, DEFAULT_ROLE_RANKING)[0] == expected


def test_custom_ranking_from_settings() -> None:
    custom = [{"label": "Recruiters first", "keywords": ["recruiter"]},
              {"label": "CTO", "keywords": ["cto"]}]
    assert rank("Recruiter", custom) == (0, "Recruiters first")
    assert rank("CTO", custom) == (1, "CTO")


# ---------------------------------------------------------------------------- resolution


def make_job(s: Session, company: Company, *, stage: Stage = Stage.new,
             score: int | None = None) -> Application:
    n = next(_n)
    job = Job(source="adzuna", external_id=f"ct-{n}", url=f"https://example.test/ct/{n}",
              title=f"Engineer {n}", company_id=company.id, dedupe_key=f"ct-{n}",
              country="FR", matched_track="T-contacts")
    s.add(job)
    s.flush()
    app = Application(job_id=job.id, stage=stage)
    s.add(app)
    if score is not None:
        s.add(FitScore(job_id=job.id, score=score, prompt_version="v3"))
    s.flush()
    return app


def make_company(s: Session, *people: tuple[str, str, str]) -> Company:
    n = next(_n)
    company = Company(name=f"Resolve Co {n}", normalized_name=f"resolve co {n}")
    s.add(company)
    s.flush()
    for name, title, source in people:
        s.add(Contact(company_id=company.id, full_name=name, title=title, source=source,
                      normalized_name=name.lower(), role_rank=rank(title, DEFAULT_ROLE_RANKING)[0],
                      email=f"{name.split()[0].lower()}{n}@co.io"))
    s.flush()
    return company


def test_tier_1_order_depends_on_company_size(seeded: None) -> None:
    with Session(engine) as s:
        people = (("Rita Recruiter", "Recruiter", "apollo_dump"),
                  ("Eve Manager", "Engineering Manager", "apollo_dump"),
                  ("Fred Founder", "Founder & CEO", "apollo_dump"),
                  ("Carl Cto", "CTO", "apollo_dump"))
        large, small, bound = make_company(s, *people), make_company(s, *people), \
            make_company(s, *people)
        small.employees = 12
        bound.employees_max = 200  # "under 200" from an Apollo list; threshold 200 → small
        apps = {name: make_job(s, c) for name, c in
                (("large", large), ("small", small), ("bound", bound))}
        for app in apps.values():
            contacts.resolve(s, app)
        who = {k: s.get(Contact, a.contact_id).full_name for k, a in apps.items()}
        assert who == {"large": "Rita Recruiter", "small": "Carl Cto", "bound": "Carl Cto"}
        assert apps["large"].route == "undecided"  # routing waits for CV approval
        assert not contacts.resolve(s, apps["large"]).changed  # idempotent
        small.employees = 5000  # set by hand: now a large company
        s.add(small)
        contacts.resolve(s, apps["small"])
        assert s.get(Contact, apps["small"].contact_id).full_name == "Rita Recruiter"
        s.rollback()


def test_small_order_puts_founders_before_heads_of_engineering() -> None:
    from app.models import Company as Co

    r = contacts.Ranking(DEFAULT_ROLE_RANKING,
                         contacts._order(None, DEFAULT_ROLE_RANKING, contacts.DEFAULT_SMALL_ORDER),
                         contacts._order(None, DEFAULT_ROLE_RANKING, contacts.DEFAULT_LARGE_ORDER),
                         50)
    labels = lambda order: [r.label(i) for i in order]  # noqa: E731
    assert labels(r.small)[:4] == ["CTO", "Founder / CEO", "VP / Head of Engineering",
                                   "Head of Data / AI / ML"]
    assert labels(r.small)[-1] == "HR / Talent"
    assert labels(r.large)[:2] == ["HR / Talent", "Engineering Manager"]
    assert contacts.is_small(Co(name="x", normalized_name="x", employees=49), 50)
    assert not contacts.is_small(Co(name="x", normalized_name="x", employees=50), 50)
    assert not contacts.is_small(Co(name="x", normalized_name="x", employees_max=200), 50)
    assert not contacts.is_small(Co(name="x", normalized_name="x"), 50)  # unknown = large


def test_a_later_import_takes_the_company_out_of_the_lookup_queue(seeded: None) -> None:
    with Session(engine) as s:
        company = make_company(s)
        app = make_job(s, company, score=90)
        contacts.resolve(s, app)
        assert app.contact_tier == ContactTier.lookup_queued
        s.add(Contact(company_id=company.id, full_name="Late Import", title="CTO",
                      normalized_name="late import", role_rank=0))
        s.flush()
        contacts.resolve(s, app)
        assert app.contact_tier == ContactTier.apollo_dump
        assert s.exec(select(CompanyLookup).where(
            CompanyLookup.company_id == company.id)).first() is None
        assert company.id not in [r.company.id for r in contacts.lookup_queue(s).rows]
        s.rollback()


def test_found_resolves_every_job_and_not_found_is_tier_3(seeded: None) -> None:
    with Session(engine) as s:
        found_co, empty_co = make_company(s), make_company(s)
        jobs = [make_job(s, found_co), make_job(s, found_co)]
        other = make_job(s, empty_co)
        contacts.resolve_many(s, [(a, s.get(Job, a.job_id)) for a in [*jobs, other]])
        contacts.lookup_found(s, found_co.id, full_name="Nina Head", title="Head of Data",
                              email="nina@found.io", linkedin_url=None)
        assert {a.contact_tier for a in jobs} == {ContactTier.lookup_found}
        assert len({a.contact_id for a in jobs}) == 1
        contacts.lookup_not_found(s, empty_co.id)
        assert other.contact_tier == ContactTier.none and other.contact_id is None
        assert contacts.used_today(s) >= 2
        s.rollback()


def test_manual_choices_and_applied_jobs_are_never_touched(seeded: None) -> None:
    with Session(engine) as s:
        company = make_company(s, ("Tom Lead", "Tech Lead", "apollo_dump"),
                               ("Carl Cto", "CTO", "apollo_dump"))
        mine = make_job(s, company)
        tom = s.exec(select(Contact).where(Contact.company_id == company.id,
                                           Contact.full_name == "Tom Lead")).one()
        contacts.set_contact(s, mine, tom)
        assert not contacts.resolve(s, mine).changed and mine.contact_id == tom.id
        applied = make_job(s, company, stage=Stage.done)
        assert not contacts.resolve(s, applied).changed and applied.contact_id is None
        contacts.clear_contact(s, mine)
        assert s.get(Contact, mine.contact_id).full_name == "Carl Cto"
        s.rollback()


def test_resolution_writes_events(seeded: None) -> None:
    with Session(engine) as s:
        app = make_job(s, make_company(s, ("Carl Cto", "CTO", "apollo_dump")))
        contacts.resolve(s, app)
        events = s.exec(select(ApplicationEvent).where(
            ApplicationEvent.application_id == app.id,
            ApplicationEvent.kind == EventKind.contact_resolved)).all()
        assert events and "Carl Cto" in events[-1].message
        s.rollback()


def test_skip_hides_until_tomorrow_and_the_counter_resets_at_midnight(seeded: None) -> None:
    with Session(engine) as s:
        company = make_company(s)
        contacts.resolve(s, make_job(s, company, score=99))
        contacts.lookup_skip(s, company.id)
        ids = [r.company.id for r in contacts.lookup_queue(s).rows]
        assert company.id not in ids
        later = datetime.now(UTC) + timedelta(days=1, hours=1)
        assert company.id in [r.company.id for r in contacts.lookup_queue(s, later).rows]
        contacts.lookup_not_found(s, company.id)
        assert contacts.used_today(s) >= 1
        assert contacts.used_today(s, later) == 0  # a new day starts at local midnight
        s.rollback()


def test_report_counts_by_track_and_country(seeded: None) -> None:
    with Session(engine) as s:
        with_contact = make_company(s, ("Carl Cto", "CTO", "apollo_dump"))
        make_job(s, with_contact)
        make_job(s, make_company(s))
        out = contacts.match_all(s)
        track = next(g for g in out["by_track"] if g["group"] == "T-contacts")
        assert track["with_contact"] >= 1 and track["queued"] >= 1
        assert out["totals"]["jobs"] == sum(g["jobs"] for g in out["by_country"])
        s.rollback()


def test_discovery_hook_resolves_new_jobs(seeded: None) -> None:
    with Session(engine) as s:
        app = make_job(s, make_company(s, ("Carl Cto", "CTO", "apollo_dump")))
        s.commit()
        job_id, app_id = app.job_id, app.id
    from app.services.discovery import after_discovery

    after_discovery(engine, [job_id], queue=None)
    with Session(engine) as s:
        assert s.get(Application, app_id).contact_tier == ContactTier.apollo_dump


def test_add_contact_rejects_a_known_email(seeded: None) -> None:
    with Session(engine) as s:
        company = make_company(s)
        contacts.add_contact(s, company.id, full_name="A B", title=None, email="dup@x.io",
                             linkedin_url=None, source=ContactSource.manual)
        with pytest.raises(contacts.ContactError):
            contacts.add_contact(s, company.id, full_name="C D", title=None, email="DUP@x.io",
                                 linkedin_url=None, source=ContactSource.manual)
        s.rollback()


def test_lookup_status_values() -> None:
    assert {s.value for s in LookupStatus} == {"queued", "found", "not_found", "skipped", "never"}


# ------------------------------------------------------------------------------------ API


def test_import_through_the_api_with_preview_polling_and_hash_guard(client) -> None:  # noqa: ANN001
    import json
    import time

    co = f"Api Co {next(_n)}"
    raw = csv_bytes(f"Ana,Api,CTO,{co},ana{next(_n)}@api.io", f"Bo,Api,Recruiter,{co},")
    [preview] = client.post("/api/contacts/import/preview",
                            files=[("files", ("api.csv", raw, "text/csv"))]).json()
    assert preview["total_rows"] == 2 and preview["mapping"]["company"] == "Company"
    assert preview["already_imported_at"] is None
    r = client.post("/api/contacts/import", files={"file": ("api.csv", raw, "text/csv")},
                    data={"mapping": json.dumps(preview["mapping"])})
    assert r.status_code == 202
    run_id = r.json()["id"]
    for _ in range(100):
        run = client.get(f"/api/contacts/imports/{run_id}").json()
        if run["status"] != "running":
            break
        time.sleep(0.05)
    assert run["status"] == "done" and run["created"] == 2
    again = client.post("/api/contacts/import", files={"file": ("api.csv", raw, "text/csv")},
                        data={"mapping": json.dumps(preview["mapping"])})
    assert again.status_code == 409
    bad = client.post("/api/contacts/import", files={"file": ("x.csv", raw, "text/csv")},
                      data={"mapping": json.dumps({"email": "Email"})})
    assert bad.status_code == 422


def test_lookup_and_per_job_contact_endpoints(client) -> None:  # noqa: ANN001
    with Session(engine) as s:
        company = make_company(s)
        app = make_job(s, company, score=97)
        contacts.resolve(s, app)
        s.commit()
        company_id, app_id, job_id = company.id, app.id, app.job_id
    queue = client.get("/api/contacts/lookups").json()
    assert company_id in [i["company_id"] for i in queue["items"]]
    after = client.post(f"/api/contacts/lookups/{company_id}/found",
                        json={"full_name": "Lia Found", "title": "CTO", "email": "lia@f.io"})
    assert after.status_code == 200 and after.json()["used_today"] >= 1
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["contact"]["full_name"] == "Lia Found"
    assert detail["contact"]["role_label"] == "CTO"
    assert detail["application"]["contact_tier"] == "lookup_found"
    assert detail["lookup_status"] == "found"
    mine = client.post(f"/api/applications/{app_id}/contact",
                       json={"full_name": "Max Manual", "title": "Tech Lead"})
    assert mine.json()["contact"]["full_name"] == "Max Manual"
    cleared = client.delete(f"/api/applications/{app_id}/contact").json()
    assert cleared["contact"]["full_name"] == "Lia Found"  # CTO outranks the tech lead


def test_contacts_settings_are_validated_and_rerank(client) -> None:  # noqa: ANN001
    bad = client.put("/api/settings/contacts", json={"value": {"role_ranking": []}})
    assert bad.status_code == 422
    custom = [{"label": "Recruiters first", "keywords": ["recruiter"]}]
    ok = client.put("/api/settings/contacts", json={"value": {"role_ranking": custom}})
    assert ok.status_code == 200
    with Session(engine) as s:
        recruiter = s.exec(select(Contact).where(Contact.title == "Recruiter")).first()
        assert recruiter.role_rank == 0
    client.put("/api/settings/contacts", json={"value": {"role_ranking": DEFAULT_ROLE_RANKING}})
    assert client.put("/api/settings/lookup", json={"value": {"daily_cap": 0}}).status_code == 422


def test_companies_list_filters(client) -> None:  # noqa: ANN001
    body = client.get("/api/companies", params={"filter": "needs_lookup"}).json()
    assert body["total"] == len(body["items"]) or body["total"] > 100
    assert all(i["contact_count"] == 0 for i in body["items"])
    has = client.get("/api/companies", params={"filter": "has_contacts"}).json()
    assert has["items"] and all(i["contact_count"] > 0 for i in has["items"])


# ------------------------------------------------------------------ queue order, never, boards


def test_queue_orders_shortlisted_then_fit_then_newest_with_reasons(seeded: None) -> None:
    with Session(engine) as s:
        now = datetime.now(UTC)
        shortlisted, high, tie_old, tie_new = (make_company(s) for _ in range(4))
        make_job(s, shortlisted, stage=Stage.shortlisted, score=60)
        make_job(s, high, score=99)
        old = make_job(s, tie_old, score=95)
        new = make_job(s, tie_new, score=95)
        s.get(Job, old.job_id).discovered_at = now - timedelta(days=9)
        s.get(Job, new.job_id).discovered_at = now - timedelta(days=1)
        s.flush()
        contacts.resolve_many(s, contacts._open_apps(s, company_ids={
            shortlisted.id, high.id, tie_old.id, tie_new.id}))
        rows = [r for r in contacts.lookup_queue(s, limit=5000).rows
                if r.company.id in {shortlisted.id, high.id, tie_old.id, tie_new.id}]
        assert [r.company.id for r in rows] == [shortlisted.id, high.id, tie_new.id, tie_old.id]
        assert rows[0].reason == "1 shortlisted job"
        assert rows[1].reason == "Best fit 99"
        assert rows[2].reason.startswith("Best fit 95") or "newest" in rows[2].reason
        assert "newest job 9 days ago" in rows[3].reason
        s.rollback()


def test_never_look_up_sends_jobs_to_web_apply_even_with_contacts(seeded: None) -> None:
    with Session(engine) as s:
        board = make_company(s, ("Tina Talent", "Recruiter", "apollo_dump"))
        app = make_job(s, board)
        contacts.resolve(s, app)
        assert app.contact_id is not None
        contacts.lookup_never(s, board.id)
        assert (app.contact_tier, app.contact_id) == (ContactTier.none, None)
        assert board.id not in [r.company.id for r in contacts.lookup_queue(s, limit=5000).rows]
        contacts.lookup_again(s, board.id)
        assert app.contact_id is not None
        s.rollback()


@pytest.mark.parametrize(("name", "descriptions", "tracks", "expected"), [
    ("RemoteJobsOne", ["x"] * 9, ["A", "B"],
     ["name contains “remote”", "9 open jobs across 2 tracks"]),
    ("Hire Feed", ["x"], ["A"], ["name contains “hire”"]),
    # "for a client" in only 2 of 9 listings: not a signal; many jobs alone is too weak
    ("Acme Consulting", ["Pour le compte d'un client, nous cherchons"] * 2 + ["x"] * 7,
     ["A", "B"], []),
    ("Staffy", ["Pour le compte d'un client, nous cherchons"] * 5 + ["x"] * 4, ["A", "B"],
     ["5 of 9 listings are “for a client”", "9 open jobs across 2 tracks"]),
    ("Nomadia", ["We build routing software"], ["A"], []),
])
def test_aggregator_signals(name: str, descriptions: list[str], tracks: list[str],
                            expected: list[str]) -> None:
    from app.services.aggregators import signals

    company = Company(name=name, normalized_name=name.lower())
    jobs = [Job(title="Engineer", description=d, matched_track=tracks[i % len(tracks)],
                source="adzuna", external_id=str(i), url="u", company_id=0, dedupe_key=str(i))
            for i, d in enumerate(descriptions)]
    assert signals(company, jobs) == expected


# ---------------------------------------------------------------------------------- merges


def test_merge_suggestions_confirm_and_reject(seeded: None) -> None:
    from app.services import company_merge, ingest

    with Session(engine) as s:
        n = next(_n)
        base = Company(name=f"Mergeco{n}", normalized_name=f"mergeco{n}")
        belgium = Company(name=f"Mergeco{n} Belgium", normalized_name=f"mergeco{n} belgium")
        other = Company(name=f"Mergeco{n} Robotics", normalized_name=f"mergeco{n} robotics")
        s.add_all([base, belgium, other])
        s.flush()
        s.add(Contact(company_id=base.id, full_name="Carl Cto", title="CTO",
                      normalized_name="carl cto", role_rank=0))
        app = make_job(s, belgium)
        make_job(s, other)
        pairs = {(x.a.id, x.b.id) for x in company_merge.suggestions(s, limit=10_000)}
        assert (base.id, belgium.id) in pairs
        assert not any(other.id in p for p in pairs)  # "robotics" is a different company
        company_merge.merge(s, base.id, belgium.id)
        assert s.get(Job, app.job_id).company_id == base.id
        assert s.get(Contact, app.contact_id).full_name == "Carl Cto"  # re-matched after merge
        assert company_merge.resolve_alias(s, f"mergeco{n} belgium").id == base.id
        assert ingest._company(s, f"Mergeco{n} Belgium").id == base.id  # future jobs land here
        assert not any(base.id in p for p in {(x.a.id, x.b.id)
                                              for x in company_merge.suggestions(s, limit=10_000)})
        third = Company(name=f"Mergeco{n} Spain", normalized_name=f"mergeco{n} spain")
        s.add(third)
        s.flush()
        make_job(s, third)
        company_merge.reject(s, base.id, third.id)
        assert (base.id, third.id) not in {(x.a.id, x.b.id)
                                          for x in company_merge.suggestions(s, limit=10_000)}
        s.rollback()


def test_merge_and_size_endpoints(client) -> None:  # noqa: ANN001
    with Session(engine) as s:
        company = make_company(s, ("Rita Recruiter", "Recruiter", "apollo_dump"),
                               ("Carl Cto", "CTO", "apollo_dump"))
        app = make_job(s, company)
        contacts.resolve(s, app)
        s.commit()
        cid, job_id = company.id, app.job_id
    assert client.get(f"/api/jobs/{job_id}").json()["contact"]["full_name"] == "Rita Recruiter"
    r = client.patch(f"/api/companies/{cid}/size", json={"employees": 20})
    assert r.status_code == 200 and r.json()["small"] and r.json()["size_label"] == "20 employees"
    assert r.json()["contacts"][0]["full_name"] == "Carl Cto"
    assert client.get(f"/api/jobs/{job_id}").json()["contact"]["full_name"] == "Carl Cto"
    assert client.get("/api/company-merges").status_code == 200
    same = client.post("/api/company-merges", json={"keep_id": cid, "merge_id": cid})
    assert same.status_code == 422
    bad = client.put("/api/settings/contacts", json={"value": {
        "role_ranking": DEFAULT_ROLE_RANKING, "small_order": ["Nope"]}})
    assert bad.status_code == 422
