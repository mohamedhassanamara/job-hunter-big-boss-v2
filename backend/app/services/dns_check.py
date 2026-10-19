"""Does a domain receive email? A free MX lookup (DNS only: no mail is sent, no provider is
called, no credit is spent). Run before any provider is paid for a domain."""

from collections.abc import Callable

import dns.exception
import dns.name
import dns.resolver

Lookup = Callable[[str], "list[str] | None"]


def lookup_mx(domain: str, timeout: float = 3.0) -> list[str] | None:
    """The domain's MX hosts, best first; [] when it has none (or doesn't exist, or publishes a
    null MX); None when DNS couldn't answer (timeout, no network): unknown, not a "no"."""
    resolver = dns.resolver.Resolver()
    resolver.lifetime = timeout
    try:
        answer = resolver.resolve(domain, "MX")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.name.EmptyLabel):
        return []
    except (dns.exception.DNSException, OSError):  # timeout, SERVFAIL, no network: unknown
        return None
    hosts = sorted(answer, key=lambda r: r.preference)
    names = [str(r.exchange).rstrip(".").lower() for r in hosts]
    return [n for n in names if n]  # a null MX ("." exchange) leaves nothing: no mail


def has_mx(domain: str, lookup: Lookup | None = None) -> bool | None:
    hosts = (lookup or lookup_mx)(domain)
    return None if hosts is None else bool(hosts)
