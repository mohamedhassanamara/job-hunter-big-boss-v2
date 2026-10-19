"""Company email patterns, in Hunter's notation: {first}.{last}, {f}{last}, {first}, …

`infer` reads known work emails at a domain (Hunter's pattern, cached contacts, your Apollo CSV
imports); `build` makes the address a pattern predicts. A built address is only a guess: it is
never used until a verifier says "valid" (catch-all domains never count). No network here.
"""

import unicodedata
from collections import Counter

PATTERNS = ["{first}.{last}", "{first}{last}", "{f}{last}", "{first}", "{first}_{last}",
            "{first}-{last}", "{last}.{first}", "{last}{f}", "{f}.{last}", "{first}{l}",
            "{last}"]


def ascii_fold(text: str) -> str:
    """"Braët" -> "braet"; keeps letters only."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(c for c in folded.lower() if c.isalpha())


def split_name(full_name: str) -> tuple[str, str]:
    """(first, last) folded; the last word is the last name ("Jean Luc Dupont" -> jean, dupont)."""
    parts = [ascii_fold(p) for p in full_name.replace("-", " ").split() if ascii_fold(p)]
    if len(parts) < 2:
        return (parts[0] if parts else ""), ""
    return parts[0], parts[-1]


def build(pattern: str, full_name: str, domain: str) -> str | None:
    first, last = split_name(full_name)
    if not first or (("{last}" in pattern or "{l}" in pattern) and not last):
        return None
    local = pattern.format(first=first, last=last, f=first[:1], l=last[:1])
    return f"{local}@{domain}" if local and domain else None


def infer(samples: list[tuple[str, str]]) -> tuple[str | None, int, list[str]]:
    """samples = [(full_name, email)] at one domain. Returns (pattern, confidence 0-100, evidence)
    where evidence lists the emails that matched. Needs at least two matching samples, or one
    when it is the only sample, for a (low) confidence."""
    votes: Counter[str] = Counter()
    matched: dict[str, list[str]] = {}
    for name, email in samples:
        local = email.split("@", 1)[0].lower()
        for pattern in PATTERNS:
            if build(pattern, name, "x.test") == f"{local}@x.test":
                votes[pattern] += 1
                matched.setdefault(pattern, []).append(email)
                break  # the first (most common) pattern that explains the address
    if not votes:
        return None, 0, []
    pattern, n = votes.most_common(1)[0]
    confidence = min(95, 40 + 25 * (n - 1)) if n > 1 else 40
    if len(votes) > 1 and votes.most_common(2)[1][1] == n:
        confidence = min(confidence, 40)  # a tie
    return pattern, confidence, matched[pattern]
