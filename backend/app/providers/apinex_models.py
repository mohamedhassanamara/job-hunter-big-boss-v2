"""Which model ids belong to the APInex gateway. One definition for every routing decision.

APInex is valid for fit scoring and the CV only. Email, letters, interview prep, the Copilot's
rewrite, the claim verifier and everything else that runs through `claude -p` reject it before
any call (`reject`).
"""


def is_apinex(model: str | None) -> bool:
    """`free/*` gateway ids (e.g. `free/minimax-m3.1-flash`), a bare `minimax*` id, or `apinex`."""
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
