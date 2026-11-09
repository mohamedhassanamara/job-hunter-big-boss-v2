"""Filler relevance: after the listing's matches, skills that share a job or project with a
matched skill, then the track's pins, then the rest with the track's groups first. Group
membership alone promotes nothing. No model calls."""
import pytest

from app.models import ExperienceItem
from app.services import skill_ledger as sl
from app.services.cv_pool import Pool

BACKEND_LISTING = ("We are hiring a backend developer. You have strong experience with Python "
                   "and SQL, you version everything in Git, and you care about testing. ")
MOBILE_LISTING = ("Mobile engineer wanted. You build apps with Flutter and Dart, you know "
                  "state management and you ship to the stores. ")

GROUPS = {
    "Core Languages": ["Dart", "Python", "SQL", "Java", "Bash", "Kotlin", "Swift"],
    "DevOps, Cloud & Release": ["Docker", "Docker Compose", "Git", "GitHub Actions (CI/CD)",
                                "Firebase (Auth, Crashlytics, Remote Config)",
                                "Google Play Console", "TestFlight", "Linux"],
    "Backend & Data Engineering": ["FastAPI", "Apache Airflow", "dbt", "DuckDB", "PostgreSQL",
                                   "Spring Boot"],
    "Mobile & Frontend": ["Flutter", "Riverpod", "Clean Architecture", "GoRouter", "Provider"],
}
BACKEND_EMPHASIS = {"skill_groups": ["Backend & Data Engineering", "Core Languages",
                                     "DevOps, Cloud & Release"],
                    "tags": ["Spring Boot", "FastAPI", "PostgreSQL", "Docker"]}
MOBILE_EMPHASIS = {"skill_groups": ["Mobile & Frontend", "Core Languages"],
                   "tags": ["Flutter", "Riverpod", "Clean Architecture", "GoRouter"]}
MOBILE_SKILLS = ["Kotlin", "Swift", "Dart", "TestFlight", "Google Play Console",
                 "Firebase (Auth, Crashlytics, Remote Config)"]
DATA_SKILLS = ["FastAPI", "Apache Airflow", "dbt", "DuckDB", "PostgreSQL"]

_ids = iter(range(1, 10_000))


def item(kind: str, title: str, tags: list[str], bullets: list[str] | None = None
         ) -> ExperienceItem:
    return ExperienceItem(id=next(_ids), kind=kind, title=title, org="X", tags=tags, tracks=[],
                          bullets=bullets or [], position=0)


def pool(items: list[ExperienceItem] | None = None, groups: dict | None = None,
         proofs: list[list[str]] | None = None, study: list[list[str]] | None = None) -> Pool:
    skill_items = [item("skill", title, tags) for title, tags in (groups or GROUPS).items()]
    everything = [*skill_items, *(items if items is not None else default_items())]
    p = Pool(items={i.id: i for i in everything}, profile={})
    for i in everything:
        p.by_kind.setdefault(i.kind, []).append(i)
    p.skill_proofs = [item("skill_proof", f"p{n}", tags) for n, tags in enumerate(proofs or [])]
    p.study_tags = {next(_ids): tags for tags in study or []}
    return p


def default_items() -> list[ExperienceItem]:
    return [
        item("project", "Lakehouse", ["python", "dbt", "apache airflow", "duckdb"],
             ["Ran the pipelines on Docker Compose with SQL models."]),
        item("project", "Parsing API", ["python", "fastapi"],
             ["Stored the results in a relational store and queried them with SQL."]),
        item("job", "Mobile developer", ["flutter", "riverpod", "gorouter"],
             ["Moved the app from Provider to Riverpod under Clean Architecture."]),
        item("job", "Platform engineer", ["spring-boot"], ["Managed releases with Git."]),
    ]


def run(p: Pool, listing: str, **kw):  # noqa: ANN003, ANN201
    return sl.select_skills(p, title="Developer", description=listing, min_items=1, **kw)


def index(out, name: str) -> int:  # noqa: ANN001
    return out.display.index(name)


# ------------------------------------------------------------------------------ ordering


def test_a_python_listing_ranks_the_data_skills_before_the_mobile_ones() -> None:
    out = run(pool(), BACKEND_LISTING, emphasis=BACKEND_EMPHASIS)
    assert out.skills[0].reason == "jd"
    last_data = max(index(out, s) for s in DATA_SKILLS)
    first_mobile = min(index(out, s) for s in MOBILE_SKILLS)
    assert last_data < first_mobile
    reasons = {s.skill: s.reason for s in out.skills}
    assert reasons["Python"] == reasons["SQL"] == reasons["Git"] == "jd"
    assert all(reasons[s] == "cooc" for s in ("FastAPI", "Apache Airflow", "dbt", "DuckDB"))
    assert reasons["PostgreSQL"] == "pin"  # the Backend track's emphasis tag
    # the order is jd, cooc, pin, fill
    order = ["jd", "cooc", "pin", "fill"]
    assert [s.reason for s in out.skills] == sorted([s.reason for s in out.skills],
                                                    key=order.index)


def test_group_membership_alone_promotes_nothing() -> None:
    out = run(pool(), BACKEND_LISTING, emphasis=BACKEND_EMPHASIS)
    reasons = {s.skill: s.reason for s in out.skills}
    # Kotlin and Swift share Core Languages with the matched Python and SQL; Linux and Firebase
    # share DevOps with the matched Git. No item ties them to a match: plain fill
    for name in ("Kotlin", "Swift", "Linux", "Firebase (Auth, Crashlytics, Remote Config)"):
        assert reasons[name] == "fill"


def test_skills_with_more_matched_partners_come_first() -> None:
    items = [item("project", "A", ["python", "sql", "tool one"]),
             item("project", "B", ["python", "tool two"]),
             item("project", "C", ["python", "tool two"])]
    groups = {"G": ["Python", "SQL", "Tool Two", "Tool One"]}
    out = run(pool(items, groups), "You need Python and SQL.")
    # Tool One appears with Python and SQL (2 partners); Tool Two with Python only, in 2 items
    assert out.display == ["Python", "SQL", "Tool One", "Tool Two"][:len(out.display)]
    assert [s.reason for s in out.skills] == ["jd", "jd", "cooc", "cooc"]


def test_a_mobile_listing_stays_mobile_first() -> None:
    out = run(pool(), MOBILE_LISTING, emphasis=MOBILE_EMPHASIS)
    assert out.display[:2] == ["Flutter", "Dart"]
    mobile = ["Riverpod", "Clean Architecture", "GoRouter", "Provider"]
    non_mobile = ["Python", "SQL", "FastAPI", "Apache Airflow", "dbt", "Docker", "Git"]
    assert max(index(out, s) for s in mobile) < min(index(out, s) for s in non_mobile)
    assert {s.skill: s.reason for s in out.skills}["Riverpod"] == "cooc"


def test_the_emphasized_groups_come_first_in_the_rest() -> None:
    # no item ties anything to the listing: steps 2 and 3 are empty, step 4 is the group order
    p = pool(items=[])
    emphasis = {"skill_groups": ["Mobile & Frontend", "Backend & Data Engineering"], "tags": []}
    out = run(p, "You need Python.", emphasis=emphasis)
    rest = out.display[1:]
    assert rest[:5] == GROUPS["Mobile & Frontend"]  # emphasized first, in your order
    assert rest[5:11] == GROUPS["Backend & Data Engineering"]
    assert rest[11:17] == [s for s in GROUPS["Core Languages"] if s != "Python"]  # then as stored
    assert rest[17:19] == GROUPS["DevOps, Cloud & Release"][:2]
    assert all(s.reason == "fill" for s in out.skills[1:])


def test_a_track_with_no_pins_and_no_emphasis_falls_through() -> None:
    out = run(pool(), BACKEND_LISTING, keep={}, emphasis={})  # no skill_keep, no emphasis
    assert out.skills and {s.reason for s in out.skills} <= {"jd", "cooc", "fill"}
    assert max(index(out, s) for s in DATA_SKILLS if s != "PostgreSQL") < min(
        index(out, s) for s in MOBILE_SKILLS)
    none = run(pool(), BACKEND_LISTING, keep=None, emphasis=None)
    assert none.display == out.display
    partial = run(pool(), BACKEND_LISTING, emphasis={"tags": ["Docker"]})  # no groups listed
    assert partial.skills[0].reason == "jd"


def test_pins_come_from_skill_keep_and_the_emphasis_tags() -> None:
    out = run(pool(), BACKEND_LISTING, keep={"x": ["TestFlight"]},
              emphasis={"skill_groups": [], "tags": ["Linux"]})
    reasons = {s.skill: s.reason for s in out.skills}
    assert reasons["TestFlight"] == "pin" and reasons["Linux"] == "pin"
    assert index(out, "TestFlight") < index(out, "Linux")  # skill_keep first, then the tags


# --------------------------------------------------------------------------- only tier 1


def test_nothing_outside_tier_one_ever_enters_the_list() -> None:
    items = [item("project", "Side", ["python", "tier two tool"],
                  ["Wrote it with Tier Two Tool and Tier Three Tool."])]
    p = pool(items, proofs=[["Tier Two Tool"]], study=[["Tier Three Tool"]])
    out = run(p, BACKEND_LISTING, keep={"x": ["Tier Two Tool"]},
              emphasis={"skill_groups": [], "tags": ["Tier Three Tool"]})
    assert {"Tier Two Tool", "Tier Three Tool"}.isdisjoint(out.display)
    assert all(s.tier == 1 for s in out.skills if s.reason != "jd")
    # the listing may still name them (tier 2 and 3 enter only by the listing)
    named = run(p, BACKEND_LISTING + "You know Tier Two Tool.")
    assert {s.skill: s.reason for s in named.skills}["Tier Two Tool"] == "jd"


def test_free_form_item_tags_never_become_skills() -> None:
    items = [item("project", "Side", ["python", "mentoring", "web"])]
    out = run(pool(items), BACKEND_LISTING)
    assert "mentoring" not in out.display and "web" not in out.display


# ------------------------------------------------------------------------------- evidence


@pytest.mark.parametrize(("bullet", "found"), [
    ("Version control with Git.", True),
    ("Hosted on GitHub.", False),  # inside a longer word
    ("Mirrored to Gitea.", False),
    ("Used git daily.", False),  # bullets are case-sensitive: you write it "Git"
    ("Git, then Docker.", True),
    ("A Git-based flow.", False),  # a hyphenated phrase is not the skill
    ("Wrote R scripts.", None),  # handled by the one-letter cases below
])
def test_bullet_evidence_is_case_sensitive_and_a_whole_word(bullet: str, found: bool | None
                                                             ) -> None:
    if found is None:
        return
    assert sl.word_exact(bullet, "Git") is found


@pytest.mark.parametrize(("text", "found"), [
    ("We ran R, Python and SQL.", True),
    ("Funded R&D programme.", False),
    ("The R/Python bridge.", False),
    ("Bar", False),
    ("Wrote R scripts.", True),
    ("(R)", True),
])
def test_a_one_letter_skill_is_not_found_inside_words_or_symbols(text: str, found: bool) -> None:
    assert sl.word_exact(text, "R") is found


@pytest.mark.parametrize(("text", "found"), [
    ("We go to market.", False),  # case-sensitive: "Go" is a skill, "go" a verb
    ("Go-to-market plan.", False),
    ("Wrote Go services.", True),
    ("Gopher", False),
])
def test_go_is_not_the_verb(text: str, found: bool) -> None:
    assert sl.word_exact(text, "Go") is found


@pytest.mark.parametrize(("tags", "found"), [
    ("git\nflutter", True),  # tags are matched in any case
    ("GIT", True),
    ("github-actions", False),
    ("gitea", False),
    ("go\npython", True),
    ("go-to-market", False),
])
def test_tags_are_matched_in_any_case_as_whole_words(tags: str, found: bool) -> None:
    term = "Go" if tags.startswith("go") else "Git"
    assert sl.word_any_case(tags, term) is found


def test_cooccurrence_uses_the_same_rules_end_to_end() -> None:
    items = [item("project", "A", ["python"], ["Hosted on GitHub, mirrored to Gitea."]),
             item("project", "B", ["python"], ["used git daily"]),
             item("project", "C", ["sql"], ["Project notes. Git"])]
    groups = {"G": ["Python", "SQL", "Git", "Rust"]}
    out = run(pool(items, groups), "You need Python.")
    reasons = {s.skill: s.reason for s in out.skills}
    # only C writes "Git" as a word, but C has no Python: Git ties to no matched skill
    assert reasons["Git"] == "fill"
    items.append(item("project", "D", ["python"], ["Daily Git use."]))
    out = run(pool(items, groups), "You need Python.")
    assert {s.skill: s.reason for s in out.skills}["Git"] == "cooc"
