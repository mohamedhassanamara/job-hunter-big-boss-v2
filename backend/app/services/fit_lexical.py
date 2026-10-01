"""The lexical evidence check behind "fit before/after" (no model, no network).

Adapted from jobhunt-fit in github.com/mohamedaminehamdi/job-hunter
(MIT License; the copyright notice is in docs/CREDITS.md). Re-written for this
app's data model (the experience pool and the CV document); no code is imported from it.

The idea: take the listing's lines that name something checkable (tools, methods, credentials),
look each term up in your experience, and report
- evidenced: lines your experience backs (tailoring can't change this number),
- shown: of those, lines visible on the CV's first screen (summary, skills, role titles, first
  ten bullets) — before (your master experience) and after (the tailored CV),
- present: lines backed anywhere in the CV,
- dropped: terms your experience backs that the CV left out,
- unbacked: terms the CV names that your experience doesn't back,
- a years note: years asked vs years held.
Lines with only soft skills ("communication", "proactive") aren't checkable: they leave the count.
"""

import re
from typing import Any

from app.services.cv_pool import Pool


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


_STOP = _words("""
a an the and or of to in on at for with by from as is are be will you your our we our their
this that these those it its into over per via etc e.g i.e we're you'll who what how le la
les un une des du de et ou en au aux pour par avec sur dans est sont nous vous votre nos der
die das und oder mit für von zu im ist sind wir sie ihr""")
_FILLER = _words("""
experience experienced strong solid good great excellent proven deep hands-on knowledge
understanding ability able skills skill years year plus nice bonus preferred required
requirements responsibilities team teams work working environment role position candidate
opportunity company business customers clients product products mission expérience
connaissance connaissances maîtrise compétences équipe poste profil années ans erfahrung
kenntnisse jahre""")
_SOFT = _words("""
communication communicative proactive passionate motivated autonomous autonomy rigorous
curious curiosity collaborative teamwork organized organised flexible adaptable creative
ownership mindset attitude dynamic enthusiastic reliable autonome rigoureux rigoureuse
curieux curieuse motivé motivée dynamique passionné passionnée selbstständig teamfähig""")
_WORD = re.compile(r"[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9+#./-]*[A-Za-zÀ-ÿ0-9+#]|[A-Za-zÀ-ÿ0-9]")
_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:years?|yrs|ans|années|jahre)", re.I)
STRENGTH = ["demonstrated", "credentialed", "claimed", "asserted"]


def _norm(w: str) -> str:
    return w.lower().strip(".,;:()")


# A line that states a requirement: there, a capitalised word mid-sentence is a tool or method
# (Kubernetes, Rust). Elsewhere (the company pitch, perks) it's usually not.
_CUE = re.compile(r"\b(?:experience|experienced|know|knowledge|proficien\w*|familiar\w*|skills?|"
                  r"expertise|stack|tools?|technolog\w*|using|with|must|required|preferred|"
                  r"nice to have|bonus|plus|maîtris\w*|connaissances?|expérience|compétences?|"
                  r"outils|requis|souhaité\w*|apprécié\w*|idéalement|kenntnisse|erfahrung)\b",
                  re.I)


def _looks_technical(w: str, first: bool, cue: bool) -> bool:
    """A name: digits or +#/. (C++, S3, Node.js), ALL CAPS (SQL, AWS), an inner capital
    (PostgreSQL), or, on a requirement line, capitalised mid-sentence (Kubernetes, Rust).
    Places, the company and the job title are filtered out separately (`ignored`)."""
    if any(c.isdigit() for c in w) or any(c in w for c in "+#/."):
        return True
    if len(w) >= 2 and w.isupper():
        return True
    return any(c.isupper() for c in w[1:]) or (cue and w[0].isupper() and not first)


def _singular(n: str) -> str:
    return n[:-1] if len(n) > 3 and n.endswith("s") and not n.endswith("ss") else n


def salient_terms(line: str, vocabulary: set[str], ignore: set[str] | None = None) -> list[str]:
    """The checkable terms of one line: tool-like names or words in your own skills vocabulary;
    never stopwords, filler, soft skills, the company's own name, the job title or places."""
    out: list[str] = []
    ignore = ignore or set()
    cue = bool(_CUE.search(line))
    for i, w in enumerate(_WORD.findall(line)):
        n = _norm(w)
        if not n or n in _STOP or n in _FILLER or n in _SOFT or n.isdigit() or n in ignore \
                or _singular(n) in ignore:
            continue
        if n in vocabulary or _singular(n) in vocabulary or _looks_technical(w, i == 0, cue):
            term = n if n in vocabulary else _singular(n) if _singular(n) in vocabulary else n
            if term not in out:
                out.append(term)
    return out


def requirement_lines(description: str) -> list[str]:
    parts = re.split(r"\n+|(?<=[.;])\s+(?=[A-ZÀ-Ý•\-])|\s+[•·]\s+", description or "")
    return [p.strip(" •-*\t") for p in parts if len(p.split()) >= 3][:60]


def _has(text: str, term: str) -> bool:
    """Whole word, case-insensitive; a plural matches its singular (LLMs ~ LLM)."""
    stem = _singular(term)
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(stem)}s?(?![A-Za-z0-9])", text, re.I) \
        is not None


def _profile_places(pool: Pool) -> list[tuple[str, str, str]]:
    """(where, strength, text) across your experience, strongest first."""
    out: list[tuple[str, str, str]] = []
    for item in [*pool.of("job"), *pool.of("project"), *pool.of("volunteering")]:
        for n, b in enumerate(item.bullets or []):
            out.append((f"{item.title} · {item.org or ''} · bullet {n + 1}".strip(),
                        "demonstrated", b))
    for item in [*pool.of("education"), *pool.of("certification")]:
        out.append((f"{item.title} · {item.org or ''}", "credentialed",
                    f"{item.title} {item.org or ''} {' '.join(item.bullets or [])}"))
    for item in [*pool.of("skill"), *pool.of("job"), *pool.of("project")]:
        if item.tags:
            out.append((f"{item.title} (skills)", "claimed", " ".join(item.tags)))
    for item in pool.of("summary"):
        out.append(("summary", "asserted", item.summary or ""))
    return out


def vocabulary(pool: Pool) -> set[str]:
    return {_norm(t) for i in pool.items.values() for t in (i.tags or [])}


def evidence(term: str, places: list[tuple[str, str, str]]) -> dict[str, str] | None:
    for where, strength, text in places:
        if _has(text, term):
            m = re.search(rf".{{0,60}}{re.escape(term)}.{{0,60}}", text, re.I | re.S)
            return {"term": term, "where": where, "strength": strength,
                    "quote": (m.group(0) if m else text[:120]).strip()}
    return None


def pool_skim(pool: Pool) -> str:
    """Your master experience's first screen: a summary snippet, skills, role titles and the
    first ten bullets in order."""
    bullets = [b for i in pool.of("job") for b in (i.bullets or [])][:10]
    summary = next((i.summary for i in pool.of("summary") if i.summary), "")
    skills = " ".join(t for i in pool.of("skill") for t in (i.tags or []))
    titles = " ".join(i.title for i in pool.of("job"))
    return "\n".join([summary, skills, titles, *bullets])


def cv_text(content: dict[str, Any]) -> tuple[str, str]:
    """(first screen, everything) of a tailored CV document."""
    roles = content.get("roles") or []
    bullets = [b for r in roles for b in (r.get("bullets") or [])]
    skills = " ".join(x for g in content.get("skills") or [] for x in (g.get("items") or []))
    titles = " ".join(f"{r.get('title', '')} {r.get('org', '')}" for r in roles)
    skim = "\n".join([content.get("summary") or "", skills, titles, *bullets[:10]])
    rest = []
    for key in ("projects", "education", "certifications", "volunteering"):
        for x in content.get(key) or []:
            if isinstance(x, dict):
                rest.append(" ".join(str(v) for v in x.values() if isinstance(v, str)))
                rest += [b for b in x.get("bullets") or [] if isinstance(b, str)]
    return skim, "\n".join([skim, *bullets[10:], *rest])


def years_note(description: str, held: int | None) -> str | None:
    asked = [int(m.group(1)) for m in _YEARS.finditer(description or "") if int(m.group(1)) <= 20]
    if not asked:
        return None
    most = max(asked)
    if held is None:
        return f"The listing asks for {most}+ years"
    return (f"The listing asks for {most}+ years; you have {held}" if held < most
            else f"The listing asks for {most}+ years; you have {held}: covered")


def ignored(company: str, title: str, location: str) -> set[str]:
    """Words that are about the listing itself, not a requirement: the company, the job title
    and place names (cities, countries)."""
    from app.services.geo import CITIES, COUNTRY_ALIASES

    words = {_norm(w) for w in _WORD.findall(f"{company} {title} {location}")}
    for aliases in COUNTRY_ALIASES.values():
        words |= {_norm(w) for a in aliases for w in a.split()}
    for cities in CITIES.values():
        words |= {_norm(w) for c in cities for w in str(c).split()}
    words |= {"europe", "eu", "emea", "mena", "gulf", "worldwide", "remote"}
    return {w for w in words if len(w) > 1}


def compare(pool: Pool, description: str, content: dict[str, Any] | None,
            years_held: int | None = None, *, company: str = "", title: str = "",
            location: str = "") -> dict[str, Any]:
    """Before (your master experience) vs after (the tailored CV) on one listing."""
    vocab = vocabulary(pool)
    skip = ignored(company, title, location)
    places = _profile_places(pool)
    profile_text = "\n".join(t for _, _, t in places)
    before_skim = pool_skim(pool)
    after_skim, after_all = cv_text(content or {})
    lines = []
    for line in requirement_lines(description):
        terms = salient_terms(line, vocab, skip)
        if not terms:
            continue  # nothing checkable (soft skills only)
        backed = [e for t in terms if (e := evidence(t, places))]
        lines.append({"line": line[:200], "terms": terms, "evidence": backed})
    checkable = len(lines)
    evidenced = [x for x in lines if x["evidence"]]

    def shown(text: str) -> int:
        return sum(any(_has(text, e["term"]) for e in x["evidence"]) for x in evidenced)

    backed_terms = sorted({e["term"] for x in evidenced for e in x["evidence"]})
    all_terms = sorted({t for x in lines for t in x["terms"]})
    dropped = [t for t in backed_terms if not _has(after_all, t)] if content else []
    unbacked = [t for t in all_terms if t not in backed_terms and _has(after_all, t)
                and not _has(profile_text, t)] if content else []
    return {
        "checkable": checkable,
        "evidenced": len(evidenced),
        "shown_before": shown(before_skim),
        "shown_after": shown(after_skim) if content else None,
        "present_after": shown(after_all) if content else None,
        "dropped": dropped[:12],
        "unbacked": unbacked[:12],
        "gaps": sorted({t for x in lines if not x["evidence"] for t in x["terms"]})[:12],
        "years": years_note(description, years_held),
        "lines": lines[:40],
    }
