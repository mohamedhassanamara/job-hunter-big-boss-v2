"""Lightweight safety for one-click LinkedIn captures (docs/LINKEDIN_EXTENSION_DESIGN.md §12).

A capture saves at once, so a silently wrong read (a snippet taken as the whole listing, the wrong
company link) would land unseen. Instead of a review screen, the server derives flags from what was
read; the LinkedIn Jobs / Profiles sections show flagged items first, and "Looks right" clears them.
Pure functions: the flags are stored in the existing JSON columns (`job.capture["review"]`,
`linkedin_profile.capture_sources["review"]`), so there is no schema change."""

from typing import Any

from app.models.base import utcnow

SHORT_LISTING = 500


def _flag(code: str, text: str) -> dict[str, str]:
    return {"code": code, "text": text}


def job_flags(*, description: str, collapsed: bool, description_source: str, location: str,
              country: str | None, workplace: str, company_url_source: str) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    if collapsed:
        flags.append(_flag("collapsed", 'The listing was still collapsed ("… more"): the '
                                        "description may be cut off"))
    elif description_source == "meta":
        flags.append(_flag("summary_only", "The description comes from the page's summary tag, "
                                           "not the listing"))
    elif len(description) < SHORT_LISTING:
        flags.append(_flag("short", f"The description is short ({len(description)} characters)"))
    if not location:
        flags.append(_flag("no_location", "No location was read from the top card"))
    elif not country and workplace.lower() != "remote":
        flags.append(_flag("no_country", f'No country found in "{location}"'))
    if company_url_source == "guessed":
        flags.append(_flag("company_link", "No company link matched the company name: the first "
                                          "company link on the page was used"))
    return flags


def person_flags(*, headline: str, current_title: str, company_source: str,
                 has_dated_experience: bool) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    if company_source == "headline":
        flags.append(_flag("company_headline", "The company was taken from the headline"))
    elif company_source == "typed":
        flags.append(_flag("company_typed", "You typed the company: the page did not give it"))
    if not headline:
        flags.append(_flag("no_headline", "No headline was read"))
    if not has_dated_experience:
        flags.append(_flag("no_experience", "No dated experience was read"))
    if not current_title and not headline:
        flags.append(_flag("role_unclear", "No title words to decide the role from"))
    return flags


def block(flags: list[dict[str, str]], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """What is stored. A recapture that raises nothing new keeps an earlier "Looks right"."""
    reviewed = (previous or {}).get("reviewed_at")
    old = {f["code"] for f in (previous or {}).get("flags", [])}
    if reviewed and not {f["code"] for f in flags} <= old:
        reviewed = None  # something new to look at
    return {"flags": flags, "reviewed_at": reviewed}


def mark_reviewed(review: dict[str, Any] | None) -> dict[str, Any]:
    return {"flags": (review or {}).get("flags", []), "reviewed_at": utcnow().isoformat()}


def needs_review(review: dict[str, Any] | None) -> bool:
    return bool(review and review.get("flags") and not review.get("reviewed_at"))
