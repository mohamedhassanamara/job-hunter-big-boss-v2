"""Apply the suggested fixes of flagged claims (services/claim_fix.py). The suggestions come with
the verification itself; applying edits the text and re-verifies only the changed sentences."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, WorkspaceDep
from app.services import claim_fix, verifier

router = APIRouter(tags=["claim-fixes"])


class Fix(BaseModel):
    sentence: str
    replacement: str = ""  # "" removes the sentence


class ApplyIn(BaseModel):
    kind: Literal["email", "letter", "answer", "linkedin"]
    id: int
    sub: Literal["note", "followup", "inmail", ""] = ""  # which LinkedIn message
    fixes: list[Fix] = Field(min_length=1)


class ApplyOut(BaseModel):
    verification: dict[str, Any]
    verification_state: str


@router.post("/claim-fixes/apply", response_model=ApplyOut)
def apply_fixes(body: ApplyIn, session: SessionDep, workspace: WorkspaceDep) -> ApplyOut:
    """Apply one or several fixes, then re-verify only the sentences they changed."""
    try:
        record = claim_fix.apply(session, body.kind, body.id, body.sub,
                                 [(f.sentence, f.replacement) for f in body.fixes],
                                 verifier.for_workspace(session, workspace))
    except claim_fix.FixError as exc:
        session.rollback()
        raise HTTPException(409, str(exc)) from exc
    return ApplyOut(verification=record, verification_state=str(record.get("status") or "none"))
