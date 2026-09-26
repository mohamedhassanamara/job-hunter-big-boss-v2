import re
import unicodedata

_LEGAL_SUFFIXES = {
    "sl", "slu", "sa", "sas", "sarl", "spa", "srl", "lda", "gmbh", "ag", "bv", "ltd", "inc",
    "llc", "plc", "group", "grupo",
}
# Gender markers ((m/f/d), H/F, M/W/D…) and work-mode suffixes don't make a job different.
_TITLE_NOISE = {
    "m", "f", "h", "d", "x", "w", "mfd", "hf", "fh", "mwd", "wmd", "fhx", "hfx", "mfx",
    "remote", "hybrid", "onsite", "teletravail", "remoto", "remota",
}


def _ascii_words(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.replace(".", ""))
    folded = folded.encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]+", folded)


def normalize_company(name: str) -> str:
    words = [w for w in _ascii_words(name) if w not in _LEGAL_SUFFIXES]
    return " ".join(words) or name.strip().lower()


def normalize_title(title: str) -> str:
    return " ".join(w for w in _ascii_words(title) if w not in _TITLE_NOISE)


def dedupe_key(company: str, title: str, country: str | None) -> str:
    return f"{normalize_company(company)}|{normalize_title(title)}|{(country or '').lower()}"
