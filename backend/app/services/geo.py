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
    "AE": ["united arab emirates", "uae", "u a e", "emirates", "emirats arabes unis"],
    "QA": ["qatar"],
    "BH": ["bahrain", "bahrein"],
    "KW": ["kuwait", "koweit"],
    "JO": ["jordan", "jordanie"],
    "SA": ["saudi arabia", "ksa", "kingdom of saudi arabia", "arabie saoudite"],
    "OM": ["oman", "sultanate of oman"],
    "EG": ["egypt", "egypte"],
    "LB": ["lebanon", "liban"],
    "TN": ["tunisia", "tunisie"],
    "DZ": ["algeria", "algerie"],
    "TR": ["turkey", "turkiye"],
    "SG": ["singapore"],
    "ZA": ["south africa"],
    "NZ": ["new zealand"],
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
    "BE": [
        "brussels", "bruxelles", "brussel", "antwerp", "antwerpen", "anvers", "ghent", "gent",
        "leuven", "louvain", "liege", "namur", "mechelen", "charleroi", "bruges", "brugge",
    ],
    "CH": ["zurich", "geneva", "geneve", "basel", "lausanne"],
    "AT": ["vienna", "wien", "graz"],
    "PL": ["warsaw", "warszawa", "krakow", "wroclaw"],
    "AE": ["dubai", "abu dhabi", "sharjah", "ajman", "ras al khaimah", "al ain", "fujairah"],
    "QA": ["doha", "lusail", "al rayyan", "al wakrah"],
    "BH": ["manama", "muharraq", "riffa", "isa town"],
    "KW": ["kuwait city", "hawalli", "salmiya", "farwaniya", "ahmadi"],
    "JO": ["amman", "irbid", "zarqa", "aqaba"],
    "SA": [
        "riyadh", "jeddah", "dammam", "khobar", "al khobar", "neom", "dhahran", "mecca", "medina",
    ],
    "OM": ["muscat"],
    "EG": ["cairo", "alexandria", "giza"],
    "TN": ["tunis", "sfax", "sousse"],
    "US": ["new york", "san francisco", "seattle", "boston", "austin", "chicago"],
}

EU_EEA = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT",
    "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "IS", "LI", "NO",
}

EUROPE = EU_EEA | {"GB", "CH", "UA", "RS", "AL", "BA", "MK", "ME", "MD"}
GCC = {"AE", "QA", "BH", "KW", "SA", "OM"}
MIDDLE_EAST_NORTH_AFRICA = GCC | {"JO", "LB", "EG", "TN", "MA", "DZ", "TR", "IQ", "PS", "LY"}
AFRICA = {"ZA", "EG", "TN", "MA", "DZ", "NG", "KE", "GH"}
EMEA = EUROPE | MIDDLE_EAST_NORTH_AFRICA | AFRICA
AMERICAS = {"US", "CA", "MX", "BR", "AR", "CL", "CO", "PE"}
ASIA_PACIFIC = {"IN", "SG", "AU", "NZ", "JP", "CN", "PH", "ID", "MY", "VN", "TH", "KR"}

WORLD = frozenset({"*"})  # sentinel: open to every country

# Region words in a remote job's location → the countries it is open to. Longest phrases first.
_REGION_WORDS: list[tuple[str, frozenset[str]]] = [
    (w, frozenset(codes))
    for words, codes in [
        (["worldwide", "anywhere", "global", "globally", "international", "all countries"], WORLD),
        (["middle east", "mena", "gcc", "gulf", "arab world", "gulf region"],
         MIDDLE_EAST_NORTH_AFRICA),
        (["emea"], EMEA),
        (["europe", "european", "european union", "eu", "eea", "schengen"], EUROPE),
        (["cet", "cest", "wet", "west", "eet"], EUROPE),  # European time zones
        (["africa"], AFRICA),
        (["north america", "americas", "latam", "latin america", "south america"], AMERICAS),
        (["est", "pst", "cst", "mst", "us time zones", "us timezones"], {"US", "CA"}),
        (["apac", "asia", "asia pacific", "oceania"], ASIA_PACIFIC),
    ]
    for w in words
]
_REGION_WORDS.sort(key=lambda wc: -len(wc[0]))

# Remote scopes (search profile `remote_scope`): which remote regions count as eligible.
REMOTE_SCOPES = {
    "anywhere": "Remote open to Europe, the Middle East or Africa (EMEA) or worldwide",
    "europe": "Remote open to Europe or worldwide",
    "targets": "Remote open to one of your target countries or worldwide",
}


def region_of(code: str) -> str:
    """Display group for a country code (Settings country picker)."""
    if code in EUROPE:
        return "Europe"
    if code in MIDDLE_EAST_NORTH_AFRICA:
        return "Middle East & North Africa"
    return "Other"


def country_catalog() -> list[dict[str, str]]:
    """Every country the location parser recognises, for the Settings picker."""
    return [
        {"code": code, "name": aliases[0].title(), "region": region_of(code)}
        for code, aliases in COUNTRY_ALIASES.items()
    ]


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


def remote_region(text: str | None) -> frozenset[str] | None:
    """Countries a remote job is open to, from its location text. WORLD for worldwide,
    None when the text names no country or region (unknown)."""
    if not text or not text.strip():
        return None
    folded = fold(text)
    open_to: set[str] = set()
    for word, codes in _REGION_WORDS:
        if _contains(folded, word):
            if codes == WORLD:
                return WORLD
            open_to |= codes
    for code, aliases in COUNTRY_ALIASES.items():
        if any(_contains(folded, a) for a in aliases):
            open_to.add(code)
    if not open_to:
        code = country_from_text(text)  # a city ("Remote, Berlin")
        if code:
            open_to.add(code)
    return frozenset(open_to) or None


def remote_allows(
    text: str | None, country: str | None, targets: set[str], scope: str
) -> tuple[bool, str | None]:
    """Is a remote job eligible under `scope`? Returns (allowed, first excluded code).

    Unknown regions are allowed (better to show a job than hide it silently; the scorer's
    location dimension then judges the listing text). US-only remote is never eligible because
    no scope includes the Americas.
    """
    open_to = remote_region(text)
    if open_to is None and country:
        open_to = frozenset({country})
    if open_to is None or open_to == WORLD:
        return True, None
    eligible = {"anywhere": EMEA | targets, "europe": EUROPE, "targets": targets}.get(
        scope, EMEA | targets
    )
    if open_to & eligible:
        return True, None
    return False, sorted(open_to)[0]
