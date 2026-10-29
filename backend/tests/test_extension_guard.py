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


def test_sources_never_automate_or_request_anything() -> None:
    offenders = [f"{p.relative_to(EXT)}: {name}" for p in _sources() for name, pat in BANNED.items()
                 if re.search(pat, _code(p))]
    assert offenders == []


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
