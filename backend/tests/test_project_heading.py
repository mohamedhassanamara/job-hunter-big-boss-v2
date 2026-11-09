"""The project heading in the templates: a long tech stack wraps instead of running off the page,
a short one renders exactly as before, and the label always has a gap. Real LaTeX runs."""
import shutil
import tempfile
from pathlib import Path

import pymupdf
import pytest

from app.services.cv_render import (
    CVDocument,
    CVProfile,
    CVProject,
    CVTemplate,
    compile_tex,
    load_template,
    render_tex,
)
from tests.test_skill_fit import HAS_SANS, sans_template

pytestmark = pytest.mark.skipif(shutil.which("latexmk") is None, reason="LaTeX not installed")

MARGIN = 0.55 * 72  # the templates' geometry margin (points)
NAME = "Job Hunter: AI-Powered Job Aggregation & Application Platform"
LONG = ["Python", "FastAPI", "SQLModel", "React", "TypeScript", "Ollama", "Claude/Gemini APIs"]
SHORT = ["Python", "dbt", "Airflow"]
OLD_MACRO = r"""\newcommand{\resumeProjectHeading}[2]{
  \item
    \begin{tabular*}{\textwidth}{l@{\extracolsep{\fill}}r}
      #1 & #2 \\
    \end{tabular*}
}"""


def old_style(template: CVTemplate, tmp_path: Path) -> CVTemplate:
    """The same template with the previous `l`-column heading (to compare against)."""
    path = tmp_path / f"old-{template.name}"
    shutil.copytree(template.path, path)
    text = (template.path / "cv.tex.j2").read_text()
    start = text.index("% The heading wraps when the stack is long")
    end = text.index("\n}\n", text.index("\\newcommand{\\resumeProjectHeading}")) + 3
    (path / "cv.tex.j2").write_text(text[:start] + OLD_MACRO + "\n" + text[end:])
    return CVTemplate(name=f"old-{template.name}", path=path, config=template.config,
                      builtin=False)


def templates(tmp_path: Path) -> dict[str, CVTemplate]:
    out = {"default": load_template("default")}
    if HAS_SANS:
        out["sans"] = sans_template(tmp_path)
    return out


def build(template: CVTemplate, stack: list[str], label: str = "Personal project",
          name: str = NAME) -> tuple[list, list, float]:
    """(lines, spans, page width): each as ((x0, y0, x1, y1), text), sorted."""
    doc = CVDocument(projects=[CVProject(name=name, stack=stack, label=label,
                                         bullets=["Built it."])])
    tex = render_tex(doc, CVProfile(full_name="Ada Lovelace"), template)
    result = compile_tex(tex, Path(tempfile.mkdtemp()), "cv")
    assert result.ok, result.error
    with pymupdf.open(result.pdf_path) as pdf:
        page = pdf[0]
        lines, spans = [], []
        for block in page.get_text("dict")["blocks"]:
            for ln in block.get("lines", []):
                lines.append((tuple(round(v, 1) for v in ln["bbox"]),
                              "".join(sp["text"] for sp in ln["spans"]).strip()))
                spans += [(tuple(round(v, 1) for v in sp["bbox"]), sp["text"].strip())
                          for sp in ln["spans"] if sp["text"].strip()]
        return sorted(r for r in lines if r[1]), sorted(spans), page.rect.width


def header_rows(rows: list) -> list:
    """The lines of the project heading: below the section title, above the first bullet."""
    top = next(r[0][3] for r in rows if r[1].upper() == "PROJECTS")
    bottom = next(r[0][1] for r in rows if r[1] == "Built it.")
    return [r for r in rows if top <= r[0][1] < bottom]


def test_the_old_heading_really_overflowed_with_a_long_stack(tmp_path: Path) -> None:
    template = old_style(load_template("default"), tmp_path)
    rows, _spans, width = build(template, LONG)
    assert max(r[0][2] for r in header_rows(rows)) > width - MARGIN + 1  # the defect


@pytest.mark.parametrize("which", ["default", "sans"])
def test_a_long_stack_wraps_and_stays_inside_the_margin(which: str, tmp_path: Path) -> None:
    if which not in (tpl := templates(tmp_path)):
        pytest.skip("Source Sans Pro is not installed")
    rows, _spans, width = build(tpl[which], LONG)
    header = header_rows(rows)
    assert max(r[0][2] for r in rows) <= width - MARGIN + 1  # nothing leaves the right margin
    assert min(r[0][0] for r in header) >= MARGIN - 1
    assert len({round(r[0][1]) for r in header}) >= 2  # it wrapped onto a second line
    assert any(r[1].endswith("Personal project") or r[1] == "Personal project" for r in header)


@pytest.mark.parametrize("which", ["default", "sans"])
def test_a_short_stack_renders_exactly_as_before(which: str, tmp_path: Path) -> None:
    if which not in (tpl := templates(tmp_path)):
        pytest.skip("Source Sans Pro is not installed")
    new_rows, new_spans, _ = build(tpl[which], SHORT, name="FPL Batch Data Lakehouse")
    old_rows, old_spans, _ = build(old_style(tpl[which], tmp_path), SHORT,
                                   name="FPL Batch Data Lakehouse")
    assert len(new_rows) == len(old_rows)
    for (nb, nt), (ob, ot) in zip(new_rows + new_spans, old_rows + old_spans, strict=True):
        assert nt == ot
        assert all(abs(a - b) <= 0.6 for a, b in zip(nb, ob, strict=True)), (nt, nb, ob)


@pytest.mark.parametrize("which", ["default", "sans"])
@pytest.mark.parametrize("stack", [[], SHORT[:1], SHORT, LONG[:5], LONG, LONG * 2])
def test_the_label_always_has_a_gap(which: str, stack: list[str], tmp_path: Path) -> None:
    if which not in (tpl := templates(tmp_path)):
        pytest.skip("Source Sans Pro is not installed")
    _rows, spans, width = build(tpl[which], stack)
    # the label may come out as one span or as one per word, depending on the font
    words = [s for s in spans if s[1] in ("Personal", "project", "Personal project")]
    assert words
    label_x0, label_x1 = min(s[0][0] for s in words), max(s[0][2] for s in words)
    label_y = words[0][0][1]
    same_line = [s for s in spans if s not in words and abs(s[0][1] - label_y) < 3
                 and s[0][2] <= label_x0 + 0.5]
    assert same_line  # the heading text shares the label's first line
    gap = label_x0 - max(s[0][2] for s in same_line)
    assert gap >= 9.5  # 1em at 10pt: the text and the label never touch
    assert label_x1 <= width - MARGIN + 1  # the label stays inside the margin


def test_a_label_wider_than_the_stack_still_fits() -> None:
    rows, _spans, width = build(load_template("default"), SHORT,
                                label="A rather long label for a project")
    assert max(r[0][2] for r in rows) <= width - MARGIN + 1
