"""Contact finders (Phase 12): Hunter, Prospeo, Apollo and Apify behind one small interface.

Only the Get contact waterfall (services/contact_waterfall.py, one click) calls them. Each finder
has a pure `parse_*` mapper (tested offline) and uses PoliteClient with retries=0 on paid calls,
because a retry could spend a second credit. Keys are passed per call (never stored on the object
or in a URL) so the quota layer can rotate them; errors are typed so a refused key is disabled
and never retried.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from app.providers.http import SourceError


class FinderError(RuntimeError):
    """The provider failed; nothing was found (and normally nothing was charged)."""


class KeyRefused(FinderError):
    """Auth error, suspended, or forbidden: disable the key, never retry it."""


class OutOfCredits(FinderError):
    """The provider says this key has no credits left."""


class RateLimited(FinderError):
    """Too many requests: skip this provider for now (no retry loop)."""


def classify(exc: SourceError) -> FinderError:
    text = str(exc).lower()
    status = exc.status
    if status in (401, 403) or "invalid_api_key" in text or "unauthorized" in text \
            or "suspend" in text or "banned" in text:
        return KeyRefused(str(exc))
    if status == 402 or "insufficient_credits" in text or "no credits" in text \
            or "usage limit" in text or "limit reached" in text:
        return OutOfCredits(str(exc))
    if status == 429 or "http 429" in text or "rate_limit" in text:
        return RateLimited(str(exc))
    return FinderError(str(exc))


@dataclass
class Cost:
    credits: float = 0.0
    usd: float = 0.0

    def __add__(self, other: "Cost") -> "Cost":
        return Cost(self.credits + other.credits, self.usd + other.usd)


@dataclass
class Candidate:
    """Someone a provider listed. `email_status` is the provider's own deliverability verdict:
    only "valid" is ever used; accept_all (catch-all), unknown and invalid never are."""

    full_name: str
    title: str | None = None
    email: str | None = None
    email_status: str | None = None  # valid | accept_all | unknown | invalid
    provider: str = ""
    provider_id: str | None = None  # for reveal (Prospeo person_id, Apollo id)
    linkedin_url: str | None = None
    has_email: bool | None = None  # known before revealing (Prospeo/Apollo)
    actor: str | None = None
    key_label: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def load(cls, data: dict[str, Any]) -> "Candidate":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @property
    def verified(self) -> bool:
        return bool(self.email) and self.email_status == "valid"


@dataclass
class Search:
    candidates: list[Candidate] = field(default_factory=list)
    cost: Cost = field(default_factory=Cost)
    pattern: str | None = None  # Hunter's "{first}.{last}"
    pattern_confidence: int | None = None
    organization: dict[str, Any] = field(default_factory=dict)  # industry, linkedin_url, size


class ContactFinder(Protocol):
    provider: str
    unit: str  # "credits" | "usd"

    def search(self, key: str, domain: str, titles: list[str], *, limit: int = 10) -> Search: ...

    def reveal(self, key: str, candidate: Candidate) -> tuple[Candidate, Cost]: ...


def split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.split()
    return (parts[0], " ".join(parts[1:])) if parts else ("", "")
