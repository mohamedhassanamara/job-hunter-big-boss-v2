"""Roles and tracks come from Settings (search_profile.tracks); this module holds LANGUAGE data.

A track groups the job titles the user wants (e.g. "Mobile": Flutter Developer, Mobile Developer)
together with their years of experience in that field. Each role has variants per language
("Développeur Flutter", "Flutter-Entwickler"…), suggested here and editable in the UI.

Nothing in this module names a role. The lexicon below translates generic job-title words
(developer, engineer, data, mobile…) so that:
- `suggest_variants` can propose FR/ES/DE/IT/NL equivalents for any title the user types,
- `match_track` can recognise a listing title in any of those languages.
"""

import re
from typing import Any

from app.services.geo import fold

LANGS = ("en", "fr", "es", "de", "it", "nl")

# Head nouns: the job word a title ends with in English. Romance languages put it first
# ("Développeur Flutter"), German/Dutch compound or keep it last ("Flutter-Entwickler").
HEADS: dict[str, dict[str, list[str]]] = {
    "developer": {"en": ["Developer", "Engineer"], "fr": ["Développeur"], "es": ["Desarrollador"],
                  "de": ["Entwickler"], "it": ["Sviluppatore"], "nl": ["Ontwikkelaar"]},
    "engineer": {"en": ["Engineer"], "fr": ["Ingénieur"], "es": ["Ingeniero"],
                 "de": ["Engineer", "Ingenieur"], "it": ["Ingegnere"], "nl": ["Engineer"]},
    "scientist": {"en": ["Scientist"], "fr": ["Scientist"], "es": ["Científico"],
                  "de": ["Scientist"], "it": ["Scientist"], "nl": ["Scientist"]},
    "analyst": {"en": ["Analyst"], "fr": ["Analyste"], "es": ["Analista"], "de": ["Analyst"],
                "it": ["Analista"], "nl": ["Analist"]},
    "architect": {"en": ["Architect"], "fr": ["Architecte"], "es": ["Arquitecto"],
                  "de": ["Architekt"], "it": ["Architetto"], "nl": ["Architect"]},
}
# Modifiers that are translated (everything else, e.g. "Flutter", "iOS", "Python", is kept as is).
# Romance forms are what follows the head noun ("Ingeniero de datos").
MODIFIERS: dict[str, dict[str, list[str]]] = {
    "data": {"fr": ["Data", "de données"], "es": ["de datos", "Data"], "de": ["Data"],
             "it": ["Data", "dei dati"], "nl": ["Data"]},
    "mobile": {"fr": ["mobile"], "es": ["móvil", "mobile"], "de": ["Mobile", "App"],
               "it": ["mobile"], "nl": ["Mobile", "App"]},
    "ai": {"fr": ["IA"], "es": ["IA"], "de": ["KI", "AI"], "it": ["IA"], "nl": ["AI"]},
    "software": {"fr": ["logiciel"], "es": ["de software"], "de": ["Software"],
                 "it": ["software"], "nl": ["Software"]},
}
_ROMANCE_LANGS = {"fr", "es", "it"}

# Folded word → canonical token, used on both the listing title and the user's role phrases.
_WORDS = {
    "mlops": "ml ops", "genai": "ai", "llm": "ai", "llms": "ai", "ia": "ai", "ki": "ai",
    "engineering": "engineer", "engineers": "engineer",
    "ingenieur": "engineer", "ingenieure": "engineer", "ingeniero": "engineer",
    "ingeniera": "engineer", "ingegnere": "engineer", "engenheiro": "engineer",
    "engenheira": "engineer",
    "developpeur": "developer", "developpeuse": "developer", "desarrollador": "developer",
    "desarrolladora": "developer", "entwickler": "developer", "entwicklerin": "developer",
    "sviluppatore": "developer", "sviluppatrice": "developer", "ontwikkelaar": "developer",
    "programmer": "developer", "programador": "developer", "programadora": "developer",
    "developers": "developer", "development": "developer",
    "donnees": "data", "datos": "data", "dati": "data", "dados": "data", "daten": "data",
    "analytique": "analytics", "movil": "mobile", "moviles": "mobile", "mobil": "mobile",
    "mobiles": "mobile", "developpeurs": "developer", "desarrolladores": "developer",
    "ingenieros": "engineer", "ingenieurs": "engineer", "sviluppatori": "developer",
    "ingegneri": "engineer",
    "analyste": "analyst", "analista": "analyst", "analist": "analyst",
    "architecte": "architect", "arquitecto": "architect", "architekt": "architect",
    "architetto": "architect", "cientifico": "scientist", "logiciel": "software",
}
_PHRASES = [
    (r"\bmachine learning\b", "ml"), (r"\bartificial intelligence\b", "ai"),
    (r"\bintelligence artificielle\b", "ai"), (r"\binteligencia artificial\b", "ai"),
    (r"\bintelligenza artificiale\b", "ai"), (r"\bgen ai\b", "ai"), (r"\bml ops\b", "ml ops"),
]
# Romance head words: only these titles put the job noun first ("Ingeniero de datos").
_ROMANCE_HEADS = {
    "ingenieur", "ingenieure", "ingeniero", "ingeniera", "ingegnere", "engenheiro", "engenheira",
    "developpeur", "developpeuse", "desarrollador", "desarrolladora", "sviluppatore",
    "sviluppatrice", "programador", "programadora", "analyste", "analista", "architecte",
    "arquitecto", "architetto", "cientifico",
}
# German compounds: "Softwareentwickler" → software developer, "Dateningenieur" → data engineer.
_COMPOUND_SUFFIXES = {"entwickler": "developer", "entwicklerin": "developer",
                      "ingenieur": "engineer"}
_MAX_GAP = 2  # words allowed between role tokens ("data platform engineer" ~ "data engineer")
# Titles that contain role words but are another trade ("Data Center Mechanical Engineer").
_NOISE_PHRASES = ("data center", "data centre", "datacenter", "datacentre", "data centers",
                  "data centres", "data entry")
# A gap word from another engineering discipline breaks a match ("AI Mechanical Engineer").
_BLOCKING_GAP = {"electrical", "mechanical", "civil", "hvac", "facilities", "facility",
                 "construction", "commissioning", "mep", "cabling", "structural", "plumbing"}


def _split_compound(word: str) -> list[str]:
    for suffix, head in _COMPOUND_SUFFIXES.items():
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            prefix = word[: -len(suffix)]
            return [_WORDS.get(prefix, prefix), head]
    return [word]


def _normalize(title: str) -> list[tuple[str, bool]]:
    """(token, came_from_a_romance_head) pairs after translation to canonical tokens."""
    text = fold(title)
    for pattern, repl in _PHRASES:
        text = re.sub(pattern, repl, text)
    out: list[tuple[str, bool]] = []
    for w in text.split():
        mapped = _WORDS.get(w)
        parts = mapped.split() if mapped else _split_compound(w)
        out.extend((tok, w in _ROMANCE_HEADS) for tok in " ".join(parts).split())
    return out


def normalize_title(title: str) -> list[str]:
    return [tok for tok, _ in _normalize(title)]


def _in_order(words: list[str], tokens: list[str], starts: set[int] | None = None) -> bool:
    """`tokens` appear in `words` in order, at most _MAX_GAP words apart, and no gap word is
    from another trade. `starts` restricts where the first token may match."""
    for start, w in enumerate(words):
        if w != tokens[0] or (starts is not None and start not in starts):
            continue
        pos, ok = start, True
        for tok in tokens[1:]:
            window = words[pos + 1 : pos + 2 + _MAX_GAP]
            if tok not in window or _BLOCKING_GAP.intersection(window[: window.index(tok)]):
                ok = False
                break
            pos = pos + 1 + window.index(tok)
        if ok:
            return True
    return False


def phrase_matches(title: str, phrase: str) -> bool:
    folded = f" {fold(title)} "
    if any(f" {p} " in folded for p in _NOISE_PHRASES):
        return False
    pairs = _normalize(title)
    words = [tok for tok, _ in pairs]
    tokens = normalize_title(phrase)
    if not tokens:
        return False
    if _in_order(words, tokens):
        return True
    # Romance titles put the noun first ("Ingeniero de datos" → engineer … data). Only there:
    # in English "Backend Engineer Kotlin & Data" is noise.
    romance = {i for i, (_, is_romance) in enumerate(pairs) if is_romance}
    return len(tokens) > 1 and bool(romance) and _in_order(words, tokens[::-1], starts=romance)


# Languages job titles are written in, per country (English is always added).
COUNTRY_LANGS: dict[str, tuple[str, ...]] = {
    "FR": ("fr",), "BE": ("fr", "nl"), "LU": ("fr", "de"), "CH": ("de", "fr", "it"),
    "DE": ("de",), "AT": ("de",), "ES": ("es",), "IT": ("it",), "NL": ("nl",),
}


# ----------------------------------------------------------------------------------- tracks


def tracks_of(profile: Any) -> list[dict[str, Any]]:
    """The profile's tracks; a legacy flat `roles` list becomes one unnamed track."""
    tracks = getattr(profile, "tracks", None) or []
    if tracks:
        return tracks
    roles = getattr(profile, "roles", None) or []
    return [{"name": "", "roles": [{"title": r, "variants": {}} for r in roles]}] if roles else []


def role_phrases(role: dict[str, Any], langs: tuple[str, ...] = LANGS) -> list[str]:
    """Title first, then variants for `langs`, de-duplicated case-insensitively."""
    out, seen = [], set()
    candidates = [role.get("title") or ""]
    for lang in langs:
        candidates += (role.get("variants") or {}).get(lang) or []
    for phrase in candidates:
        key = fold(phrase)
        if key and key not in seen:
            seen.add(key)
            out.append(phrase.strip())
    return out


def with_suggested_variants(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Roles saved without a `variants` key get suggestions; edited variants are kept as is."""
    out = []
    for track in tracks:
        roles = []
        for role in track.get("roles") or []:
            role = {**role, "title": (role.get("title") or "").strip()}
            if not role["title"]:
                continue
            if role.get("variants") is None:
                role["variants"] = suggest_variants(role["title"])
            roles.append(role)
        out.append({**track, "name": (track.get("name") or "").strip(), "roles": roles})
    return out


def query_phrases(profile: Any, country: str | None = None) -> list[str]:
    """Search phrases for a source query: every role title plus its variants in the languages
    of `country` (all languages when None), de-duplicated, in track/role order."""
    langs = ("en", *COUNTRY_LANGS.get((country or "").upper(), ())) if country else LANGS
    out, seen = [], set()
    for track in tracks_of(profile):
        for role in track.get("roles") or []:
            for phrase in role_phrases(role, langs):
                if fold(phrase) not in seen:
                    seen.add(fold(phrase))
                    out.append(phrase)
    return out


def capped(phrases: list[str], limit: int, warnings: list[str], label: str) -> list[str]:
    """Keep the first `limit` phrases (titles come first); note what was trimmed."""
    if len(phrases) > limit:
        warnings.append(
            f"{label}: {len(phrases) - limit} of {len(phrases)} role phrases skipped "
            f"(limit {limit} per query set; trim variants in Settings to choose which)"
        )
    return phrases[:limit]


def all_titles(tracks: list[dict[str, Any]]) -> list[str]:
    return [r["title"] for t in tracks for r in t.get("roles") or [] if r.get("title")]


def match_track(title: str, tracks: list[dict[str, Any]]) -> tuple[str, str] | None:
    """(track name, role title) of the first role whose title or any variant matches."""
    for track in tracks:
        for role in track.get("roles") or []:
            if any(phrase_matches(title, p) for p in role_phrases(role)):
                return track.get("name") or "", role.get("title") or ""
    return None


def matches_role(title: str, roles: list[str]) -> str | None:
    """Flat-list form (a single unnamed track), kept for callers that only have titles."""
    hit = match_track(title, [{"roles": [{"title": r} for r in roles]}])
    return hit[1] if hit else None


# --------------------------------------------------------------------------------- variants


def _split_title(title: str) -> tuple[list[str], str | None, str]:
    """'Senior Flutter Developer' → (['Senior', 'Flutter'], 'developer', 'Developer')."""
    words = title.split()
    if not words:
        return [], None, ""
    last = fold(words[-1])
    head = _WORDS.get(last, last)
    if head in HEADS:
        return words[:-1], head, words[-1]
    return words, None, ""


def _mods(mods: list[str], lang: str) -> list[str]:
    """Translated modifier phrase options for `lang` ('Data' → ['de datos', 'Data'] in es)."""
    if not mods:
        return [""]
    key = fold(" ".join(mods))
    if key in MODIFIERS and lang in MODIFIERS[key]:
        return MODIFIERS[key][lang]
    return [" ".join(mods)]


def suggest_variants(title: str) -> dict[str, list[str]]:
    """Common equivalents of a job title per language. Suggestions only: the user edits them."""
    mods, head, original_head = _split_title(title.strip())
    out: dict[str, list[str]] = {lang: [] for lang in LANGS}
    if head is None:
        return out
    base = " ".join(mods)
    for lang in LANGS:
        forms: list[str] = []
        for noun in HEADS[head].get(lang, []):
            for mod in _mods(mods, lang):
                if lang == "en":
                    forms.append(f"{base} {noun}".strip())
                elif lang in _ROMANCE_LANGS:
                    forms.append(f"{noun} {mod}".strip())
                elif lang == "de" and mod and " " not in mod:
                    forms += [f"{mod}-{noun}", f"{mod} {noun}"]
                else:
                    forms.append(f"{mod} {noun}".strip())
        seen = {fold(title)}
        for f in forms:
            if fold(f) not in seen and f.lower() != original_head.lower():
                seen.add(fold(f))
                out[lang].append(f)
    return out
