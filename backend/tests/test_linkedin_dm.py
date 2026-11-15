"""The post-acceptance LinkedIn DM: the six persona x alumni examples pass the code checks and
every check has a failing case. Offline, no model."""

import pytest
from sqlmodel import Session

from app.db import engine
from app.services import linkedin_check as lc
from app.services.cv_pool import load_pool

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
