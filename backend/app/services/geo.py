"""Country detection from free-text locations, and remote-region compatibility."""

import re
import unicodedata

COUNTRY_ALIASES: dict[str, list[str]] = {
    "ES": ["spain", "espana", "espagne", "spanien", "spagna"],
    "PT": ["portugal"],
    "FR": ["france", "frankreich", "francia", "franca"],
    "IT": ["italy", "italia", "italie", "italien"],
    "DE": ["germany", "deutschland", "allemagne", "alemania", "germania"],
    "GB": ["united kingdom", "uk", "england", "scotland", "great britain", "royaume uni"],
    "IE": ["ireland", "irlande"],
    "NL": ["netherlands", "nederland", "the netherlands", "pays bas", "holland"],
    "BE": ["belgium", "belgique", "belgie"],
    "LU": ["luxembourg"],
    "CH": ["switzerland", "suisse", "schweiz", "svizzera"],
    "AT": ["austria", "osterreich", "autriche"],
    "PL": ["poland", "polska", "pologne"],
    "CZ": ["czech republic", "czechia"],
    "SE": ["sweden", "sverige"],
    "DK": ["denmark", "danmark"],
    "NO": ["norway", "norge"],
    "FI": ["finland", "suomi"],
    "EE": ["estonia"],
    "LT": ["lithuania"],
    "LV": ["latvia"],
    "RO": ["romania"],
    "BG": ["bulgaria"],
    "GR": ["greece"],
    "HR": ["croatia"],
    "SI": ["slovenia"],
    "SK": ["slovakia"],
    "HU": ["hungary"],
    "CY": ["cyprus"],
    "MT": ["malta"],
    "US": ["united states", "usa", "us", "u s", "united states of america"],
    "CA": ["canada"],
    "MX": ["mexico"],
    "BR": ["brazil", "brasil"],
    "IN": ["india"],
    "AU": ["australia"],
    "MA": ["morocco", "maroc"],
}

CITIES: dict[str, list[str]] = {
    "ES": [
        "madrid", "barcelona", "valencia", "sevilla", "seville", "bilbao", "malaga", "zaragoza",
        "alicante", "palma", "las palmas", "granada", "murcia", "san sebastian", "donostia",
        "a coruna", "vigo", "valladolid", "cordoba", "santander", "pamplona", "gijon", "oviedo",
    ],
    "PT": ["lisbon", "lisboa", "porto", "oporto", "braga", "coimbra", "aveiro", "faro", "funchal"],
    "FR": [
        "paris", "lyon", "marseille", "toulouse", "nantes", "lille", "bordeaux", "nice",
        "strasbourg", "montpellier", "rennes", "grenoble", "sophia antipolis", "la defense",
        "aix en provence", "boulogne billancourt", "levallois perret", "issy les moulineaux",
        "neuilly sur seine", "massy", "nanterre",
    ],
    "IT": [
        "milan", "milano", "rome", "roma", "turin", "torino", "bologna", "florence", "firenze",
        "naples", "napoli", "genoa", "genova", "venice", "venezia", "padova", "padua", "verona",
        "trento", "bari", "brescia", "bergamo",
    ],
    "DE": [
        "berlin", "munich", "munchen", "hamburg", "cologne", "koln", "frankfurt", "stuttgart",
        "dusseldorf", "leipzig", "dresden", "hannover", "nuremberg", "nurnberg", "bremen",
        "essen", "dortmund", "karlsruhe", "mannheim", "bonn",
    ],
    "GB": ["london", "manchester", "edinburgh", "bristol", "cambridge", "oxford", "leeds"],
    "NL": ["amsterdam", "rotterdam", "utrecht", "eindhoven", "the hague", "den haag"],
    "IE": ["dublin", "cork"],
    "BE": ["brussels", "bruxelles", "antwerp", "ghent"],
    "CH": ["zurich", "geneva", "geneve", "basel", "lausanne"],
    "AT": ["vienna", "wien", "graz"],
    "PL": ["warsaw", "warszawa", "krakow", "wroclaw"],
    "US": ["new york", "san francisco", "seattle", "boston", "austin", "chicago"],
}

EU_EEA = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT",
    "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "IS", "LI", "NO",
}

# Broad regions that include someone living in Southern Europe.
_BROAD_REGIONS = ["worldwide", "anywhere", "global", "europe", "european", "eu", "eea", "emea"]
# Timezone hints: only meaningful when no specific country is named.
_TIMEZONES = ["cet", "cest", "gmt", "utc", "wet", "west"]


def fold(text: str) -> str:
    """Lowercase, strip accents and punctuation → space-separated words."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text))


def _contains(haystack: str, needle: str) -> bool:
    return f" {needle} " in f" {haystack} "


def country_from_text(text: str | None) -> str | None:
    """Best-effort ISO country code for a location string like 'Barcelona, Spain'."""
    if not text:
        return None
    folded = fold(text)
    # Prefer the last-mentioned country ("Remote from Spain, based in France" → France).
    best: tuple[int, str] | None = None
    for code, aliases in COUNTRY_ALIASES.items():
        for alias in aliases:
            idx = f" {folded} ".rfind(f" {alias} ")
            if idx >= 0 and (best is None or idx > best[0]):
                best = (idx, code)
    if best:
        return best[1]
    for code, cities in CITIES.items():
        if any(_contains(folded, c) for c in cities):
            return code
    return None


def region_allows(text: str | None, targets: set[str]) -> tuple[bool, str | None]:
    """Is a remote job's candidate region open to someone in one of `targets`?

    Returns (allowed, detected_code). Unknown/empty regions are allowed: better to show a job
    than to hide it silently.
    """
    if not text or not text.strip():
        return True, None
    folded = fold(text)
    mentioned = {
        code
        for code, aliases in COUNTRY_ALIASES.items()
        if any(_contains(folded, a) for a in aliases)
    }
    if mentioned & targets:
        return True, sorted(mentioned & targets)[0]
    if any(_contains(folded, r) for r in _BROAD_REGIONS):
        return True, None
    if mentioned:
        return False, sorted(mentioned)[0]
    if any(_contains(folded, tz) for tz in _TIMEZONES):
        return True, None
    return True, None
