"""Which language a message is written in, and why.

The old detector was a two-way vote (French vs English), so a German listing counted as French
whenever the German words "du" and "des" (also French) outweighed the English ones. Now the
listing's language is detected among English, French, German, Spanish and Arabic, and the rule is:

  write in the listing's language only if you speak it at a working level (Settings → Candidate
  languages: Professional working, Full professional or Native) and the app can write it
  (English and French: the greeting, subject and years wording are built by code in those two);
  otherwise write in English.

An explicit choice always wins (the draft's language dropdown, a job's language setting, Settings →
Email language) and the reason says so.
"""

import re
from dataclasses import dataclass
from typing import Any

NAMES = {"en": "English", "fr": "French", "de": "German", "es": "Spanish", "ar": "Arabic"}
SUPPORTED = ("en", "fr")  # what the app can write (greetings, subjects, years wording)
# LinkedIn's proficiency levels: these count as "a working level".
_WORKING = ("native", "bilingual", "full professional", "professional working")
_MIN_VOTES = 3  # fewer stop words than this: not enough text to tell

# Stop words, without the words two languages share (du, des, in, an, la, en, de…).
_STOP_WORDS: dict[str, set[str]] = {
    "en": {"the", "and", "of", "to", "for", "with", "you", "we", "our", "is", "are", "be", "on",
           "as", "at", "by", "this", "that", "will", "your", "or", "from", "have", "who", "it",
           "can", "about", "their", "an", "what", "all", "has", "not", "more"},
    "fr": {"le", "les", "est", "pour", "dans", "une", "avec", "vous", "nous", "sur", "au", "aux",
           "ce", "cette", "qui", "que", "par", "sont", "être", "notre", "nos", "votre", "vos",
           "ou", "il", "elle", "leur", "chez", "poste", "équipe", "expérience", "et", "à", "un",
           "pas", "plus", "tous", "toutes", "ses", "mais"},
    "de": {"der", "die", "das", "und", "ist", "nicht", "mit", "für", "auf", "wir", "du", "dir",
           "dich", "sie", "ein", "eine", "einen", "einem", "zu", "von", "im", "den", "dem", "bei",
           "oder", "auch", "als", "wird", "werden", "sind", "haben", "deine", "dein", "unser",
           "unsere", "ihre", "ihr", "mehr", "über", "aus", "nach", "zum", "zur", "uns", "was",
           "wenn", "dass", "kannst", "bist", "hier", "wie", "sich", "es", "des", "arbeit"},
    "es": {"el", "los", "las", "y", "que", "para", "con", "por", "una", "del", "su", "nuestro",
           "nuestra", "equipo", "experiencia", "es", "se", "al", "más", "como", "trabajo"},
}
_ARABIC = re.compile(r"[؀-ۿ]")
_WORD = re.compile(r"[a-zà-ÿœæßäöü]+")


@dataclass
class Choice:
    language: str  # what the message is written in: en | fr
    detected: str  # what the listing is in: en | fr | de | es | ar
    source: str  # auto | override | job | setting
    reason: str  # one sentence for the draft header

    def as_dict(self) -> dict[str, str]:
        return {"language": self.language, "detected": self.detected, "source": self.source,
                "reason": self.reason}


def detect(text: str | None) -> tuple[str, int]:
    """(language, votes): a stop-word vote across languages (Arabic by script). English when
    there is too little text to tell."""
    text = (text or "").lower().replace("’", "'")
    letters = re.findall(r"[^\W\d_]", text)
    if letters and len(_ARABIC.findall(text)) / len(letters) > 0.3:
        return "ar", len(letters)
    words = _WORD.findall(text)
    votes = {lang: sum(w in stops for w in words) for lang, stops in _STOP_WORDS.items()}
    best = max(votes, key=lambda k: (votes[k], k == "en"))
    if votes[best] < _MIN_VOTES:
        return "en", votes[best]
    return best, votes[best]


def working_languages(profile: dict[str, Any] | None) -> set[str]:
    """Language codes you speak at a working level (Settings → Candidate languages)."""
    by_name = {v.lower(): k for k, v in NAMES.items()}
    out = set()
    for entry in (profile or {}).get("languages") or []:
        code = by_name.get(str(entry.get("language") or "").strip().lower())
        if code and any(w in str(entry.get("level") or "").lower() for w in _WORKING):
            out.add(code)
    return out


def choose(listing: str | None, profile: dict[str, Any] | None, *, setting: str = "auto",
           job_setting: str = "auto", override: str | None = None) -> Choice:
    """The language to write in, with the detected one and the reason."""
    detected, _votes = detect(listing)
    for source, value, label in (("override", override, "your choice for this draft"),
                                 ("job", job_setting, "this job's language setting"),
                                 ("setting", setting, "Settings → Email language")):
        if value in SUPPORTED:
            return Choice(value, detected, source,
                          f"{NAMES[value]}: {label} (the listing is in {NAMES[detected]}).")
    spoken = working_languages(profile)
    listed = bool((profile or {}).get("languages"))  # nothing listed: no rule to apply
    if detected in SUPPORTED and (detected in spoken or not listed):
        why = "the listing is in {d}" + (" and you speak it at a working level"
                                         if listed else " (no languages set in Settings → "
                                                        "Candidate)")
        return Choice(detected, detected, "auto", NAMES[detected] + ": " + why.format(
            d=NAMES[detected]) + ".")
    if detected in SUPPORTED:  # supported, but not one you speak
        return Choice("en", detected, "auto",
                      f"English: the listing is in {NAMES[detected]}, which isn't a working "
                      "language in your profile.")
    if detected in spoken:  # you speak it, the app can't write it yet
        return Choice("en", detected, "auto",
                      f"English: the listing is in {NAMES[detected]}, which you speak, but the "
                      "app writes emails in English or French only.")
    if detected == "en":
        return Choice("en", "en", "auto", "English: the listing is in English.")
    return Choice("en", detected, "auto",
                  f"English: the listing is in {NAMES[detected]}, which isn't a working language "
                  "in your profile.")
