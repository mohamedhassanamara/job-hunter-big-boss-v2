"""CV templates: style golden test, escaping, optional header fields, empty sections."""

import json
import shutil
from pathlib import Path

import pytest

from app.services.cv_render import (
    ROOT,
    CVDocument,
    CVLink,
    CVProfile,
    CVRole,
    compile_tex,
    latex_escape,
    load_template,
    render_tex,
)

FIXTURE = json.loads((Path(__file__).parent / "fixtures/cv/reference_sample.json").read_text())
needs_latex = pytest.mark.skipif(shutil.which("latexmk") is None, reason="needs TeX Live")


def sample() -> tuple[CVDocument, CVProfile]:
    return CVDocument(**FIXTURE["document"]), CVProfile(**FIXTURE["profile"])


@needs_latex
def test_style_golden_default_template_matches_the_reference(tmp_path: Path) -> None:
    """The default template filled with reference-like data renders the reference pixel for
    pixel: same page count, same fonts, same image."""
    import pymupdf

    doc, profile = sample()
    gen = compile_tex(render_tex(doc, profile, load_template("default")), tmp_path, "gen")
    ref = compile_tex((ROOT / "templates/reference/cv.tex").read_text(), tmp_path, "ref")
    assert gen.ok and ref.ok, (gen.error, ref.error)
    assert gen.pages == ref.pages == 1
    with pymupdf.open(gen.pdf_path) as a, pymupdf.open(ref.pdf_path) as b:
        assert {f[3] for f in a[0].get_fonts()} == {f[3] for f in b[0].get_fonts()}
        pa, pb = a[0].get_pixmap(dpi=100), b[0].get_pixmap(dpi=100)
        assert (pa.width, pa.height) == (pb.width, pb.height)
        diff = sum(1 for i in range(0, len(pa.samples), 3)
                   if pa.samples[i:i + 3] != pb.samples[i:i + 3])
        assert diff / (pa.width * pa.height) < 0.001


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("40% & 100$", r"40\% \& 100\$"),
        ("C# and a_b", r"C\# and a\_b"),
        ("{x} ^ ~80%", r"\{x\} \^{} $\sim$80\%"),
        ("a\\b <c> |d|", r"a\textbackslash{}b \textless{}c\textgreater{} \textbar{}d\textbar{}"),
        ('built "Lovester" fast', "built ``Lovester'' fast"),
    ],
)
def test_latex_escape(text: str, expected: str) -> None:
    assert latex_escape(text) == expected


def test_every_special_character_is_escaped_in_the_output() -> None:
    doc = CVDocument(summary="Cut costs by 40% & shipped C# tools_v2 for $0 {fast} ~ #1")
    tex = render_tex(doc, CVProfile(full_name="A_B & Co"), load_template("default"))
    assert r"Cut costs by 40\% \& shipped C\# tools\_v2 for \$0 \{fast\} $\sim$ \#1" in tex
    assert r"{A\_B \& Co}" in tex


def _header(tex: str) -> str:
    return tex.split(r"\begin{center}")[1].split(r"\end{center}")[0]


def test_missing_header_fields_leave_no_icon_or_separator() -> None:
    profile = CVProfile(full_name="Ada", email="ada@example.com",
                        links=[CVLink(type="linkedin", url="https://linkedin.com/in/ada")])
    header = _header(render_tex(CVDocument(), profile, load_template("default")))
    assert "faIcon{phone}" not in header and "map-marker-alt" not in header
    assert "faIcon{github}" not in header
    assert "faIcon{envelope}" in header and "faIcon{linkedin}" in header
    assert header.count("$|$") == 0  # one item per line: nothing to separate
    assert r"\underline{linkedin.com/in/ada}" in header  # label derived from the URL


def test_name_only_header_has_no_trailing_break() -> None:
    header = _header(render_tex(CVDocument(), CVProfile(full_name="Ada"), load_template("default")))
    assert r"\\" not in header and "faIcon" not in header


@pytest.mark.parametrize("n", [0, 1, 3, 5])
def test_variable_number_of_links(n: int) -> None:
    links = [CVLink(type=t, url=f"https://example.com/{i}", label=f"l{i}")
             for i, t in enumerate(["github", "portfolio", "other", "linkedin", "github"][:n])]
    profile = CVProfile(full_name="Ada", phone="+1 555", links=links)
    header = _header(render_tex(CVDocument(), profile, load_template("default")))
    assert header.count(r"\href{https://example.com/") == n
    assert header.count("$|$") == max(0, n - 1)  # separators only between links
    if n:
        assert r"\faIcon{globe}" in header or n < 2


def test_empty_sections_are_omitted_entirely() -> None:
    doc = CVDocument(summary="Hi", roles=[CVRole(title="Dev", org="Acme", bullets=["Did x"])])
    tex = render_tex(doc, CVProfile(full_name="Ada"), load_template("default"))
    assert r"\section{Summary}" in tex and r"\section{Professional Experience}" in tex
    for title in ("Technical Skills", "Projects", "Certifications", "Education", "Volunteering"):
        assert f"section{{{title}" not in tex


def test_paper_size_comes_from_the_template_config() -> None:
    template = load_template("default")
    assert "letterpaper" in render_tex(CVDocument(), CVProfile(full_name="A"), template)
    template.config = {**template.config, "paper": "a4"}
    tex = render_tex(CVDocument(), CVProfile(full_name="A"), template)
    assert r"\documentclass[a4paper,10pt]" in tex and "letterpaper" not in tex


# ------------------------------------------------------------ one point → narrative paragraph


def _tex_with(roles: list[CVRole], template: str = "default") -> str:
    doc, profile = sample()
    doc = doc.model_copy(update={"roles": roles, "projects": []})
    return render_tex(doc, profile, load_template(template))


@pytest.mark.parametrize("template", ["default"])
def test_single_point_renders_as_a_paragraph_and_several_as_bullets(template: str) -> None:
    one = CVRole(title="Engineer", org="Acme", bullets=["Shipped the app to production."])
    many = CVRole(title="Dev", org="Beta", bullets=["Built A.", "Built B."])
    tex = _tex_with([one, many], template)
    body = tex.split(r"\begin{document}")[1]
    single, multi = body.split("Beta")[0], body.split("Beta")[1]
    assert r"\resumeParagraph{Shipped the app to production.}" in single
    assert r"\resumeItem{" not in single and r"\resumeItemListStart" not in single
    assert multi.count(r"\resumeItem{") == 2 and r"\resumeItemListStart" in multi
    assert r"\resumeParagraph{" not in multi


def test_paragraph_style_is_unindented_justified_and_tight() -> None:
    tex = _tex_with([CVRole(title="E", org="A", bullets=["One."])])
    macro = tex[tex.index(r"\newcommand{\resumeParagraph}"):].split("\n\n")[0]
    assert r"\parindent}{0pt}" in macro and r"\rightskip=0pt" in macro
    assert r"\linespread{1.2}" in macro and r"\vspace{2pt}" in macro
    assert r"\item" not in macro  # no bullet marker


@needs_latex
def test_paragraph_compiles(tmp_path: Path) -> None:
    tex = _tex_with([CVRole(title="E", org="A", bullets=["Delivered x. " * 20])])
    assert compile_tex(tex, tmp_path, "p").ok
