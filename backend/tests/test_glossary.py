"""The career-changer glossary: only your own entries, validated, used as known vocabulary for
the item that contains your first words, passed to the generators and the claim verifier as facts,
and never an excuse for a tool, number or years. Offline."""

from sqlmodel import Session

from app.db import engine
from app.models import ExperienceItem
from app.providers.base import SummarySentence
from app.services import cv_check, glossary, verifier
from app.services.cv_pool import Pool

ENTRIES = [{"from": "Offline sync", "to": "incremental data synchronisation", "note": ""},
           {"from": "multi-service backend", "to": "distributed systems", "note": "mobile API"}]


def pool(profile: dict | None = None) -> Pool:
    item = ExperienceItem(id=7, kind="job", title="Mobile Engineer", org="Acme",
                          bullets=["Built offline sync for a Flutter app used by 40K people",
                                   "Ran a multi-service backend for the app"], tags=["Flutter"])
    other = ExperienceItem(id=8, kind="job", title="Intern", org="Beta",
                           bullets=["Wrote unit tests"], tags=["Dart"])
    return Pool(items={7: item, 8: other},
                profile={"glossary": ENTRIES} if profile is None else profile,
                by_kind={"job": [item, other]})


def test_only_valid_entries_survive_and_repeats_are_dropped() -> None:
    raw = [*ENTRIES, {"from": "offline sync", "to": "other"}, {"from": "", "to": "x"},
           {"from": "same", "to": "Same"}, "junk", {"from": "a", "to": "b", "note": " n  o "}]
    got = glossary.clean(raw)
    assert [e["from"] for e in got] == ["Offline sync", "multi-service backend", "a"]
    assert got[-1]["note"] == "n o" and glossary.clean(None) == [] and glossary.clean("x") == []


def test_a_term_is_known_only_where_its_first_words_are() -> None:
    profile = {"glossary": ENTRIES}
    assert glossary.known_terms("We shipped offline sync.", profile) == [
        "incremental data synchronisation"]
    assert glossary.known_terms("Nothing relevant here", profile) == []
    assert glossary.known_terms("offlinesync", profile) == []  # whole words only
    assert "distributed systems" in glossary.expand("a multi-service backend", profile)


def test_the_pool_and_cited_items_know_your_terms_but_only_for_their_own_work() -> None:
    p = pool()
    assert "distributed systems" in p.all_text()
    assert "distributed systems" in cv_check.cited_text(p, [7])
    assert "distributed systems" not in cv_check.cited_text(p, [8])  # the intern item lacks it
    assert "distributed systems" not in pool({}).all_text()


def claim_problems(text: str, ids: list[int], p: Pool) -> list[str]:
    return cv_check.sentence_problems(SummarySentence(text=text, citations=ids), p, {3})


def test_a_glossary_term_passes_the_grounding_check_where_the_pool_says_it() -> None:
    text = "Operated distributed systems behind a Flutter app."
    without = claim_problems(text, [7], pool({}))
    assert any("distributed systems" in x for x in without)  # flagged without your glossary
    assert claim_problems(text, [7], pool()) == []  # your own term for the same work


def test_it_never_adds_a_number_a_tool_or_scale() -> None:
    p = pool()
    assert any("90" in x for x in claim_problems(
        "Operated distributed systems used by 90K people.", [7], p))
    assert any("BigQuery" in x for x in claim_problems(
        "Operated distributed systems with BigQuery.", [7], p))
    # the term is known for the item that has your first words, not for another item's tools
    assert "incremental data synchronisation" not in cv_check.cited_text(p, [8])


def test_prompt_facts_and_the_verifier_facts_only_exist_when_you_wrote_entries() -> None:
    assert glossary.prompt_facts({}) == {} and glossary.verifier_lines({}) == ""
    facts = glossary.prompt_facts({"glossary": ENTRIES})["glossary"]
    assert facts[0] == {"from": "Offline sync", "to": "incremental data synchronisation"}
    assert facts[1]["note"] == "mobile API"
    assert "“multi-service backend” = “distributed systems”" in glossary.verifier_lines(
        {"glossary": ENTRIES})


def test_the_verifier_is_told_in_its_facts_source(seeded: None) -> None:
    with Session(engine) as s:
        from app.services.cv_pool import load_pool

        sources = verifier.candidate_sources(s, load_pool(s), None)
    assert "Glossary (written by the candidate" in sources["facts"]  # the sandbox's sample terms


def test_generators_get_the_glossary_as_facts(seeded: None) -> None:
    from app.models import Application
    from app.services import cover_letter, cv_service
    from app.services.cv_pool import load_pool

    with Session(engine) as s:
        app = s.query(Application).first()
        pool_ = load_pool(s)
        cv_req = cv_service.build_request(s, app, pool_)
        assert cv_req.facts["glossary"][0]["from"] == "offline sync"
        from app.models import CVVersion

        cv = s.query(CVVersion).first()
        letter_req = cover_letter.build_request(s, app, cv, pool_, "en")
        assert letter_req.candidate["glossary"][0]["to"] == "incremental data synchronisation"


def test_settings_validation(client) -> None:  # noqa: ANN001
    base = client.get("/api/settings").json()["values"]["profile"]
    put = client.put
    ok = put("/api/settings/profile", json={"value": {**base, "glossary": ENTRIES}})
    assert ok.status_code == 200 and len(ok.json()["values"]["profile"]["glossary"]) == 2
    for bad in ([{"from": "x", "to": ""}], [{"from": "x", "to": "X"}],
                [{"from": "a", "to": "b"}, {"from": "A", "to": "c"}], "text",
                [{"from": "x" * 81, "to": "y"}]):
        r = put("/api/settings/profile", json={"value": {**base, "glossary": bad}})
        assert r.status_code == 422, bad
