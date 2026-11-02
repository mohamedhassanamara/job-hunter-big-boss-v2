"""Phone / location visibility on the CV header (Settings → Candidate → Visibility)."""
import pytest

from app.services import cv_render
from app.services.cv_pool import Pool, cv_profile
from app.services.cv_render import CVDocument, load_template, render_tex

PROFILE = {"full_name": "Ada Lovelace", "based_in": "Tunis, Tunisia", "phone": "+216 11 222 333",
           "email": "ada@example.com",
           "links": [{"type": "github", "label": "", "url": "https://github.com/ada"}]}
TEMPLATES = ["default"] + (
    ["updated1"] if (cv_render.USER_TEMPLATES / "updated1" / "cv.tex.j2").exists() else [])


def pool(show_phone: bool = True, show_location: bool = True) -> Pool:
    return Pool(items={}, profile=dict(PROFILE),
                visibility={"show_phone": show_phone, "show_location": show_location})


def render(p: Pool, template: str) -> str:
    return render_tex(CVDocument(), cv_profile(p), load_template(template))


@pytest.mark.parametrize("template", TEMPLATES)
@pytest.mark.parametrize("show_phone", [True, False])
@pytest.mark.parametrize("show_location", [True, False])
def test_four_combinations(template: str, show_phone: bool, show_location: bool) -> None:
    tex = render(pool(show_phone, show_location), template)
    assert ("+216 11 222 333" in tex) is show_phone
    assert ("Tunis, Tunisia" in tex) is show_location
    assert "ada@example.com" in tex and "github.com/ada" in tex  # the rest is untouched
    # no orphaned separator or empty item: the contact line is only what is shown
    assert "\\hspace{1pt}$|$\\hspace{1pt} \\\\" not in tex
    assert "$|$\\hspace{1pt} \n" not in tex


def test_hiding_both_leaves_a_clean_contact_line() -> None:
    tex = render(pool(False, False), "default")
    header = tex.split(r"\begin{center}")[1].split(r"\end{center}")[0]
    assert "faIcon{phone}" not in header and "map-marker-alt" not in header
    assert header.count("$|$") == 0
    assert "faIcon{envelope}" in header


def test_hiding_never_changes_the_stored_profile() -> None:
    p = pool(False, False)
    cv_profile(p)
    assert p.profile["phone"] == PROFILE["phone"] and p.profile["based_in"] == "Tunis, Tunisia"


def test_load_pool_reads_the_setting(client) -> None:
    from sqlmodel import Session

    from app.db import engine
    from app.services.cv_pool import load_pool

    with Session(engine) as s:
        assert load_pool(s).visibility == {"show_phone": True, "show_location": True}
    client.put("/api/settings/output_visibility",
               json={"value": {"show_phone": False, "show_location": True}})
    with Session(engine) as s:
        p = load_pool(s)
        assert p.visibility == {"show_phone": False, "show_location": True}
        shown = cv_profile(p)
        assert shown.phone == ""
        assert shown.location == (p.profile.get("based_in") or "").strip()
    client.put("/api/settings/output_visibility",
               json={"value": {"show_phone": True, "show_location": True}})
