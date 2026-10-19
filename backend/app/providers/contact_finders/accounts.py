"""The providers' free account endpoints (no credit used): the real limits and usage, for the
quota layer and the Settings screen. Apollo has none on free plans."""

import httpx

from app.providers.contact_finders import classify
from app.providers.http import PoliteClient, SourceError


def _get(name: str, url: str, headers: dict[str, str], params: dict | None = None,
         transport: httpx.BaseTransport | None = None) -> dict:
    client = PoliteClient(name, retries=0, min_interval=0.3, headers=headers, transport=transport)
    try:
        return client.get_json(url, params=params or {})
    except SourceError as exc:
        raise classify(exc) from exc
    finally:
        client.close()


def hunter(key: str, transport: httpx.BaseTransport | None = None) -> tuple[float, float]:
    d = _get("Hunter", "https://api.hunter.io/v2/account", {"X-API-KEY": key},
             transport=transport).get("data") or {}
    c = (d.get("requests") or {}).get("credits") or {}
    return float(c.get("available") or 0), float(c.get("used") or 0)


def prospeo(key: str, transport: httpx.BaseTransport | None = None) -> tuple[float, float]:
    r = _get("Prospeo", "https://api.prospeo.io/account-information", {"X-KEY": key},
             transport=transport).get("response") or {}
    used, left = float(r.get("used_credits") or 0), float(r.get("remaining_credits") or 0)
    return used + left, used


def apify(key: str, transport: httpx.BaseTransport | None = None) -> tuple[float, float]:
    d = _get("Apify", "https://api.apify.com/v2/users/me/limits",
             {"Authorization": f"Bearer {key}"}, transport=transport).get("data") or {}
    return (float((d.get("limits") or {}).get("maxMonthlyUsageUsd") or 0),
            float((d.get("current") or {}).get("monthlyUsageUsd") or 0))
