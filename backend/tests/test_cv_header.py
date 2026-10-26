"""Refresh header: only the header text changes, in the CV's own style; sent CVs never; approved
stays approved; a result that overflows one page isn't saved. No model, no network."""

from datetime import UTC, datetime

from sqlmodel import Session

from app.db import engine
from app.models import CVVersion
from app.models.enums import CVStatus
from app.services import cv_header
from app.services.cv_pool import cv_profile, load_pool
from app.services.cv_render import CVDocument, load_template, render_tex
from tests.test_outreach import job_ready  # noqa: F401 (fixture)

OLD = r"""\begin{document}
\begin{center}
    \textbf{\Huge \scshape \textcolor{primaryColor}{Old Name}} \\ \vspace{4pt}
\faIcon{phone} +1 \\ \vspace{2pt}
\faIcon{linkedin} \href{https://l.example/a}{a} \hspace{1pt}$|$\hspace{1pt} \faIcon{globe} \href{https://old.example}{old}
\end{center}

\section{Summary}
Keep me \raggedbottom.
"""
NEW = OLD.replace("Old Name", "New Name") \
    .replace("https://old.example}{old}", "https://new.example}{new}") \
    .replace(r"\hspace{1pt}$|$\hspace{1pt}", r"\hspace{3pt}$\cdot$\hspace{3pt}")


def test_splice_changes_only_the_header_text_and_keeps_the_cvs_own_separators() -> None:
    out = cv_header.splice(OLD, NEW)
    assert "New Name" in out and "https://new.example" in out
    assert r"\hspace{1pt}$|$\hspace{1pt}" in out and r"$\cdot$" not in out  # the CV's own style
    assert out.endswith("Keep me \\raggedbottom.\n") and r"\section{Summary}" in out
    fewer = NEW.replace("\\faIcon{phone} +1 \\\\ \\vspace{2pt}\n", "")
    assert cv_header.splice(OLD, fewer) is None  # a different header structure: nothing guessed


def test_a_sent_cv_is_never_refreshed_and_an_unsent_approved_one_stays_approved(
        job_ready: dict) -> None:  # noqa: F811
    with Session(engine) as s:
        v = s.get(CVVersion, job_ready["cv"])
        pool = load_pool(s)
        doc = CVDocument.model_validate(v.content or {})
        v.content = doc.model_dump()
        v.tex = render_tex(doc, cv_profile(pool).model_copy(update={"links": []}),
                           load_template("default"))
        v.template = "default"
        v.status = CVStatus.approved
        s.add(v)
        s.commit()
    with Session(engine) as s:
        v = s.get(CVVersion, job_ready["cv"])
        v.locked_at = datetime.now(UTC)
        s.add(v)
        s.commit()
    result = cv_header.refresh(engine, job_ready["cv"])
    assert result["outcome"] == "skipped" and "Sent" in result["reason"]
    assert job_ready["cv"] not in [r["id"] for r in cv_header.refresh_all(engine)]
    with Session(engine) as s:
        v = s.get(CVVersion, job_ready["cv"])
        v.locked_at = None
        s.add(v)
        s.commit()
    again = cv_header.refresh(engine, job_ready["cv"])
    assert again["outcome"] != "refreshed" or again["pages_after"] == 1
    with Session(engine) as s:
        assert s.get(CVVersion, job_ready["cv"]).status == CVStatus.approved
