"""The sandbox and tests: made-up people, no network, no keys. Behaviour is set per provider so
the waterfall's order, stop and cache rules can be shown and tested."""

from app.providers.contact_finders import Candidate, Cost, Search
from app.providers.contact_finders import split_name as _split

PEOPLE = [("Camille Laurent", "CTO"), ("Noah Becker", "Head of Engineering"),
          ("Lena Rossi", "Talent Acquisition Manager")]


class MockFinder:
    """`finds` = which provider ends the waterfall; the others come back empty (like a company a
    provider doesn't cover). `reveals`: Prospeo/Apollo show people first, emails need a reveal."""

    def __init__(self, provider: str, unit: str = "credits", *, finds: bool = False,
                 needs_reveal: bool = False, calls: list[str] | None = None):
        self.provider, self.unit = provider, unit
        self.finds, self.needs_reveal = finds, needs_reveal
        self.calls = calls if calls is not None else []

    def search(self, key: str, domain: str, titles: list[str], *, limit: int = 10) -> Search:
        self.calls.append(f"{self.provider}.search:{domain}")
        cost = Cost(usd=0.004) if self.unit == "usd" else Cost(
            credits=0.0 if self.provider == "apollo" else 1.0)
        if not self.finds:
            return Search([], cost)
        people = []
        for i, (name, title) in enumerate(PEOPLE):
            first, last = _split(name)
            email = f"{first}.{last}@{domain}".lower()
            people.append(Candidate(
                full_name=name, title=title, provider=self.provider, actor=(
                    "microworlds/leads-finder" if self.provider == "apify" else None),
                provider_id=f"{self.provider}-{i}|{domain}", has_email=True,
                email=None if self.needs_reveal else email,
                email_status=None if self.needs_reveal else "valid"))
        return Search(people, cost, "{first}.{last}" if self.provider == "hunter" else None)

    def reveal(self, key: str, candidate: Candidate) -> tuple[Candidate, Cost]:
        self.calls.append(f"{self.provider}.reveal:{candidate.full_name}")
        if candidate.email:
            return candidate, Cost()
        first, last = _split(candidate.full_name)
        domain = (candidate.provider_id or "|example.test").split("|", 1)[1]
        candidate.email = f"{first}.{last}@{domain}".lower()
        candidate.email_status = "valid"
        return candidate, Cost(credits=1.0)

    def verify(self, key: str, email: str) -> tuple[str, Cost]:
        self.calls.append(f"hunter.verify:{email}")
        return "valid", Cost(credits=0.5)
