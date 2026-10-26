"""Refresh a CV's header from the current Candidate profile and links, nothing else.

The header (name, contact line, links) is drawn from Settings → Candidate when a CV is rendered,
so a CV rendered before you changed a link keeps the old one. `refresh` renders today's header and
puts only its text into the CV's own stored LaTeX (the name and the items of the contact and link
lines, with that CV's own separators and spacing): bullets, skills, summary and layout, even from
an older template, stay exactly as they are. The PDF is recompiled locally: no model call.

It applies to every draft and every approved CV that was never sent; a locked (sent) CV is never
touched. Status stays as it was. A result that no longer fits one page is not saved (the old
render stays) and is reported.
"""

import difflib
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.models import Application, Company, CVVersion, Job
from app.models.enums import CVStatus
from app.services.cv_pool import cv_profile, load_pool
from app.services.cv_render import CVDocument, compile_tex, load_template, render_tex

ELIGIBLE = (CVStatus.draft, CVStatus.approved)


class HeaderError(ValueError):
    pass


def eligible(s: Session) -> list[CVVersion]:
    """Drafts and approved CVs that were never sent (not locked), oldest first."""
    return list(s.exec(select(CVVersion).where(
        col(CVVersion.status).in_(ELIGIBLE), col(CVVersion.locked_at).is_(None))
        .order_by(col(CVVersion.id))).all())


_SEP = re.compile(r"\s*\\hspace\{[^}]*\}\$[^$]*\$\\hspace\{[^}]*\}\s*")
_TAIL = re.compile(r"(\s*\\\\\s*\\vspace\{[^}]*\}\s*)$")
_NAME = re.compile(r"(\\textcolor\{primaryColor\}\{)([^}]*)(\})")


def _header(tex: str) -> tuple[int, int]:
    start = tex.index("\\begin{document}")
    return start, tex.index("\\section", start)


def splice(old: str, new: str) -> str | None:
    """`old` with only the header text of `new`; None when the two headers aren't built the
    same way (different number of contact lines), so nothing is guessed."""
    try:
        (os_, oe), (ns, ne) = _header(old), _header(new)
    except ValueError:
        return None
    ol, nl = old[os_:oe].split("\n"), new[ns:ne].split("\n")
    oi = [i for i, x in enumerate(ol) if "\\faIcon" in x]
    ni = [i for i, x in enumerate(nl) if "\\faIcon" in x]
    if not oi or len(oi) != len(ni):
        return None
    sep = next((m.group(0) for x in ol[oi[0]:] if (m := _SEP.search(x))), " ")
    for i, j in zip(oi, ni, strict=True):
        tail = _TAIL.search(ol[i])
        head_old = ol[i][:tail.start()] if tail else ol[i]
        own = _SEP.search(head_old)
        new_body = nl[j][:m.start()] if (m := _TAIL.search(nl[j])) else nl[j]
        ol[i] = (own.group(0) if own else sep).join(_SEP.split(new_body)) \
            + (tail.group(1) if tail else "")
    name = _NAME.search(new[ns:ne])
    head = "\n".join(ol)
    if name:
        head = _NAME.sub(lambda m: m.group(1) + name.group(2) + m.group(3), head, count=1)
    return old[:os_] + head + old[oe:]


def _fresh_tex(v: CVVersion, pool: Any) -> str | None:
    """The CV's stored LaTeX with today's header, or None when it can't be done safely."""
    if not v.content or not v.tex:
        return None
    profile = cv_profile(pool)
    if not profile.full_name:
        return None
    new = render_tex(CVDocument.model_validate(v.content), profile,
                     load_template(v.template or "default"))
    return splice(v.tex, new)


def _changed_lines(old: str, new: str) -> list[str]:
    return [x[1:].strip() for x in difflib.unified_diff(old.splitlines(), new.splitlines(),
                                                        n=0, lineterm="")
            if x[:1] in "+-" and x[:3] not in ("+++", "---")]


def preview(s: Session) -> list[dict[str, Any]]:
    """The CVs a refresh would change, with the lines that differ (so a layout change that
    isn't the header is visible before anything is written)."""
    pool = load_pool(s)
    out = []
    for v in eligible(s):
        new = _fresh_tex(v, pool)
        if new is None or new == v.tex:
            continue
        app = s.get(Application, v.application_id)
        job = s.get(Job, app.job_id) if app else None
        company = s.get(Company, job.company_id) if job else None
        diff = _changed_lines(v.tex or "", new)
        out.append({"id": v.id, "application_id": v.application_id, "version": v.version,
                    "status": str(v.status), "company": company.name if company else "",
                    "title": job.title if job else "", "pages": v.page_count, "fill": v.fill,
                    "changed_lines": len(diff), "diff": diff[:12]})
    return out


def refresh(engine: Engine, cv_id: int, *, dry_run: bool = False) -> dict[str, Any]:
    """Re-render one CV's header. Returns what happened (never raises for a skip). `dry_run`
    compiles in a temp folder and reports the page fit without saving anything."""
    with Session(engine) as s:
        v = s.get(CVVersion, cv_id)
        if v is None:
            raise HeaderError("CV version not found")
        result: dict[str, Any] = {"id": v.id, "application_id": v.application_id,
                                  "version": v.version, "status": str(v.status),
                                  "pages_before": v.page_count, "fill_before": v.fill}
        if v.locked_at is not None:
            return {**result, "outcome": "skipped", "reason": "Sent: a sent CV is never changed"}
        if v.status not in ELIGIBLE:
            return {**result, "outcome": "skipped", "reason": f"A {v.status} CV isn't refreshed"}
        new = _fresh_tex(v, load_pool(s))
        if new is None:
            return {**result, "outcome": "skipped",
                    "reason": "No stored document, no name in Settings → Candidate, or a header "
                              "built differently from today's template"}
        if new == v.tex:
            return {**result, "outcome": "unchanged", "pages_after": v.page_count,
                    "fill_after": v.fill}
        with tempfile.TemporaryDirectory(prefix="jh-hdr-") as tmp:
            compiled = compile_tex(new, Path(tmp))
            if not compiled.ok or compiled.pdf_path is None:
                return {**result, "outcome": "failed", "reason": compiled.error or "LaTeX failed"}
            if compiled.pages != 1:
                return {**result, "outcome": "not_saved", "pages_after": compiled.pages,
                        "reason": f"The new header makes it {compiled.pages} pages: the old "
                                  "render stays"}
            if dry_run:
                return {**result, "outcome": "would_refresh", "pages_after": 1,
                        "fill_after": round(compiled.fill, 3)}
            target = Path(v.pdf_path) if v.pdf_path else None
            if target is None:
                from app.services.cv_service import CV_DIR

                target = CV_DIR / str(v.application_id) / f"v{v.version}" / "cv.pdf"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(compiled.pdf_path, target)
            tex_copy = Path(tmp) / "cv.tex"
            if tex_copy.exists():
                shutil.copyfile(tex_copy, target.with_suffix(".tex"))
        v.tex, v.pdf_path, v.page_count = new, str(target), 1
        v.fill = round(compiled.fill, 3)
        s.add(v)  # status, content, plan and overrides stay exactly as they were
        s.commit()
        return {**result, "outcome": "refreshed", "pages_after": 1, "fill_after": v.fill}


def refresh_all(engine: Engine, ids: list[int] | None = None, *,
                dry_run: bool = False) -> list[dict[str, Any]]:
    """Refresh every changed eligible CV (or just `ids`); one failing CV never stops the rest."""
    with Session(engine) as s:
        todo = [row["id"] for row in preview(s) if ids is None or row["id"] in ids]
    return [refresh(engine, i, dry_run=dry_run) for i in todo]
