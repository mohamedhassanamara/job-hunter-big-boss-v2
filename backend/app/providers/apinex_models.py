"""Which model ids belong to the APInex gateway. One definition for every routing decision.

APInex serves fit scoring, the CV, letters, the Copilot, research, and (by the user's choice) the
email and LinkedIn drafter (`DRAFT_MODEL`). The constructive draft reviewer is Google Gemini.
Interview prep, the rewrite, Ask Claude, the claim verifier and everything else that runs through
`claude -p` reject it before any call (`reject`).
"""

# Email + LinkedIn drafting. The `free/` prefix is the gateway's free tier: without it the gateway
# answers 402 "Insufficient balance".
DRAFT_MODEL = "free/gemini-3.8-flash"


def is_apinex(model: str | None) -> bool:
    """`free/*` gateway ids (e.g. `free/minimax-m3.1-flash`, `free/gemini-3.8-flash`), a bare
    `minimax*` id, or `apinex`. A bare `gemini-*` id is Google's."""
    m = (model or "").strip().lower()
    return m.startswith(("free/", "minimax")) or m == "apinex"


def reject(model: str | None, what: str) -> None:
    """Raise before any request when an APInex model is given to a step that can't use it."""
    if is_apinex(model):
        raise ValueError(
            f"{model} is an APInex model: it can score jobs and write the CV, not {what}"
        )


def reject_non_apinex(model: str | None) -> None:
    """The APInex generators only take APInex models."""
    if not is_apinex(model):
        raise ValueError(f"{model} is not an APInex model")
