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
    assert header.count("$|$") == 1  # email + github share one line
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


@pytest.mark.parametrize(("n", "sizes"), [(0, []), (1, [1]), (2, [2]), (3, [3]), (4, [2, 2]),
                                          (5, [3, 2]), (6, [3, 3]), (7, [3, 2, 2])])
def test_header_lines_are_balanced(n: int, sizes: list[int]) -> None:
    assert cv_render.header_line_sizes(n) == sizes


LINKS = [{"type": t, "label": "", "url": f"https://{t}.example.com/ada"}
         for t in ("linkedin", "github", "portfolio")]


@pytest.mark.parametrize(("show_phone", "show_location", "sizes"), [
    (True, True, [3, 3]), (False, True, [3, 2]), (True, False, [3, 2]), (False, False, [2, 2])])
def test_line_grouping_per_visibility_combination(show_phone: bool, show_location: bool,
                                                  sizes: list[int]) -> None:
    p = pool(show_phone, show_location)
    p.profile["links"] = LINKS
    lines = cv_render.header_lines(cv_profile(p), load_template("default").config)
    assert [len(x) for x in lines] == sizes
    flat = [i["label"] for line in lines for i in line]
    # contact items first (location, phone, email), then the links in their order
    expected = ([PROFILE["based_in"]] if show_location else []) \
        + ([PROFILE["phone"]] if show_phone else []) + ["ada@example.com"] \
        + [f"{t}.example.com/ada" for t in ("linkedin", "github", "portfolio")]
    assert flat == expected
    assert max(sizes) - min(sizes) <= 1


@pytest.mark.parametrize(("show_phone", "show_location"), [(True, True), (False, True),
                                                           (True, False), (False, False)])
def test_rendered_header_has_the_expected_number_of_text_lines(
        tmp_path, show_phone: bool, show_location: bool) -> None:
    """Compiled: one page, and the header's text lines are the grouped lines (no natural
    wrapping adds one)."""
    import shutil

    if shutil.which("latexmk") is None:
        pytest.skip("needs TeX Live")
    import pymupdf

    p = pool(show_phone, show_location)
    p.profile["links"] = LINKS
    tex = render_tex(CVDocument(), cv_profile(p), load_template("default"))
    out = cv_render.compile_tex(tex, tmp_path, "h")
    assert out.ok and out.pages == 1, out.error
    words = pymupdf.open(out.pdf_path)[0].get_text("words")
    rows: list[float] = []
    for w in sorted(words, key=lambda w: w[1]):
        if not rows or w[1] - rows[-1] > 4:  # icon glyphs sit a point or two off the baseline
            rows.append(w[1])
    expected = len(cv_render.header_lines(cv_profile(p), load_template("default").config))
    assert len(rows) == 1 + expected, rows  # the name, then one text row per grouped line
