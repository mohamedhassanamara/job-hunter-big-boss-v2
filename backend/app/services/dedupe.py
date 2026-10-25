import re
import unicodedata

_LEGAL_SUFFIXES = {
    "sl", "slu", "sa", "sas", "sarl", "spa", "srl", "lda", "gmbh", "ag", "bv", "ltd", "inc",
    "llc", "plc", "corp", "corporation", "co", "llp", "limited", "holding", "holdings",
    "group", "grupo", "technologies", "solutions", "kg", "ab", "oy",
}
# Gender markers ((m/f/d), H/F, M/W/D, all genders…) and work-mode suffixes.
_TITLE_NOISE = {
    "m", "f", "h", "d", "x", "w", "mfd", "hf", "fh", "mwd", "wmd", "fhx", "hfx", "mfx", "fm", "mf",
    "remote", "hybrid", "onsite", "teletravail", "remoto", "remota",
    "gender", "genders", "all", "welcome",
}

_FILLER_PATTERNS = [
    re.compile(r"\b(all genders welcome|all genders|all gender)\b", re.IGNORECASE),
    re.compile(r"\b(full remote|100% remote)\b", re.IGNORECASE),
    re.compile(r"\((m/w/d|m/f/d|f/m/d|d/m/w|w/m/d|h/f/x|h/f|m/f/x|m/f|f/m)\)", re.IGNORECASE),
    re.compile(r"\[(m/w/d|m/f/d|f/m/d|d/m/w|w/m/d|h/f/x|h/f|m/f/x|m/f|f/m)\]", re.IGNORECASE),
    re.compile(r"/(m/w/d|m/f/d|f/m/d|d/m/w|w/m/d|h/f/x|h/f|m/f/x|m/f|f/m)/", re.IGNORECASE),
]


def _ascii_words(text: str) -> list[str]:
    # Remove filler phrase patterns first
    cleaned = text
    for pat in _FILLER_PATTERNS:
        cleaned = pat.sub(" ", cleaned)
    folded = unicodedata.normalize("NFKD", cleaned.replace(".", ""))
    folded = folded.encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]+", folded)


def normalize_company(name: str) -> str:
    words = [w for w in _ascii_words(name) if w not in _LEGAL_SUFFIXES]
    return " ".join(words) or name.strip().lower()


def normalize_title(title: str) -> str:
    words = [w for w in _ascii_words(title) if w not in _TITLE_NOISE]
    return " ".join(words) or title.strip().lower()


def dedupe_fingerprint(company: str, title: str) -> str:
    """Deterministic canonical fingerprint: norm_company::norm_title."""
    return f"{normalize_company(company)}::{normalize_title(title)}"


def dedupe_key(company: str, title: str, country: str | None = None) -> str:
    return dedupe_fingerprint(company, title)
