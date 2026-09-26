import re
import unicodedata

_LEGAL_SUFFIXES = {
    "sl", "slu", "sa", "sas", "sarl", "spa", "srl", "lda", "gmbh", "ag", "bv", "ltd", "inc",
    "llc", "plc", "group", "grupo",
}
_TITLE_NOISE = {"m", "f", "h", "d", "x", "mfd", "hf", "fh", "remote", "hybrid"}


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
