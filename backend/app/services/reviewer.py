"""The constructive reviewer: feedback on a draft, never a verdict.

Replaces the claim verifier in the approval flow. It sends the exact text and its sources
(`verifier.prepare_*`) to the reviewer model and returns feedback, suggestions, an optional
revised body and the informational `has_unverified_claims` flag. It stores nothing, blocks
nothing, and a reviewer that can't answer returns an `error` text instead of raising.
"""

from typing import Any

from sqlmodel import Session

from app.models import LinkedInOutreach, OutreachDraft
from app.services import verifier


def _run(reviewer: Any, prepared: verifier.Prepared) -> dict[str, Any]:
    review, error = reviewer.review(
        {"kind": prepared.kind, "text": prepared.text, "sources": prepared.sources})
    return {**review.model_dump(), "model": reviewer.model, "error": error}


def review_email(s: Session, draft: OutreachDraft, reviewer: Any) -> dict[str, Any]:
    prepared = verifier.prepare_email(s, draft)
    # The editable body only (the signature is added when it is sent), so that a revised_body can
    # replace the body as it is.
    prepared.text = draft.body
    prepared.kind += "; the text is the body only, the subject and signature are added separately"
    return _run(reviewer, prepared)


def review_linkedin(s: Session, row: LinkedInOutreach, kind: str, reviewer: Any) -> dict[str, Any]:
    return _run(reviewer, verifier.prepare_linkedin(s, row, kind))
