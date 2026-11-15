"""The LinkedIn capture extension reads only the page you click on: no timers, observers, clicks,
scrolling, network, innerHTML or CSS class reads in its sources, and no permission beyond
linkedin.com (docs/LINKEDIN_EXTENSION_DESIGN.md §2.2, §2.7, §2.8). Offline: it scans the sources."""

import json
import re
from pathlib import Path

EXT = Path(__file__).resolve().parents[2] / "extension"
SRC = EXT / "src"

BANNED = {
    "timer": r"\b(?:setInterval|setTimeout|requestAnimationFrame|requestIdleCallback)\b",
    "observer": r"\b(?:MutationObserver|IntersectionObserver|ResizeObserver)\b",
    "click": r"\.click\(",
    "scroll": r"\b(?:scrollTo|scrollBy|scrollIntoView)\b",
    "dispatch": r"\bdispatchEvent\b",
    "network": r"\b(?:fetch|XMLHttpRequest|WebSocket|sendBeacon|EventSource)\b\s*\(?",
    "navigation": r"\b(?:window\.open|location\.(?:assign|replace)|location\.href\s*=)",
    "innerHTML": r"\.(?:innerHTML|outerHTML)\b|insertAdjacentHTML",
    "class read": r"\.className\b|\bclassList\b|getAttribute\(\s*['\"]class['\"]",
}


def _code(path: Path) -> str:
    text = path.read_text()
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)(^|\s)//.*$", r"\1", text)


def _sources() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.ts") if not p.name.endswith(".d.ts"))


def test_the_extension_has_sources() -> None:
    assert (EXT / "manifest.json").exists() and _sources()


def test_manifest_asks_for_nothing_beyond_linkedin() -> None:
    m = json.loads((EXT / "manifest.json").read_text())
    assert m["manifest_version"] == 3
    assert m["permissions"] == ["storage"]
    assert m["host_permissions"] == ["https://www.linkedin.com/*"]
    assert [c["matches"] for c in m["content_scripts"]] == [["https://www.linkedin.com/*"]]
    assert "web_accessible_resources" not in m  # nothing for a page to probe
    assert "externally_connectable" not in m
    assert m["options_ui"]["page"] == "options.html"  # pairing lives there, not on linkedin.com


# The one file that may touch the network: your own app on this computer, with the token.
NETWORK_FILE = SRC / "background" / "api.ts"


def test_sources_never_automate_or_request_anything() -> None:
    offenders = [f"{p.relative_to(EXT)}: {name}" for p in _sources() for name, pat in BANNED.items()
                 if re.search(pat, _code(p)) and not (name == "network" and p == NETWORK_FILE)]
    assert offenders == []


def test_the_only_network_call_goes_to_localhost_under_ext() -> None:
    code = _code(NETWORK_FILE)
    assert len(re.findall(r"\bfetch\(", code)) == 1
    assert "localhost" in code and "127.0.0.1" in code and "'http:'" in code
    assert "path.startsWith('/ext/')" in code  # nothing but the extension routes
    # the call target is built from the validated origin, never from a page or a message
    assert "fetch(`${origin}/api${path}`" in code
    hosts = set(re.findall(r"https?://[A-Za-z0-9.-]+(?::\d+)?", code))
    # (the two defaults, and the two hosts named in the validation error message)
    assert hosts <= {"http://localhost:8000", "http://localhost:5173", "http://localhost",
                     "http://127.0.0.1"}


def test_the_token_never_reaches_a_page() -> None:
    """Only the worker and the options page read the token; the content script (which runs inside
    linkedin.com) and the shared code never read it or the storage entry that holds it. (The word
    may appear in a message shown to you.)"""
    reads = re.compile(r"\.token\b|storage\.local\.get\(\s*['\"]config|Authorization")
    for folder in ("content", "shared", "popup"):
        for p in (SRC / folder).rglob("*.ts"):
            assert not reads.search(_code(p)), f"{folder}/{p.name}"


def test_no_css_class_or_id_selectors() -> None:
    """LinkedIn's classes are hashed and unstable: selectors use tags, roles and attributes only."""
    call = re.compile(r"(?:querySelector(?:All)?|closest|matches)\(\s*(['\"`])(.*?)\1")
    offenders = []
    for p in _sources():
        for _quote, selector in call.findall(_code(p)):
            bare = re.sub(r"\[[^\]]*\]", "", selector)
            if re.search(r"[.#][A-Za-z_-]", bare):
                offenders.append(f"{p.relative_to(EXT)}: {selector}")
    assert offenders == []


def test_the_lookup_reads_the_address_only_and_never_the_page() -> None:
    """The profile lookup runs without a click, so it may use ONLY the slug from
    `location.pathname`: the pure module has no DOM access, and the content script's lookup never
    extracts or queries."""
    pure = _code(SRC / "shared" / "lookup.ts")
    assert not re.search(r"\b(?:document|window|querySelector|chrome)\b", pure)
    content = _code(SRC / "content" / "index.ts")
    body = re.search(r"async function refreshLookup\(\).*?\n}\n", content, flags=re.S)
    assert body, "refreshLookup is missing"
    fn = body.group(0)
    assert "slugFromPath(location.pathname)" in fn and "lookupPath(slug)" in fn
    page_reads = r"\b(?:extract|skeleton|document|querySelector|innerText|textContent)\b"
    assert not re.search(page_reads, fn)
    # only the GET lookup is sent from it: nothing is saved or changed without your click
    assert "'POST'" not in fn and "'PATCH'" not in fn and "'DELETE'" not in fn
