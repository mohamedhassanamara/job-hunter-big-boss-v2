"""The experience pool as the CV generator sees it: active items from the Experience screen,
addressed by their database ids, plus the candidate header from Settings → Candidate.

Everything factual on a CV comes from here: titles, companies, dates, locations, issuers and
credential ids are rendered straight from these rows; the model only picks, orders and rewords
bullets and the summary."""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlmodel import Session, col, select

from app.models import AppSetting, ExperienceItem
from app.services.cv_render import CVLink, CVProfile


def month(d: date | None) -> str:
    return d.strftime("%b %Y") if d else ""


def span(item: ExperienceItem) -> tuple[str, str]:
    """('Sep 2025', 'Present') · ('Feb 2025', 'Aug 2025') · ('', '') when undated."""
    start = month(item.start_date)
    end = month(item.end_date) if item.end_date else ("Present" if item.start_date else "")
    return start, end


@dataclass
class Pool:
    items: dict[int, ExperienceItem]
    profile: dict[str, Any]
    by_kind: dict[str, list[ExperienceItem]] = field(default_factory=dict)

    def of(self, kind: str) -> list[ExperienceItem]:
        return self.by_kind.get(kind, [])

    def get(self, item_id: int, kind: str | None = None) -> ExperienceItem | None:
        item = self.items.get(item_id)
        return item if item and (kind is None or item.kind == kind) else None

    def facts(self, item: ExperienceItem) -> list[str]:
        """Source statements of an item: bullets, or its summary when it has no bullets."""
        bullets = [b for b in item.bullets if b.strip()]
        return bullets or ([item.summary] if (item.summary or "").strip() else [])

    def all_text(self) -> str:
        parts = []
        for item in self.items.values():
            parts += [item.title, item.org or "", item.summary or "", *item.bullets, *item.tags]
        return "\n".join(p for p in parts if p)

    def vocabulary(self) -> set[str]:
        return {norm(t) for t in re.findall(r"[A-Za-z][A-Za-z0-9+#.\-/]*", self.all_text())}

    def skill_terms(self) -> set[str]:
        """Every skill the pool mentions: skill groups plus the tech tags of roles/projects."""
        return {norm(t) for item in self.items.values() for t in item.tags}


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9+#]", "", text.lower())


def load_pool(s: Session) -> Pool:
    items = s.exec(
        select(ExperienceItem).where(col(ExperienceItem.is_active))
        .order_by(col(ExperienceItem.position), col(ExperienceItem.id))
    ).all()
    row = s.exec(select(AppSetting).where(AppSetting.key == "profile")).first()
    pool = Pool(items={i.id: i for i in items if i.id is not None},
                profile=dict(row.value) if row else {})
    for item in items:
        pool.by_kind.setdefault(item.kind, []).append(item)
    # Roles newest first (the CV timeline order), whatever their position on the screen.
    for kind in ("job", "volunteering", "education"):
        pool.by_kind.get(kind, []).sort(
            key=lambda i: (i.end_date is not None, -(i.end_date or i.start_date or date.min)
                           .toordinal(), -(i.start_date or date.min).toordinal()))
    return pool


def role_years(pool: Pool, today: date | None = None) -> float:
    """Professional experience from role dates: the union of job intervals (overlaps merged),
    ongoing roles counted to today. Volunteering is not counted."""
    today = today or date.today()
    spans = sorted((i.start_date, i.end_date or today) for i in pool.of("job") if i.start_date)
    total, cur_start, cur_end = 0, None, None
    for start, end in spans:
        if cur_end is None or start > cur_end:
            if cur_end is not None:
                total += (cur_end - cur_start).days
            cur_start, cur_end = start, end
        else:
            cur_end = max(cur_end, end)
    if cur_end is not None:
        total += (cur_end - cur_start).days
    return total / 365.25


EXPERIENCE_STATEMENT = "{n} years of software engineering experience"


def years_facts(pool: Pool, tracks: list[dict[str, Any]],
                today: date | None = None) -> list[dict[str, Any]]:
    """The only years-of-experience claims a CV may make. With Settings → Candidate's total
    override set, ONE exact statement ("3 years of software engineering experience", wording
    editable there) and nothing per track. Otherwise the per-track years (Settings → Search
    profile) and the total from role dates, stated as "N+ years"."""
    override = pool.profile.get("total_years_override")
    if override not in (None, ""):
        n = int(float(override))
        wording = (pool.profile.get("experience_statement") or "").strip() or \
            EXPERIENCE_STATEMENT.format(n=n)
        fact = {"label": "total experience (Settings)", "years": n, "wording": wording,
                "kind": "total", "exact": True}
        from app.services.cv_claims import short_form

        if short := short_form(wording):
            fact["short_wording"] = short[0]
            fact["short_wording_when"] = f"the same sentence already says “{short[1]}”"
        return [fact] if n >= 1 else []
    facts = []
    for track in tracks:
        years = track.get("years_experience")
        if track.get("name") and years:
            n = int(float(years))
            if n >= 1:
                facts.append({"label": f"{track['name']} experience (Settings)", "years": n,
                              "wording": f"{n}+ year{'s' if n > 1 else ''}", "kind": "track"})
    total, source = int(role_years(pool, today)), "from role dates"
    if total >= 1:
        facts.append({"label": f"professional experience ({source})", "years": total,
                      "wording": f"{total}+ year{'s' if total > 1 else ''}", "kind": "total"})
    return facts


def cv_profile(pool: Pool) -> CVProfile:
    p = pool.profile
    return CVProfile(
        full_name=(p.get("full_name") or "").strip(),
        location=(p.get("based_in") or "").strip(),
        phone=(p.get("phone") or "").strip(),
        email=(p.get("email") or "").strip(),
        links=[CVLink(**{k: str(v or "") for k, v in link.items() if k in ("type", "label", "url")})
               for link in p.get("links") or [] if (link.get("url") or "").strip()],
    )


def readiness(pool: Pool) -> list[dict[str, str]]:
    """What a CV needs that the pool/profile lacks. severity 'blocker' stops generation."""
    out = []
    if not (pool.profile.get("full_name") or "").strip():
        out.append({"key": "full_name", "severity": "blocker",
                    "message": "Add your full name in Settings → Candidate (it heads the CV)."})
    if not pool.of("job"):
        out.append({"key": "roles", "severity": "blocker",
                    "message": "Add at least one role in Experience."})
    if not pool.of("education"):
        out.append({"key": "education", "severity": "warning", "message":
                    "No education in Experience: the CV will have no Education section."})
    if not any(i.tags for i in pool.of("skill")):
        out.append({"key": "skills", "severity": "warning", "message":
                    "No skill groups in Experience: the CV will have no Skills section."})
    if not pool.of("summary"):
        out.append({"key": "summary", "severity": "warning",
                    "message": "No summary snippet in Experience: the summary will be composed "
                               "from your roles and projects (no new facts)."})
    empty = [i.title for i in pool.of("job") if not pool.facts(i)]
    if empty:
        out.append({"key": "bullets", "severity": "warning",
                    "message": f"Roles without bullets or summary: {', '.join(empty)}."})
    contact = pool.profile
    if not any((contact.get(k) or "").strip() for k in ("email", "phone")):
        out.append({"key": "contact", "severity": "warning", "message":
                    "No email or phone in Settings → Candidate: recruiters can't reach you."})
    return out


def prompt_pool(pool: Pool) -> dict[str, Any]:
    """The pool as the model sees it: ids, facts with indexes, tags. No contact data."""
    def entry(i: ExperienceItem) -> dict[str, Any]:
        start, end = span(i)
        return {"id": i.id, "title": i.title, "org": i.org, "dates": f"{start} – {end}".strip(" –"),
                "facts": {str(n): f for n, f in enumerate(pool.facts(i))}, "tags": i.tags}

    return {
        "summary_snippets": [{"id": i.id, "text": i.summary or ""} for i in pool.of("summary")],
        "roles": [entry(i) for i in pool.of("job")],
        "projects": [entry(i) for i in pool.of("project")],
        "skill_groups": [{"id": i.id, "category": i.title, "skills": i.tags}
                         for i in pool.of("skill") if i.tags],
        "certifications": [{"id": i.id, "name": i.title, "issuer": i.org}
                           for i in pool.of("certification")],
        "education": [{"id": i.id, "degree": i.title, "school": i.org}
                      for i in pool.of("education")],
        "volunteering": [entry(i) for i in pool.of("volunteering")],
    }
