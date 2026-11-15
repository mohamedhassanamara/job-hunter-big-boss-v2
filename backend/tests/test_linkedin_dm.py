"""The post-acceptance LinkedIn DM: the six persona x alumni examples pass the code checks and
every check has a failing case. Offline, no model."""

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import LinkedInOutreach
from app.models.enums import LinkedInGroup, LinkedInStatus
from app.providers.mock import MockLinkedInDrafter
from app.services import linkedin_check as lc
from app.services import linkedin_track as lt
from app.services.cv_pool import load_pool
from tests.test_ext_people import _h, _profile
from tests.test_linkedin_page import job_payload
from tests.test_linkedin_track import job_with_people

ROLE, COMPANY, FIRST, SCHOOL = "Mobile Engineer", "Acme", "Lea", "INSAT"

# Tone and length references from the brief, placeholders filled.
EXAMPLES = {
    ("peer", False): (
        "Thanks for connecting, {first}! Being upfront, I just applied for the {role} role at "
        "{company} and wanted to reach out directly rather than disappear into the ATS. I ship "
        "and maintain production apps day to day, so your team's work caught my eye. Do you "
        "happen to know if that opening is for your squad, or another team?"),
    ("peer", True): (
        "Thanks for connecting, {first}, always great to see a fellow {school} grad! Being "
        "upfront, I just applied for the {role} role at {company} and wanted to say hi directly. "
        "I build and release production apps, so I would love to know if you are working near "
        "that team or know who is driving the hire?"),
    ("lead", False): (
        "Thanks for connecting, {first}. I just submitted my application for the {role} role at "
        "{company}. I own delivery of production apps end to end, so the technical scope lined "
        "up well. Quick question: are you the hiring lead for this opening, or is another "
        "manager owning that search?"),
    ("lead", True): (
        "Thanks for connecting, {first}, fellow {school} software engineering alum here! I just "
        "applied for the {role} opening at {company} (I build and ship production apps) and "
        "wanted to reach out directly. Are you the one leading the search for this role, or "
        "could you point me to the right person on the engineering side?"),
    ("recruiter", False): (
        "Thanks for connecting, {first}! I just applied for the {role} position at {company} "
        "and wanted to drop a quick note. I build and ship production apps, so my background "
        "maps closely to the requirements. Are you handling screening for this role, or is "
        "another recruiter covering it?"),
    ("recruiter", True): (
        "Thanks for connecting, {first}, great to connect with a fellow {school} alum! I just "
        "applied for the {role} role at {company} (I build and ship production apps) and wanted "
        "to reach out directly. Are you covering this search, or is there someone else on your "
        "talent team I should connect with?"),
}
GOOD = EXAMPLES[("lead", False)].format(first=FIRST, role=ROLE, company=COMPANY, school=SCHOOL)


def ctx(persona: str = "lead", alumni: bool = False) -> lc.Context:
    with Session(engine) as s:
        pool = load_pool(s)
    return lc.Context(
        pool=pool, allowed_years={3}, job_text=f"{ROLE}\nBuild mobile apps", company=COMPANY,
        kind="dm", max_chars=600, alumni=alumni, school=SCHOOL,
        school_full="National Institute of Applied Sciences and Technologies (INSAT)",
        first_name=FIRST, group=persona, role=ROLE)


def kinds(text: str, persona: str = "lead", alumni: bool = False) -> dict[str, str]:
    return {v["type"]: v["severity"] for v in lc.check(text, ctx(persona, alumni))}


@pytest.mark.parametrize(("persona", "alumni"), list(EXAMPLES))
def test_every_calibrated_example_passes_the_checks(seeded: None, persona: str,
                                                    alumni: bool) -> None:
    text = EXAMPLES[(persona, alumni)].format(first=FIRST, role=ROLE, company=COMPANY,
                                              school=SCHOOL)
    assert len(text.split()) < lc.DM_MAX_WORDS
    assert kinds(text, persona, alumni) == {}, lc.check(text, ctx(persona, alumni))


def test_the_base_example_is_clean(seeded: None) -> None:
    assert kinds(GOOD) == {}


@pytest.mark.parametrize(("label", "text", "found", "severity"), [
    ("em-dash", GOOD.replace("end to end,", "end to end —"), "dash", "error"),
    ("en-dash", GOOD.replace("end to end,", "end to end –"), "dash", "error"),
    ("65 words", GOOD.replace("Quick question:", "Quick question: " + "really " * 30 + "so"),
     "length", "error"),
    ("banned connector", GOOD.replace("I own", "Additionally I own"), "banlist", "warning"),
    ("banned word", GOOD.replace("end to end", "seamlessly"), "banlist", "warning"),
    ("url", GOOD.replace("this opening", "this opening (https://example.com)"), "link", "error"),
    ("subject line", "Subject: Hello\n\n" + GOOD, "format", "warning"),
    ("sign-off", GOOD + "\n\nBest regards", "format", "warning"),
    ("call request", GOOD.replace("Quick question:", "Could we hop on a call?"),
     "meeting_ask", "warning"),
    ("no question", GOOD.rsplit("Quick question", 1)[0].strip(), "question", "warning"),
    ("no role", GOOD.replace(ROLE, "open"), "role", "warning"),
])
def test_each_check_has_a_failing_case(seeded: None, label: str, text: str, found: str,
                                       severity: str) -> None:
    assert kinds(text).get(found) == severity, (label, lc.check(text, ctx()))


def test_an_alumni_dm_must_name_the_school(seeded: None) -> None:
    assert kinds(GOOD, "lead", alumni=True).get("school") == "warning"


def test_a_non_alumni_dm_never_names_the_school(seeded: None) -> None:
    text = GOOD.replace("Thanks for connecting",
                        f"Fellow {SCHOOL} grad here, thanks for connecting")
    assert kinds(text).get("school") == "error"


def test_the_ceiling_is_strictly_under_65_words(seeded: None) -> None:
    base = f"Hi {FIRST}, I applied for the {ROLE} role at {COMPANY}"
    pad = lambda n: base + " " + " ".join(["word"] * (n - len(base.split()) - 2)) + " ok, who?"  # noqa: E731
    assert len(pad(64).split()) == 64 and "length" not in kinds(pad(64))
    assert len(pad(65).split()) == 65 and kinds(pad(65)).get("length") == "error"


# ---------------------------------------------------------------- the draft on acceptance

@pytest.mark.parametrize(("group", "alumni"), [
    (g, a) for g in (LinkedInGroup.peer, LinkedInGroup.lead, LinkedInGroup.recruiter)
    for a in (False, True)])
def test_the_mock_dm_passes_the_checks_for_all_six_variants(seeded: None, group: LinkedInGroup,
                                                            alumni: bool) -> None:
    with Session(engine) as s:
        app, _ = job_with_people(s)
        row = lt.add(s, app, full_name="Lea Dm", title="Engineer", linkedin_url=None,
                     group=group, alumni=alumni)
        row.status = LinkedInStatus.accepted
        s.commit()
        rid = row.id
        school = lt.school(load_pool(s))[0]
    done = lt.draft_followup(engine, rid, MockLinkedInDrafter())
    text = done.followup["text"]
    assert not [v for v in done.followup["violations"] if v["severity"] == "error"], done.followup
    assert (school in text) is alumni
    assert len(text.split()) < lc.DM_MAX_WORDS and "—" not in text and text.endswith("?")


def _make_row(status: LinkedInStatus) -> int:
    with Session(engine) as s:
        app, _ = job_with_people(s)
        row = lt.add(s, app, full_name="Pat Accept", title="Recruiter", linkedin_url=None,
                     group=LinkedInGroup.recruiter)
        row.status = status
        s.commit()
        return row.id


def test_your_click_on_they_accepted_drafts_the_dm_and_sends_nothing(seeded: None,
                                                                     client) -> None:  # noqa: ANN001
    rid = _make_row(LinkedInStatus.sent)
    out = client.post(f"/api/linkedin/people/{rid}/status", json={"status": "accepted"}).json()
    assert out["status"] == "accepted"
    with Session(engine) as s:
        row = s.get(LinkedInOutreach, rid)
        assert row.followup and row.followup["text"] and row.messaged_at is None
        assert row.status == LinkedInStatus.accepted  # drafted, never marked as sent


def test_other_statuses_draft_nothing(seeded: None, client) -> None:  # noqa: ANN001
    rid = _make_row(LinkedInStatus.to_contact)
    client.post(f"/api/linkedin/people/{rid}/status", json={"status": "sent"})
    with Session(engine) as s:
        assert not s.get(LinkedInOutreach, rid).followup


def test_an_existing_dm_is_not_redrafted(seeded: None) -> None:
    rid = _make_row(LinkedInStatus.accepted)
    with Session(engine) as s:
        row = s.get(LinkedInOutreach, rid)
        row.followup = {"text": "my own words?"}
        s.commit()
    assert lt.auto_draft_dm(engine, rid, MockLinkedInDrafter()) is False
    with Session(engine) as s:
        assert s.get(LinkedInOutreach, rid).followup["text"] == "my own words?"


def test_a_first_degree_capture_accepts_a_sent_invite_and_drafts(client) -> None:  # noqa: ANN001
    h = _h(client)
    company = "Acceptco Phase3"
    client.post("/api/ext/job", json={"payload": job_payload(
        url="https://www.linkedin.com/jobs/view/4099999911/", job_id="4099999911",
        title_parsed="Data Engineer", company_parsed=company,
        about={"lines": ["We build data pipelines with Spark and Airflow. " * 6]})}, headers=h)
    second = _profile(company, slug="sam-accept", name="Sam Accept")
    saved = client.post("/api/ext/person", json={"payload": second}, headers=h).json()
    assert saved["job"]
    with Session(engine) as s:
        row = s.exec(select(LinkedInOutreach).where(
            LinkedInOutreach.contact_id == saved["contact_id"])).one()
        rid = row.id
        assert row.status == LinkedInStatus.to_contact
    # a capture that still shows 2nd degree changes nothing
    client.post("/api/ext/person", json={"payload": second}, headers=h)
    with Session(engine) as s:
        assert s.get(LinkedInOutreach, rid).status == LinkedInStatus.to_contact
    client.post(f"/api/linkedin/people/{rid}/status", json={"status": "sent"})
    first = _profile(company, slug="sam-accept", name="Sam Accept")
    first["regions"][0]["lines"][1] = "· 1st"
    client.post("/api/ext/person", json={"payload": first}, headers=h)
    with Session(engine) as s:
        row = s.get(LinkedInOutreach, rid)
        assert row.status == LinkedInStatus.accepted and row.accepted_at
        assert row.followup and row.followup["text"] and row.messaged_at is None


def test_a_first_degree_capture_never_moves_other_statuses(client) -> None:  # noqa: ANN001
    h = _h(client)
    company = "Stillco Phase3"
    client.post("/api/ext/job", json={"payload": job_payload(
        url="https://www.linkedin.com/jobs/view/4099999922/", job_id="4099999922",
        title_parsed="Data Engineer", company_parsed=company,
        about={"lines": ["We build data pipelines with Spark and Airflow. " * 6]})}, headers=h)
    prof = _profile(company, slug="kim-still", name="Kim Still")
    prof["regions"][0]["lines"][1] = "· 1st"
    saved = client.post("/api/ext/person", json={"payload": prof}, headers=h).json()
    with Session(engine) as s:  # a new row (to_contact) stays: you haven't sent an invite
        row = s.exec(select(LinkedInOutreach).where(
            LinkedInOutreach.contact_id == saved["contact_id"])).one()
        assert row.status == LinkedInStatus.to_contact and not row.followup
