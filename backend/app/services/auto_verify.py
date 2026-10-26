"""Claim verification in the background, so a draft shows "verified" (or why not) when you open
it and Approve doesn't wait for a Claude call.

After an email draft is written: verify it (Claude, subscription). If it fails on claims, write
ONE new draft with the failing claims as feedback and verify that once; then stop. A verifier that
couldn't run never triggers a rewrite. Later, a draft still in review whose text you edited (after
a quiet minute) or whose sources changed (your pool or profile) is verified again, once per change.
Nothing is approved or sent here; approval stays yours.
"""

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.models import OutreachDraft
from app.models.base import utcnow
from app.models.enums import DraftStatus
from app.services import verifier

log = logging.getLogger(__name__)
EDIT_QUIET = timedelta(seconds=60)  # re-verify an edited draft once you stopped typing


def _blocking_errors(draft: OutreachDraft) -> bool:
    return any(v.get("severity") == "error" for v in draft.violations or [])


def feedback_from(record: dict[str, Any]) -> str:
    """The failing claims, as the note the drafter rewrites from."""
    bad = [c for c in record.get("claims") or [] if c.get("verdict") in verifier.BLOCKING]
    lines = [f"- “{c.get('claim', '')}” {verifier.LABEL.get(c.get('verdict', ''), '')}"
             + (f" ({str(c['reason']).rstrip('.')})" if c.get("reason") else "") for c in bad]
    return ("The claim check found statements your sources don't support. Rewrite the email so "
            "every sentence says only what your experience, the listing or the recipient "
            "details state; drop a claim rather than soften it:\n" + "\n".join(lines))


def _verify(engine: Engine, draft_id: int, workspace: str) -> dict[str, Any] | None:
    with Session(engine) as s:
        draft = s.get(OutreachDraft, draft_id)
        if draft is None or draft.status != DraftStatus.draft or _blocking_errors(draft):
            return None  # the code checks come first: Claude only sees a text that passes them
        record = verifier.verify_email(s, draft, verifier.for_workspace(s, workspace))
        s.commit()
        return record


def verify_after_draft(engine: Engine, draft_id: int, *, drafter: Any,
                       workspace: str = "real") -> tuple[int, dict[str, Any]]:
    """Verify a new draft; on failed claims write one revision and verify it. Returns the id of
    the draft that is left to review and what happened (stored on the generation task)."""
    from app.services import outreach

    info: dict[str, Any] = {"verify_attempts": 0}
    try:
        record = _verify(engine, draft_id, workspace)
        if record is None:
            info["verify"] = "skipped: the code checks found errors to fix first"
            return draft_id, info
        info["verify_attempts"], info["verify"] = 1, record["status"]
        if record["status"] != "failed":  # passed, or "error": the verifier couldn't run
            return draft_id, info
        with Session(engine) as s:
            app_id = s.get(OutreachDraft, draft_id).application_id
        revised = outreach.generate_applied(engine, app_id, drafter,
                                            feedback=feedback_from(record),
                                            base_draft_id=draft_id)
        info["regenerated_from"] = draft_id
        again = _verify(engine, revised.id, workspace)
        info["verify_attempts"] = 2
        info["verify"] = again["status"] if again else "skipped: the code checks found errors"
        return revised.id, info
    except Exception as exc:  # noqa: BLE001 (the draft itself is fine: say what didn't run)
        log.warning("background verification of draft %s failed: %s", draft_id, exc)
        info["verify"] = f"not run: {str(exc)[:200]}"
        return draft_id, info


def stale_drafts(s: Session) -> list[OutreachDraft]:
    """Drafts in review whose last verification no longer matches the text or the sources."""
    stamp, now, out = verifier.pool_stamp(s), utcnow(), []
    for d in s.exec(select(OutreachDraft).where(OutreachDraft.status == DraftStatus.draft)
                    .order_by(col(OutreachDraft.id))).all():
        if not d.verification or _blocking_errors(d):
            continue  # never verified (by choice or earlier failure) or fix the checks first
        text = verifier.email_text(s, d)
        if verifier.state(d.verification, text, stamp) != "stale":
            continue
        edited = d.verification.get("hash") != verifier.text_hash(text)
        if edited and d.updated_at and now - d.updated_at < EDIT_QUIET:
            continue  # still typing (a changed pool has no reason to wait)
        out.append(d)
    return out


def stale_tick(engine: Engine, workspace: str = "real") -> bool:
    """Verify one stale draft (the worker calls this when it has nothing else to do)."""
    with Session(engine) as s:
        stale = stale_drafts(s)
        draft_id = stale[0].id if stale else None
    if draft_id is None:
        return False
    _verify(engine, draft_id, workspace)
    return True
