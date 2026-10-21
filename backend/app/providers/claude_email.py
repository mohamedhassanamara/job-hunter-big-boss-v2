"""Cold-email drafter on Claude Code headless mode, with the same isolation and subscription check
as the CV generator (it reuses that call path). One job at a time; never in bulk."""

import json
import re
from pathlib import Path

from app.providers.base import (
    AppliedEmailPlan,
    CVGenerationFailed,
    DraftFailed,
    EmailDraftPlan,
    EmailRequest,
    IntroEmailPlan,
)
from app.providers.claude_cv import TIMEOUT, ClaudeCVGenerator

PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "outreach.md"


def load_sections() -> tuple[str, dict[str, str]]:
    """(version id, sections: system = speculative email, applied = job-linked email, retry)."""
    text = PROMPT_FILE.read_text()
    version = re.search(r"^version:\s*(\S+)", text, re.M)
    sections = dict(re.findall(r"^## (\w+)\n(.*?)(?=^## \w+\n|\Z)", text, re.M | re.S))
    return (f"outreach/v{version.group(1) if version else '0'}",
            {k: v.strip() for k, v in sections.items()})


def load_prompts() -> tuple[str, str, str]:
    """(version id, system prompt, retry instructions) from app/prompts/outreach.md."""
    version, sections = load_sections()
    return version, sections["system"], sections["retry"]


def revision_block(request: EmailRequest) -> str:
    """PREVIOUS DRAFT + the user's feedback (a regeneration with feedback), else nothing."""
    rev = (request.rules or {}).get("revision")
    if not rev:
        return ""
    return ("\n\nPREVIOUS DRAFT (edit this)\nSubject: " + str(rev.get("previous_subject", ""))
            + "\n\n" + str(rev.get("previous_body", ""))
            + "\n\nWHAT THE USER WANTS CHANGED\n" + str(rev.get("feedback", "")))


def with_revise(system: str, request: EmailRequest, revise: str) -> str:
    return system + (f"\n\n{revise}" if (request.rules or {}).get("revision") else "")


def reference_block(request: EmailRequest) -> str:
    """Approved examples of the right level of detail: never to be copied."""
    refs = (request.rules or {}).get("style_reference") or []
    if not refs:
        return ""
    return ("\n\nSTYLE REFERENCE (the level of detail only: never reuse its wording or its "
            "facts unless they are yours for this job)\n" + "\n---\n".join(refs))


def applied_message(request: EmailRequest, feedback: str = "") -> str:
    """The job-linked email's input: the JOB is not private here (the email names it)."""
    signals = (request.rules or {}).get("signals") or []
    return (
        (f"REJECTED DRAFT PROBLEMS\n{feedback}\n\n" if feedback else "")
        + "RULES\n" + json.dumps({k: v for k, v in request.rules.items()
                                   if k not in ("signals", "revision", "style_reference")},
                                  ensure_ascii=False)
        + "\n\nFACTS\n" + json.dumps(request.candidate, ensure_ascii=False)
        + "\n\nCONTACT\n" + json.dumps(request.contact, ensure_ascii=False)
        + revision_block(request) + reference_block(request)
        + "\n\nSIGNALS (optional)\n" + json.dumps(signals, ensure_ascii=False, indent=1)
        + "\n\nJOB\n" + json.dumps(request.job, ensure_ascii=False, indent=1)
        + "\n\nEXPERIENCE POOL\n" + json.dumps(request.pool, ensure_ascii=False, indent=1)
    )


def user_message(request: EmailRequest, feedback: str = "") -> str:
    signals = (request.rules or {}).get("signals")
    return (
        (f"REJECTED DRAFT PROBLEMS\n{feedback}\n\n" if feedback else "")
        + "RULES\n" + json.dumps({k: v for k, v in request.rules.items()
                                   if k not in ("signals", "revision")}, ensure_ascii=False)
        + "\n\nFACTS\n" + json.dumps(request.candidate, ensure_ascii=False)
        + "\n\nCONTACT\n" + json.dumps(request.contact, ensure_ascii=False)
        + revision_block(request)
        + ("\n\nSIGNALS\n" + json.dumps(signals, ensure_ascii=False, indent=1)
           if signals is not None else "")
        + "\n\nJOB (private: use it to decide what to talk about, never mention it)\n"
        + json.dumps(request.job, ensure_ascii=False, indent=1)
        + "\n\nEXPERIENCE POOL\n" + json.dumps(request.pool, ensure_ascii=False, indent=1)
    )


class ClaudeEmailDrafter(ClaudeCVGenerator):
    via = "claude -p"  # Claude Code headless on your subscription (never Ollama)
    def __init__(self, model: str = "claude-sonnet-5", *, timeout: int = TIMEOUT, **kw):  # noqa: ANN003
        super().__init__(model, timeout=timeout, **kw)
        self.prompt_version, sections = load_sections()
        self.email_prompt, self.retry_prompt = sections["system"], sections["retry"]
        self.applied_prompt = sections["applied"]
        self.revise_prompt = sections["revise"]

    def draft_applied(self, request: EmailRequest, feedback: str = "") -> AppliedEmailPlan:
        """The job-linked email: an honest application follow-up (prompt v11+)."""
        system = with_revise(self.applied_prompt, request, self.revise_prompt) \
            + (f"\n\n{self.retry_prompt}" if feedback else "")
        try:
            return self._call(self.command(system, AppliedEmailPlan),
                              applied_message(request, feedback), AppliedEmailPlan)
        except CVGenerationFailed as exc:
            raise DraftFailed(str(exc).replace("plan", "draft")) from exc

    def draft_intro(self, request: EmailRequest, feedback: str = "") -> IntroEmailPlan:
        """The personal introduction (prompt v4+): hook from signals, value, direct ask."""
        system = with_revise(self.email_prompt, request, self.revise_prompt) \
            + (f"\n\n{self.retry_prompt}" if feedback else "")
        try:
            return self._call(self.command(system, IntroEmailPlan),
                              user_message(request, feedback), IntroEmailPlan)
        except CVGenerationFailed as exc:
            raise DraftFailed(str(exc).replace("plan", "draft")) from exc

    def draft(self, request: EmailRequest, feedback: str = "") -> EmailDraftPlan:
        system = self.email_prompt + (f"\n\n{self.retry_prompt}" if feedback else "")
        try:
            return self._call(self.command(system, EmailDraftPlan),
                              user_message(request, feedback), EmailDraftPlan)
        except CVGenerationFailed as exc:  # same call path; say "email" to the user
            raise DraftFailed(str(exc).replace("plan", "draft")) from exc
