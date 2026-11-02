"""A user template copied from the default before the paragraph fix still has the old
\\resumeParagraph (\\par + \\vspace + \\linespread): it is flagged, never blocked."""

from pathlib import Path

import pytest

from app.services import cv_render, cv_service, cv_templates
from app.services.cv_render import ROOT, CompileResult

OLD_MACRO = r"""
% A role/project with ONE point reads as a justified narrative paragraph: no bullet, no indent.
\newcommand{\resumeParagraph}[1]{%
  \par\vspace{2pt}%
  {\small\linespread{1.2}\selectfont\setlength{\parindent}{0pt}\rightskip=0pt\relax
   \noindent #1\par}%
  \vspace{2pt}%
}

\newcommand{\resumeSubheading}[4]{ \item #1 }
"""


def test_the_old_macro_is_flagged_and_the_fixed_one_is_not() -> None:
    assert cv_templates.template_warnings(OLD_MACRO) == [cv_templates.STALE_PARAGRAPH_MESSAGE]
    fixed = (ROOT / "templates/default/cv.tex.j2").read_text()
    assert cv_templates.template_warnings(fixed) == []
    assert cv_templates.template_warnings(r"\newcommand{\resumeItem}[1]{\item #1}") == []


@pytest.mark.parametrize("bad", [r"\par\ #1", r"\vspace{2pt}#1", r"\linespread{1.2}#1"])
def test_each_old_ingredient_alone_is_flagged(bad: str) -> None:
    source = "\\newcommand{\\resumeParagraph}[1]{" + bad + "}\n\n\\newcommand{\\x}{\\par}"
    assert cv_templates.template_warnings(source)  # the later macro's \par does not count
    ok = "\\newcommand{\\resumeParagraph}[1]{\\item #1\\parindent}\n\n\\newcommand{\\x}{\\par}"
    assert cv_templates.template_warnings(ok) == []  # \parindent is not \par


def test_a_stale_user_template_still_validates_but_carries_the_warning(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    user = tmp_path / "templates"
    (user / "old").mkdir(parents=True)
    default = ROOT / "templates/default"
    (user / "old/cv.config.yaml").write_text((default / "cv.config.yaml").read_text())
    fixed = [line for line in (default / "cv.tex.j2").read_text().split("\n")
             if not line.startswith(r"\newcommand{\resumeParagraph}")]
    stale = "\n".join(fixed).replace("\\begin{document}", OLD_MACRO + "\n\\begin{document}", 1)
    assert OLD_MACRO in stale
    (user / "old/cv.tex.j2").write_text(stale)
    monkeypatch.setattr(cv_render, "USER_TEMPLATES", user)
    monkeypatch.setattr(cv_templates, "USER_TEMPLATES", user)
    monkeypatch.setattr(cv_templates, "VALIDATION_FILE", user / ".validation.json")
    monkeypatch.setattr(cv_templates, "PREVIEW_DIR", user / ".previews")
    one_page = CompileResult(True, tmp_path / "x.pdf", 1, 0.9)
    monkeypatch.setattr(cv_templates, "compile_tex", lambda *_a, **_k: one_page)
    first = cv_templates.validate("old")
    assert first.valid and first.warnings == [cv_templates.STALE_PARAGRAPH_MESSAGE]
    again = cv_templates.validate("old")  # served from the cache: still warned
    assert again.valid and again.warnings == first.warnings
    assert cv_templates.validate("default").warnings == []
    with caplog.at_level("WARNING"):
        monkeypatch.setattr(cv_service, "cv_settings", lambda s: {"default_template": "old"})
        assert cv_service._template(None, None) == "old"  # type: ignore[arg-type]
    assert "out of date" in caplog.text
