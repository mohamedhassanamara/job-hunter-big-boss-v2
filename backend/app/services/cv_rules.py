"""How a tailored CV is shaped, beyond relevance: the writing guide given to the model, bullet
allowances by role type (recency and duration), skill-section shaping, and the summary checks.
Everything is configurable in Settings → CV; the defaults below are the fallbacks.
"""

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.models import ExperienceItem

DEFAULT_GUIDE = "\n".join([
    "Summary: two full sentences with a subject (never a fragment like \"Brings…\"), no \"I\", "
    "about 45 words. Sentence 1: who I am, positioned for this job's track; for Data/AI jobs lead "
    "with what I build (e.g. \"Software engineer building data pipelines and local LLM "
    "systems\"). Sentence 2: what I bring to THIS role, naming at least one concrete thing I "
    "built from the cited items (e.g. \"a privacy-first resume parser on a local Mistral LLM\", "
    "\"a dbt/Airflow lakehouse for football data\"). Give sentence 2 a subject without \"I\" "
    "(e.g. \"Recent work includes…\", \"Projects include…\", \"That work spans…\"), never a bare "
    "verb like \"Built…\" or \"Delivered…\". Vary the opening between CVs. No numbers "
    "that also appear in bullets, no certifications, no internships, no tool lists.",
    "Bullets: impact first (what I built and why it mattered), strong and varied verbs, one idea "
    "per bullet. Prefer bullets with concrete outcomes; skip generic ones (\"collaborated in Agile "
    "sprints\") unless nothing else fits.",
    "Don't repeat the same fact in the summary, the skills and the bullets.",
    "Human tone: natural phrasing, no keyword stuffing; not every bullet needs a metric.",
    "Use the style exemplar for tone, bullet length and summary length (its content is already "
    "in the pool).",
])

# Phrases that make a CV read as generated (editable in Settings → CV, like the email list).
DEFAULT_CV_BANNED = [
    "hands-on experience", "well suited", "strong foundation", "real-world applications",
    "production-ready", "brings experience", "passionate", "proven track record", "leveraging",
]

DEFAULT_STRUCTURE: dict[str, Any] = {
    "current": [3, 4],        # the role you're in now
    "long_role": [2, 3],      # roles longer than long_role_months
    "long_role_months": 12,
    "short_role": [1, 3],     # shorter roles: 1-3 depending on relevance to the track
    "graduation": [1, 3],     # graduation / end-of-studies projects
    "internship": [1, 2],     # never more than 2
    "projects_max": 2,
    "project_bullets": [2, 3],  # never a 1-bullet project
    "volunteering_max": 1,
    "skill_groups_max": 4,
    "skill_items_max": 8,
    "fill_min": 0.88,         # never add filler beyond the allowances to reach it
    "summary_max_words": 45,
    "summary_max_sentences": 2,
}

# One rule per line. "Parent: A, B" = a generic term and its specific tools → "Parent (A, B)"
# (the generic term alone is dropped when a tool is present). "A + B" = a tool and what it
# emulates → "A (B)" when both are present. "A / B" → "A/B" when both are present.
DEFAULT_SKILL_MERGES = [
    "LLMs: Mistral, Ollama, OpenAI, Llama, GPT, Claude, Gemini",
    "LocalStack + S3",
    "Linux / Bash",
    "Docker + Docker Compose",
]
GENERIC_ALIASES = {"llms": {"llm", "llms", "large language models", "large language model"}}

_INTERN = re.compile(r"\b(intern|internship|stage|stagiaire|praktikum|praktikant|prácticas|"
                     r"practicas|tirocinio|tirocinante|apprenti|apprentice|alternance|trainee)\b",
                     re.I)
_GRADUATION = re.compile(r"(graduation|end[- ]of[- ]studies|capstone|thesis|final[- ]year|"
                         r"\bpfe\b|projet de fin|master'?s project|m[ée]moire)", re.I)
_GENERIC_BULLET = re.compile(r"\b(agile|scrum|sprints?|collaborat\w*|stakeholders?|team ?work|"
                             r"cross-functional|daily stand-?ups?|code reviews?)\b", re.I)


def structure(cv_settings: dict[str, Any]) -> dict[str, Any]:
    return {**DEFAULT_STRUCTURE, **(cv_settings.get("structure") or {})}


def guide(cv_settings: dict[str, Any]) -> str:
    return (cv_settings.get("writing_guide") or "").strip() or DEFAULT_GUIDE


def banned(cv_settings: dict[str, Any]) -> list[str]:
    rules = cv_settings.get("banned_phrases")
    return DEFAULT_CV_BANNED if rules is None else list(rules)


def merges(cv_settings: dict[str, Any]) -> list[str]:
    rules = cv_settings.get("skill_merges")
    return DEFAULT_SKILL_MERGES if rules is None else list(rules)


# ---------------------------------------------------------------------------- role types


def months(item: ExperienceItem, today: date | None = None) -> int:
    if not item.start_date:
        return 0
    end = item.end_date or today or date.today()
    return max(0, (end.year - item.start_date.year) * 12 + end.month - item.start_date.month + 1)


def role_type(item: ExperienceItem, rules: dict[str, Any], today: date | None = None) -> str:
    """current | internship | graduation | long_role | short_role."""
    text = f"{item.title} {item.org or ''}"
    if _INTERN.search(text):
        return "internship"
    if _GRADUATION.search(text):
        return "graduation"
    today = today or date.today()
    if item.start_date and (item.end_date is None or item.end_date >= today):
        return "current"
    return "long_role" if months(item, today) > int(rules["long_role_months"]) else "short_role"


def allowance(kind: str, item: ExperienceItem | None, relevance: int, rules: dict[str, Any],
              available: int, today: date | None = None) -> tuple[int, int]:
    """(min, max) bullets for an entry, capped by what the pool has."""
    if kind == "project":
        lo, hi = rules["project_bullets"]
    elif kind == "volunteering":
        lo, hi = 1, 1
    else:
        kind_ = role_type(item, rules, today) if item else "short_role"
        lo, hi = rules[kind_]
        if kind_ in ("short_role", "graduation"):  # 1-3 by how much it matters for this job
            hi = min(hi, 3 if relevance >= 8 else 2 if relevance >= 5 else 1)
            lo = max(lo, 2) if relevance >= 8 and hi >= 2 else min(lo, hi)
    hi = min(hi, available)
    return min(lo, hi), hi


def is_generic(text: str) -> bool:
    """A team-process bullet with no concrete outcome ("Collaborated in Agile sprints")."""
    return bool(_GENERIC_BULLET.search(text)) and not re.search(r"\d", text)


# ----------------------------------------------------------------------------------- skills

# Conventional spellings for tag slugs (used when your own text never spells the term).
DISPLAY = {
    "sql": "SQL", "postgresql": "PostgreSQL", "mysql": "MySQL", "mongodb": "MongoDB",
    "mlflow": "MLflow", "github-actions": "GitHub Actions", "gitlab-ci": "GitLab CI",
    "ollama": "Ollama", "terraform": "Terraform", "git": "Git", "linux": "Linux", "bash": "Bash",
    "docker": "Docker", "docker-compose": "Docker Compose", "python": "Python",
    "fastapi": "FastAPI", "flask": "Flask", "django": "Django", "spring-boot": "Spring Boot",
    "java": "Java", "rest-api": "REST API", "graphql": "GraphQL", "mqtt": "MQTT",
    "testflight": "TestFlight", "yolov8": "YOLOv8", "spacy": "spaCy", "openai": "OpenAI",
    "rag": "RAG", "nlp": "NLP", "llm": "LLM", "llms": "LLMs", "tf-idf": "TF-IDF",
    "localstack": "LocalStack", "s3": "S3", "duckdb": "DuckDB", "dbt": "dbt",
    "airflow": "Airflow", "dart": "Dart", "flutter": "Flutter", "riverpod": "Riverpod",
    "gorouter": "GoRouter", "bff": "BFF", "aws": "AWS", "gcp": "GCP", "azure": "Azure",
    "kafka": "Kafka", "spark": "Spark", "pyspark": "PySpark", "pandas": "pandas",
    "numpy": "NumPy", "pytorch": "PyTorch", "tensorflow": "TensorFlow", "keras": "Keras",
    "scikit-learn": "scikit-learn", "kubernetes": "Kubernetes", "javascript": "JavaScript",
    "typescript": "TypeScript", "react": "React", "nodejs": "Node.js", "node": "Node.js",
    "computer-vision": "Computer Vision", "deep-learning": "Deep Learning", "lstm": "LSTM",
    "cnn": "CNN", "etl": "ETL", "elt": "ELT", "ci-cd": "CI/CD", "firebase": "Firebase",
    "mistral": "Mistral", "whisper": "Whisper", "prophet": "Prophet", "esp32": "ESP32",
    "raspberry-pi": "Raspberry Pi", "iot": "IoT", "clean-architecture": "Clean Architecture",
    "mockito": "Mockito", "google-maps": "Google Maps", "snowflake": "Snowflake",
    "bigquery": "BigQuery", "redis": "Redis", "power-bi": "Power BI", "tableau": "Tableau",
}


def display(term: str, spelled: str | None = None) -> str:
    """How a skill is written: your own spelling if you ever wrote it with capitals, else the
    conventional name for a known slug, else the term as given."""
    if spelled and spelled != spelled.lower():
        return spelled
    if term != term.lower():
        return term
    return DISPLAY.get(term.strip().lower(), spelled or term)


@dataclass
class _Merge:
    kind: str  # group | pair | join
    parent: str
    members: list[str]


def parse_merges(lines: list[str]) -> list[_Merge]:
    out = []
    for raw in lines:
        line = raw.strip()
        if ":" in line:
            parent, rest = line.split(":", 1)
            out.append(_Merge("group", parent.strip(), [m.strip() for m in rest.split(",")
                                                        if m.strip()]))
        elif "+" in line:
            a, b = (x.strip() for x in line.split("+", 1))
            out.append(_Merge("pair", a, [b]))
        elif "/" in line:
            a, b = (x.strip() for x in line.split("/", 1))
            out.append(_Merge("join", a, [b]))
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def merge_items(items: list[str], rules: list[_Merge]) -> list[str]:
    """Apply merge rules inside one skill group, keeping the order of first appearance."""
    items = list(items)
    for rule in rules:
        index = {_norm(x): i for i, x in enumerate(items)}
        members = [m for m in rule.members if _norm(m) in index]
        if rule.kind == "group":
            aliases = GENERIC_ALIASES.get(_norm(rule.parent), set()) | {_norm(rule.parent)}
            generic = [i for i, x in enumerate(items) if _norm(x) in {_norm(a) for a in aliases}]
            if not members:
                continue
            present = [items[index[_norm(m)]] for m in members]
            positions = sorted(generic + [index[_norm(m)] for m in members])
            merged = f"{rule.parent} ({', '.join(present)})"
        else:
            if _norm(rule.parent) not in index or not members:
                continue
            parent = items[index[_norm(rule.parent)]]
            member = items[index[_norm(members[0])]]
            positions = sorted([index[_norm(rule.parent)], index[_norm(members[0])]])
            merged = f"{parent} ({member})" if rule.kind == "pair" else f"{parent}/{member}"
        keep = positions[0]
        items = [merged if i == keep else x for i, x in enumerate(items)
                 if i == keep or i not in positions]
    return items


def shape_skills(groups: list[tuple[str, list[str]]], rules: dict[str, Any],
                 merge_lines: list[str]) -> list[tuple[str, list[str]]]:
    """At most N groups (in the model's relevance order), merges applied, no item repeated
    across groups, at most M items each, empty groups dropped."""
    parsed = parse_merges(merge_lines)
    seen: set[str] = set()
    out = []
    for category, items in groups:
        merged = merge_items(items, parsed)
        unique = []
        for x in merged:
            key = _norm(x)
            if key and key not in seen:
                seen.add(key)
                unique.append(x)
        if unique:
            out.append((category, unique[: int(rules["skill_items_max"])]))
        if len(out) >= int(rules["skill_groups_max"]):
            break
    return out


# ---------------------------------------------------------------------------------- summary

_NUMBER = re.compile(r"\d[\d,.]*\s*[%kKmM+]*")
_YEARS = re.compile(r"\d+\s*\+?\s*(?:years?|yrs?)", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE.split(text.strip()) if s.strip()]


# A sentence opening on one of these is a fragment ("Brings experience…"), not a sentence.
_FRAGMENT_START = {
    "brings", "bringing", "delivers", "offers", "combines", "has", "having", "specializes",
    "specialises", "focuses", "builds", "building", "designs", "designing", "develops",
    "developing", "creates", "adds", "enjoys", "excels", "thrives", "possesses", "demonstrates",
    "leverages", "leveraging", "skilled", "experienced", "adept", "known", "eager", "able",
    # past tense: "Built a resume parser…" has no subject either
    "built", "designed", "developed", "created", "delivered", "led", "shipped", "engineered",
    "architected", "implemented", "launched", "trained", "deployed", "automated", "migrated",
    "optimized", "optimised", "worked", "contributed", "managed", "owned", "drove", "spearheaded",
}
# A career change isn't what you build: kept out of the first words of a Data/AI summary.
_TRANSITION = re.compile(r"\b(transition\w*|moving (?:into|from|toward\w*|to)|pivot\w*|"
                         r"shifting|switching|career change)\b", re.I)
_LEADING_CLAUSE = re.compile(r"^(?:at|in|on|for|during|with|across|since|as)\b[^,]{0,60},\s*",
                             re.I)
_STOP = {"a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "with", "by", "at", "from",
         "into", "as", "is", "are", "that", "this", "its", "their", "using", "based", "via"}


def _content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9][a-z0-9+#.-]*", text.lower()) if w not in _STOP]


def opening(text: str, n: int = 4) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower())[:n])


def summary_problems(text: str, *, rules: dict[str, Any], bullet_texts: list[str],
                     certifications: list[ExperienceItem], internships: list[ExperienceItem],
                     tools: set[str], max_sentences: int | None = None,
                     max_words: int | None = None, banned_phrases: list[str] | None = None,
                     cited_texts: list[str] | None = None,
                     other_openings: list[str] | None = None,
                     lead_with_build: bool = False) -> list[str]:
    """Why a summary breaks the guide (empty = fine). Checked in code; the summary is
    regenerated once with these reasons."""
    max_sentences = max_sentences or int(rules["summary_max_sentences"])
    max_words = max_words or int(rules["summary_max_words"])
    out = []
    n_sent, n_words = len(sentences(text)), len(text.split())
    if n_sent > max_sentences:
        out.append(f"{n_sent} sentences (max {max_sentences})")
    if n_words > round(max_words * 1.15):
        out.append(f"{n_words} words (about {max_words} max)")
    without_years = _YEARS.sub(" ", text)

    def metric(m: str) -> str:
        """The digits of a figure worth flagging (40%, 140K+, 2,000); '' for a bare 1-9."""
        digits = re.sub(r"[^\d]", "", m)
        return digits if digits and (int(digits) >= 10 or re.search(r"[%kKmM+]", m)) else ""

    bullet_numbers = {metric(m) for b in bullet_texts
                      for m in _NUMBER.findall(_YEARS.sub(" ", b))} - {""}
    repeated = sorted({m.strip() for m in _NUMBER.findall(without_years)
                       if metric(m) in bullet_numbers})
    if repeated:
        out.append(f"repeats numbers from the bullets ({', '.join(repeated)})")
    low = text.lower()
    # The issuer or the word itself: a certificate titled "Data Engineer" mustn't match a
    # summary saying "data engineering".
    if re.search(r"\bcertif", low) or any(c.org and len(c.org) > 3 and c.org.lower() in low
                                          for c in certifications):
        out.append("mentions certifications")
    if _INTERN.search(text) or any(i.org and i.org.lower() in low for i in internships):
        out.append("mentions an internship")
    for phrase in banned_phrases or []:
        if phrase.strip() and re.search(rf"\b{re.escape(phrase.strip().lower())}\b", low):
            out.append(f"banned phrase “{phrase.strip()}”")
    if re.search(r"\b(i|my|me|i'm|i've)\b", low):
        out.append("uses the first person (no “I”)")
    for sentence in sentences(text):
        body = _LEADING_CLAUSE.sub("", sentence.strip())  # "At Acme, built…" → "built…"
        first = (re.findall(r"[a-z]+", body.lower()) or [""])[0]
        if first in _FRAGMENT_START:
            start = " ".join(sentence.split()[:3])
            out.append(f"“{start}…” has no subject: start it with a subject such as “Recent "
                       "work includes…” or “Projects include…” (no “I”)")
            break
    first_words = " ".join(text.split()[:8])
    if lead_with_build and _TRANSITION.search(first_words):
        out.append("opens with a career change: lead with what you build (e.g. “Software "
                   "engineer building data pipelines and local LLM systems”)")
    if cited_texts is not None:
        source = _content_words(" ".join(cited_texts))
        pairs = {" ".join(source[i:i + 2]) for i in range(len(source) - 1)}
        words = _content_words(text)
        if not any(" ".join(words[i:i + 2]) in pairs for i in range(len(words) - 1)):
            out.append("names nothing concrete you built (use a project or system from the "
                       "cited items)")
    if other_openings and opening(text) in set(other_openings):
        out.append(f"opens like another CV (“{' '.join(text.split()[:4])}…”): vary the opening")
    for sentence in sentences(text):
        listed = tool_list(sentence, tools)
        if listed:
            out.append(f"lists tools ({', '.join(listed)})")
            break
    return out


def tool_list(sentence: str, tools: set[str]) -> list[str]:
    """An enumeration of 3+ tools ("Python, SQL, dbt and Airflow"). Tools inside a description
    of something built ("a dbt/Airflow lakehouse", "a local Mistral LLM") don't count."""
    def tool_in(chunk: str) -> str | None:
        words = chunk.split()
        if not 0 < len(words) <= 3:
            return None
        return next((t for t in tools if re.search(rf"(?<![\w-]){re.escape(t)}(?![\w-])",
                                                    chunk, re.I)), None)

    run: list[str] = []
    for chunk in re.split(r",|;|\band\b|\bor\b|&", sentence):
        hit = tool_in(chunk.strip(" ."))
        run = [*run, hit] if hit else []
        if len(run) >= 3:
            return [r.lower() for r in run]
    return []


# ------------------------------------------------------------------------------ exemplar

REFERENCE = Path(__file__).resolve().parents[3] / "templates" / "reference" / "cv.tex"


def _plain(tex: str) -> str:
    text = re.sub(r"\$\\sim\$", "~", tex)
    text = text.replace("\\%", "%").replace("``", "\u201c").replace("''", "\u201d")
    text = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", "", text)
    return re.sub(r"[{}]", "", text).strip()


def style_exemplar(path: Path = REFERENCE) -> dict[str, Any]:
    """The reference CV's summary and bullets as plain text: tone and length only."""
    if not path.exists():
        return {}
    tex = path.read_text()
    summary = re.search(r"\\section\{Summary\}\s*\\small\{(.+?)\}\s*\n", tex, re.S)
    bullets = [_plain(b) for b in re.findall(r"\\resumeItem\{(.+?)\}\s*\n", tex)]
    return {"summary": _plain(summary.group(1)) if summary else "", "bullets": bullets[:10]}
