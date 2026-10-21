"""Honesty about years of experience (CVs, cover letters, form answers, emails, LinkedIn).

Each track in Settings → Search profile says whether your experience in it is professional or
project-based (`experience`: professional | projects, with a note such as "personal projects,
a graduation project, an internship and certifications"). Your years wording is professional
experience: it may never be attached to a project-based track.

Flagged (errors):
- a years claim attached to a project-based track's domain ("3 years of experience building
  data pipelines", "3 years in data", "over 2 years developing ETL"),
- a title or phrase implying professional experience in it: one of that track's role titles
  after "experienced", "as a", "I'm a", or opening a sentence with "with…", and
  "professional <domain> engineering experience".
Allowed: the years about the professional tracks, and the project-based work said as what it is
("software engineer (3 years, mobile and backend) moving into data, with dbt and Airflow
projects", "in my graduation project"). No model calls.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from sqlmodel import Session

from app.services.cv_check import violation

# Words that mark text about a domain, keyed by the words track names use ("Data/AI" → data, ai).
DOMAIN_WORDS: dict[str, list[str]] = {
    "data": ["data", "données", "pipeline", "pipelines", "etl", "elt", "lakehouse",
             "warehouse", "analytics", "big data", "dbt", "airflow", "spark", "kafka"],
    "ai": ["ai", "ia", "machine learning", "ml", "mlops", "llm", "llms", "deep learning", "nlp",
           "computer vision", "intelligence artificielle", "apprentissage automatique"],
    "analytics": ["analytics", "bi", "dashboards", "reporting"],
    "ml": ["machine learning", "ml", "mlops", "models"],
}
# Domain words that are concepts, not tools you can name as proof ("with ETL projects").
CONCEPTS = {"data", "données", "pipeline", "pipelines", "etl", "elt", "lakehouse", "warehouse",
            "analytics", "big data", "ai", "ia", "machine learning", "ml", "mlops", "llm", "llms",
            "deep learning", "deep-learning", "nlp", "computer vision", "computer-vision", "bi",
            "dashboards", "reporting", "models", "data-modeling", "data-engineering",
            "data-cleaning", "time-series", "intelligence artificielle"}
_NUM = (r"(?:\d+(?:[.,]\d+)?\+?|one|two|three|four|five|six|seven|eight|nine|ten|un|une|"
        r"deux|trois|quatre|cinq|six|sept|huit|neuf|dix)")
_YEARS = re.compile(r"(?:over|more than|plus de|près de|nearly|almost|about)?\s*\b" + _NUM
                    + r"\s*\+?\s*(?:years?|yrs|ans|années)\b", re.I)
# What makes data work honest to name next to years: it's said to be projects or a move.
_QUALIFIER = re.compile(r"\b(?:projects?|projets?|personal|personnel\w*|graduation|fin d.études|"
                        r"pfe|internship|intern|stage|stagiaire|certificat\w*|certif\w*|course\w*|"
                        r"moving into|move into|now (?:focused|focusing) (?:on|towards?)|"
                        r"transition\w*|switching|reconversion|vers la|vers "
                        r"l.|towards|learning|self-taught|side)\b", re.I)
_PROFESSIONAL_CLAIM = re.compile(r"\b(?:experienced|seasoned|senior|expert|professional|"
                                 r"confirmé\w*|expérimenté\w*)\b", re.I)


@dataclass
class Track:
    name: str
    terms: list[str]  # domain words
    titles: list[str]  # the track's role titles (lowercase)
    note: str  # how the experience was gained ("personal projects, …")


@dataclass
class Rules:
    projects: list[Track] = field(default_factory=list)  # project-based tracks
    professional: list[str] = field(default_factory=list)  # professional track names

    def __bool__(self) -> bool:
        return bool(self.projects)


def _domain_terms(name: str, titles: list[str]) -> list[str]:
    keys = {w for w in re.split(r"[^a-z]+", name.lower()) if w}
    for t in titles:
        keys |= {w for w in re.split(r"[^a-z]+", t.lower()) if w in DOMAIN_WORDS}
    terms = [x for k in sorted(keys) for x in DOMAIN_WORDS.get(k, [k])]
    return list(dict.fromkeys(terms))


def rules_from(tracks: list[dict[str, Any]]) -> Rules:
    out = Rules()
    for t in tracks or []:
        name = t.get("name") or ""
        if (t.get("experience") or "professional") == "projects":
            titles = [(r.get("title") or "").lower() for r in t.get("roles") or []
                      if r.get("title")]
            out.projects.append(Track(name, _domain_terms(name, titles), titles,
                                      t.get("experience_note") or "projects"))
        else:
            out.professional.append(name)
    return out


def rules(s: Session) -> Rules:
    from app.services.discovery import active_profile

    _, profile = active_profile(s)
    return rules_from(profile.tracks)


_DATABASES = re.compile(r"\bbases? de données\b|\bdatabases?\b", re.I)  # backend work, not data


def _has(text: str, term: str) -> re.Match[str] | None:
    """Whole word. Short terms (AI, IA, ML, BI) only in capitals, so "J'ai" isn't AI."""
    text = _DATABASES.sub(lambda m: " " * len(m.group(0)), text)  # offsets kept
    if len(term) <= 2:
        return re.search(rf"(?<![A-Za-zÀ-ÿ'’]){re.escape(term.upper())}(?![A-Za-zÀ-ÿ])", text)
    return re.search(rf"(?<![a-zà-ÿ'’]){re.escape(term)}(?![a-zà-ÿ])", text, re.I)


def _sentences(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", text or "") if x.strip()]


def about_projects(text: str, r: Rules) -> bool:
    """Whether a short label ("Data Engineering", "AI/ML") names a projects track's domain."""
    return any(_has(text, term) for t in r.projects for term in t.terms)


def professional_areas(areas: list[str], r: Rules) -> list[str]:
    """The areas the years may sit next to (the email's intro line): never a projects track's."""
    return [a for a in areas if not about_projects(a, r)]


def problems(text: str, r: Rules) -> list[tuple[str, str, str]]:
    """(kind, sentence, message) for every dishonest years or title claim in the text."""
    if not r:
        return []
    out: list[tuple[str, str, str]] = []
    for sentence in _sentences(text):
        for track in r.projects:
            years = _YEARS.search(sentence)
            if years:
                after = sentence[years.end():years.end() + 70]
                near = next((t for t in track.terms if _has(after, t)), None)
                anywhere = next((t for t in track.terms if _has(sentence, t)), None)
                # The qualifier may close the clause: "…data pipelines and LLM systems in
                # personal projects".
                if near and not _QUALIFIER.search(sentence[years.end():years.end() + 70 + 45]):
                    out.append(("years_domain", sentence,
                                f"“{years.group(0).strip()}” is attached to {track.name} work "
                                f"(“{near}”), which is {track.note}: keep the years about your "
                                "professional software engineering, and say the "
                                f"{track.name} work is projects"))
                    break
                if anywhere and not _QUALIFIER.search(sentence):
                    out.append(("years_domain", sentence,
                                f"Years and {track.name} work in one sentence without saying it's "
                                f"{track.note}: separate them, or say “in projects”"))
                    break
            title = next((t for t in track.titles if _has(sentence, t)), None)
            if title:
                m = _has(sentence, title)
                before = sentence[:m.start()]
                starts = not before.strip() or re.search(r"(?:^|[.:;]\s*)$", before)
                claims = re.search(r"\b(?:i am|i'm|as an?|as|je suis|en tant que|working as|"
                                   r"worked as|work as)\s+(?:an?\s+)?(?:\w+\s+)?$", before, re.I)
                if (claims or _PROFESSIONAL_CLAIM.search(before[-30:]) or
                        (starts and re.match(r"\s*(?:with|who|having|avec)\b",
                                             sentence[m.end():], re.I))) \
                        and not _QUALIFIER.search(sentence[max(0, m.start() - 40):m.end() + 40]):
                    out.append(("title_claim", sentence,
                                f"“{m.group(0)}” reads as professional {track.name} experience, "
                                f"which is {track.note}"))
                    break
            domain = "|".join(map(re.escape, track.terms))
            phrase = re.search(rf"\b(?:professional|experienced)\s+(?:{domain})(?:\s+\w+)?\s+"
                               r"(?:experience|engineering|background)\b", sentence, re.I)
            if phrase and not _QUALIFIER.search(sentence):
                out.append(("title_claim", sentence,
                            f"“{phrase.group(0)}” implies professional {track.name} experience, "
                            f"which is {track.note}"))
    return out


def violations(text: str, r: Rules | None, where: str = "body") -> list[dict[str, str]]:
    return [violation(kind, msg, where, "error") for kind, _s, msg in problems(text, r or Rules())]


def prompt_facts(r: Rules) -> dict[str, Any]:
    """What generation is told (FACTS.experience_by_track and the rule)."""
    return {"experience_by_track": [{"track": t.name, "experience": "projects", "how": t.note}
                                    for t in r.projects]
            + [{"track": n, "experience": "professional"} for n in r.professional],
            "years_rule": "The years wording is professional software engineering experience "
                          "(the professional tracks). Never attach it to a project-based track "
                          "(no 'N years of data…', no 'experienced data engineer'); describe "
                          "project-based work as what it is (personal projects, the graduation "
                          "project, the internship, certifications), in a separate sentence or "
                          "as a move ('moving into data, with … projects')."}
