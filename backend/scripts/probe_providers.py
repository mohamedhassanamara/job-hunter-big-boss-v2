"""Manual probe of the contact providers (makes REAL requests; paid stages spend credits).

    .venv/bin/python scripts/probe_providers.py free    # account/credit endpoints, Apify limits + Actor schemas
    .venv/bin/python scripts/probe_providers.py paid    # one minimal paid call per endpoint per key

Keys come from .env (never printed: they are labelled hunter#1, prospeo#2, ...). Results go to
the path in $PROBE_OUT (default: stdout only).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import httpx

from app.config import get_settings

ACTORS = [
    "code_crafter/leads-finder",
    "peakydev/leads-scraper-ppe",
    "boneswill/leads-generator",
    "microworlds/leads-finder",
]


def keys(raw: str) -> list[str]:
    return [k.strip() for k in raw.split(",") if k.strip()]


def call(method: str, url: str, **kw: Any) -> dict[str, Any]:
    try:
        r = httpx.request(method, url, timeout=60, **kw)
    except httpx.HTTPError as e:
        return {"status": None, "error": type(e).__name__}
    try:
        body: Any = r.json()
    except ValueError:
        body = r.text[:300]
    return {"status": r.status_code, "body": body}


def show(label: str, res: dict[str, Any], limit: int = 900) -> None:
    text = json.dumps(res, ensure_ascii=False, default=str)
    print(f"## {label}\n{text[:limit]}{' …' if len(text) > limit else ''}\n")


def hunter_account(k: str) -> dict[str, Any]:
    return call("GET", "https://api.hunter.io/v2/account", params={"api_key": k})


def prospeo_account(k: str) -> dict[str, Any]:
    return call("GET", "https://api.prospeo.io/account-information", headers={"X-KEY": k})


def apollo_headers(k: str) -> dict[str, str]:
    return {"x-api-key": k, "Content-Type": "application/json", "Cache-Control": "no-cache"}


def free() -> None:
    s = get_settings()
    for i, k in enumerate(keys(s.hunter_api_keys), 1):
        show(f"hunter#{i} account", hunter_account(k), 1500)
    for i, k in enumerate(keys(s.prospeo_api_keys), 1):
        show(f"prospeo#{i} account", prospeo_account(k), 1500)
    for i, k in enumerate(keys(s.apollo_api_keys), 1):
        show(f"apollo#{i} health", call("GET", "https://api.apollo.io/api/v1/auth/health",
                                        headers=apollo_headers(k)))
    tok = {"Authorization": f"Bearer {s.apify_token}"}
    lim = call("GET", "https://api.apify.com/v2/users/me/limits", headers=tok)
    if lim.get("status") == 200:
        d = lim["body"]["data"]
        lim["body"] = {"cycle": d["monthlyUsageCycle"],
                       "maxMonthlyUsageUsd": d["limits"].get("maxMonthlyUsageUsd"),
                       "monthlyUsageUsd": d["current"].get("monthlyUsageUsd")}
    show("apify limits", lim, 800)
    for a in ACTORS:
        act = call("GET", f"https://api.apify.com/v2/acts/{a.replace('/', '~')}", headers=tok)
        if act.get("status") != 200:
            show(f"actor {a}", act, 300)
            continue
        d = act["body"]["data"]
        build = call("GET", f"https://api.apify.com/v2/acts/{a.replace('/', '~')}/builds/default",
                     headers=tok)
        schema = (build.get("body") or {}).get("data", {}).get("inputSchema") if build.get(
            "status") == 200 else None
        info = {"pricing": d.get("pricingInfos", [])[-1:] or d.get("pricingInfo"),
                "stats": {k: d.get("stats", {}).get(k) for k in
                          ("totalUsers30Days", "totalRuns")},
                "modified": d.get("modifiedAt"), "inputSchema": schema}
        show(f"actor {a}", {"status": 200, "body": info}, 3500)


TITLES = ["CTO", "VP Engineering", "Head of Data", "Head of Engineering", "Engineering Manager"]
# one different company per key/Actor, so no credits are spent twice on the same company
HUNTER_DOMAIN = "sekoia.io"
PROSPEO_DOMAINS = ["elevenlabs.io", "matera.com"]
APOLLO_DOMAINS = ["checkout.com", "inthepocket.com"]
APIFY_RUNS = [  # (actor, company domain, input builder, max charge USD)
    ("code_crafter/leads-finder", "satispay.com", lambda d: {
        "fetch_count": 3, "company_domain": [d], "contact_job_title": TITLES,
        "email_status": ["validated"]}, 0.10),
    ("microworlds/leads-finder", "grafana.com", lambda d: {
        "max_result": 3, "company_domains": [d], "contact_job_titles": TITLES,
        "email_status": ["verified"]}, 0.10),
    ("peakydev/leads-scraper-ppe", "aboutyou.com", lambda d: {
        "totalResults": 100, "companyDomain": [d], "personTitle": TITLES}, 0.30),
    ("boneswill/leads-generator", "trimble.com", lambda d: {
        "totalResults": 100, "companyDomain": [d], "personTitle": TITLES}, 0.30),
]


def credits_hunter(k: str) -> Any:
    b = hunter_account(k).get("body", {}).get("data", {}).get("requests", {})
    return {n: b.get(n, {}).get("used") for n in ("credits", "searches", "verifications")}


def credits_prospeo(k: str) -> Any:
    return prospeo_account(k).get("body", {}).get("response", {}).get("remaining_credits")


def paid() -> None:
    s = get_settings()
    # Hunter: domain search (limit 3) -> email finder on its first person -> verifier on that email
    hk = keys(s.hunter_api_keys)[0]
    before = credits_hunter(hk)
    ds = call("GET", "https://api.hunter.io/v2/domain-search", params={
        "api_key": hk, "domain": HUNTER_DOMAIN, "limit": 3, "department": "it,executive,management"})
    d = ds.get("body", {}).get("data", {}) if isinstance(ds.get("body"), dict) else {}
    show("hunter#1 domain-search " + HUNTER_DOMAIN, {
        "status": ds["status"], "pattern": d.get("pattern"), "organization": d.get("organization"),
        "emails": [{k: e.get(k) for k in ("value", "type", "confidence", "first_name", "last_name",
                    "position", "department")} | {"verif": (e.get("verification") or {}).get("status")}
                   for e in d.get("emails", [])],
        "errors": ds.get("body", {}).get("errors") if isinstance(ds.get("body"), dict) else None}, 2500)
    after_ds = credits_hunter(hk)
    print("hunter credits before/after domain-search:", before, after_ds, "\n")
    people = [e for e in d.get("emails", []) if e.get("first_name") and e.get("last_name")]
    if people:
        p0 = people[0]
        ef = call("GET", "https://api.hunter.io/v2/email-finder", params={
            "api_key": hk, "domain": HUNTER_DOMAIN, "first_name": p0["first_name"],
            "last_name": p0["last_name"]})
        ed = ef.get("body", {}).get("data", {}) if isinstance(ef.get("body"), dict) else {}
        show("hunter#1 email-finder", {"status": ef["status"], "email": ed.get("email"),
                                       "score": ed.get("score"), "errors": ef.get("body", {}).get(
                                           "errors") if isinstance(ef.get("body"), dict) else None})
        after_ef = credits_hunter(hk)
        print("hunter credits after email-finder:", after_ef, "\n")
        vv = call("GET", "https://api.hunter.io/v2/email-verifier", params={
            "api_key": hk, "email": p0["value"]})
        vd = vv.get("body", {}).get("data", {}) if isinstance(vv.get("body"), dict) else {}
        show("hunter#1 email-verifier", {"status": vv["status"], "result": vd.get("result"),
                                         "verification_status": vd.get("status"),
                                         "score": vd.get("score")})
        print("hunter credits after verifier:", credits_hunter(hk), "\n")

    # Prospeo: search-person at the domain, then enrich-person (verified only) on its first result
    for i, (k, dom) in enumerate(zip(keys(s.prospeo_api_keys), PROSPEO_DOMAINS), 1):
        h = {"X-KEY": k, "Content-Type": "application/json"}
        b0 = credits_prospeo(k)
        sr = call("POST", "https://api.prospeo.io/search-person", headers=h, json={
            "page": 1, "filters": {"company": {"websites": {"include": [dom]}},
                                   "person_job_title": {"include": TITLES, "match_mode": "CONTAINS"}}})
        body = sr.get("body") if isinstance(sr.get("body"), dict) else {}
        res = body.get("results", []) or []
        show(f"prospeo#{i} search-person {dom}", {
            "status": sr["status"], "error": body.get("error_code") or body.get("error"),
            "free": body.get("free"), "total": (body.get("pagination") or {}).get("total_count"),
            "people": [{"id": (r.get("person") or {}).get("person_id"),
                        "name": (r.get("person") or {}).get("full_name"),
                        "title": (r.get("person") or {}).get("current_job_title"),
                        "email": (r.get("person") or {}).get("email")} for r in res[:3]]}, 2000)
        print(f"prospeo#{i} credits before/after search:", b0, credits_prospeo(k), "\n")
        if res and (res[0].get("person") or {}).get("person_id"):
            en = call("POST", "https://api.prospeo.io/enrich-person", headers=h, json={
                "only_verified_email": True,
                "data": {"person_id": res[0]["person"]["person_id"]}})
            eb = en.get("body") if isinstance(en.get("body"), dict) else {}
            person = eb.get("person") or {}
            show(f"prospeo#{i} enrich-person", {
                "status": en["status"], "error": eb.get("error_code"),
                "email": person.get("email"), "free": eb.get("free_enrichment")})
            print(f"prospeo#{i} credits after enrich:", credits_prospeo(k), "\n")

    # Apollo: free people search (no emails), then one match (reveals the work email, ~1 credit)
    for i, (k, dom) in enumerate(zip(keys(s.apollo_api_keys), APOLLO_DOMAINS), 1):
        sr = call("POST", "https://api.apollo.io/api/v1/mixed_people/api_search",
                  headers=apollo_headers(k), json={
                      "q_organization_domains_list": [dom], "person_titles": TITLES, "per_page": 3})
        body = sr.get("body") if isinstance(sr.get("body"), dict) else {"raw": sr.get("body")}
        people = body.get("people", []) or []
        show(f"apollo#{i} api_search {dom}", {
            "status": sr["status"], "total": (body.get("pagination") or {}).get("total_entries")
            or body.get("total_entries"), "error": body.get("error") or body.get("raw"),
            "people": [{"id": x.get("id"), "name": x.get("first_name"), "title": x.get("title"),
                        "has_email": x.get("has_email")} for x in people[:3]]}, 1500)
        if people:
            m = call("POST", "https://api.apollo.io/api/v1/people/match", headers=apollo_headers(k),
                     params={"id": people[0]["id"]})
            mb = m.get("body") if isinstance(m.get("body"), dict) else {}
            person = mb.get("person") or {}
            show(f"apollo#{i} people/match", {
                "status": m["status"], "email": person.get("email"),
                "email_status": person.get("email_status"), "title": person.get("title"),
                "error": mb.get("error")})

    # Apify: one capped run per Actor, 3 leads (100 where the Actor's minimum forces it)
    tok = {"Authorization": f"Bearer {s.apify_token}"}
    lim0 = call("GET", "https://api.apify.com/v2/users/me/limits", headers=tok)["body"]["data"]
    last = lim0["current"]["monthlyUsageUsd"]
    for actor, dom, build, cap in APIFY_RUNS:
        r = call("POST", f"https://api.apify.com/v2/acts/{actor.replace('/', '~')}/run-sync-get-dataset-items",
                 headers=tok, params={"maxTotalChargeUsd": cap, "timeout": 240},
                 json=build(dom))
        items = r.get("body") if isinstance(r.get("body"), list) else []
        keep = ("full_name", "name", "first_name", "last_name", "job_title", "title", "email",
                "email_status", "emailStatus", "personal_email", "company_name", "linkedin")
        slim = [{k: v for k, v in it.items() if k in keep or "email" in k.lower()
                 or "title" in k.lower()} for it in items[:3]]
        show(f"apify {actor} @ {dom}", {"status": r["status"], "n": len(items), "items": slim,
                                        "error": None if items else str(r.get("body"))[:300]}, 2500)
        now = call("GET", "https://api.apify.com/v2/users/me/limits", headers=tok)["body"]["data"]
        cur = now["current"]["monthlyUsageUsd"]
        print(f"apify spend for this run: ${cur - last:.4f} (month total ${cur:.4f}/5)\n")
        last = cur


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "free"
    if stage == "free":
        free()
    else:
        paid()
    _ = os.environ.get("PROBE_OUT")
