"""Read-only analysis of new Apollo contact CSVs against a BACKUP COPY of the real DB.

    cd backend && .venv/bin/python -I scripts/analyze_contacts_import.py \
        --db <backup copy>.db --csv ../data/import/contacts-new --out <result>.json

No writes, no network, no model or provider calls. It refuses `data/jobhunter.db` itself and opens
the copy read-only. Output is counts plus at most 3 masked examples per file (no names, no emails).
"""

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.models import (  # noqa: E402
    Application, Company, CompanyAlias, Contact, Job, LinkedInOutreach, OutreachDraft,
)
from app.models.enums import Stage  # noqa: E402
from app.services import contacts as contacts_svc  # noqa: E402
from app.services import domains, open_jobs, views  # noqa: E402
from app.services.company_resolve import linkedin_slug  # noqa: E402
from app.services.contacts_import import (  # noqa: E402
    _EMAIL, FIELD_ALIASES, detect_mapping, map_row,
)
from app.services.dedupe import normalize_company  # noqa: E402

ROLE_LOCALS = {
    "info", "contact", "contacts", "hr", "jobs", "job", "careers", "career", "admin", "office",
    "hello", "hi", "support", "sales", "team", "recruiting", "recruitment", "recrutement",
    "rh", "bewerbung", "karriere", "kontakt", "mail", "enquiries", "enquiry", "press", "presse",
    "marketing", "service", "accueil", "secretariat", "contacto", "empleo", "rrhh", "talent",
    "noreply", "no-reply", "webmaster", "postmaster", "billing", "compta", "comptabilite",
    "direction", "reception", "hallo", "post", "bonjour", "general", "management",
}
FREE_MAIL = {
    "gmail.com", "googlemail.com", "outlook.com", "outlook.fr", "outlook.de", "hotmail.com",
    "hotmail.fr", "hotmail.de", "hotmail.es", "live.com", "live.fr", "msn.com", "yahoo.com",
    "yahoo.fr", "yahoo.de", "yahoo.es", "ymail.com", "gmx.de", "gmx.net", "gmx.com", "gmx.fr",
    "web.de", "t-online.de", "freenet.de", "orange.fr", "wanadoo.fr", "free.fr", "sfr.fr",
    "laposte.net", "icloud.com", "me.com", "aol.com", "protonmail.com", "proton.me", "mail.com",
    "bluewin.ch", "telefonica.net", "terra.es", "hotmail.it", "libero.it", "mail.ru",
}
JUNK_TITLES = {"n/a", "na", "-", "--", "none", "null", "unknown", "tbd", ".", "x", "?"}
VAGUE_WORDS = {"manager", "director", "senior", "junior", "lead", "head", "consultant",
               "specialist", "owner", "associate", "employee", "member", "staff", "professional",
               "executive", "officer", "sr", "jr", "chief", "vp", "president"}
EXTRA = {  # Apollo columns the importer ignores
    "email_status": ["email status"], "dnc": ["do not call"], "last_contacted": ["last contacted"],
    "stage": ["stage"], "employees": ["# employees"], "country": ["country", "company country"],
    "seniority": ["seniority"], "departments": ["departments"], "city": ["city"],
    "company_linkedin": ["company linkedin url"],
}


def col_for(headers: list[str], names: list[str]) -> str | None:
    lower = {h.lower().strip(): h for h in headers}
    return next((lower[n] for n in names if n in lower), None)


def parse(raw: bytes) -> tuple[list[str], list[dict[str, str]], dict[str, object]]:
    """Same parsing as contacts_import.parse_csv, plus the facts it hides."""
    try:
        raw.decode("utf-8")
        enc = "utf-8" + ("-sig" if raw.startswith(b"\xef\xbb\xbf") else "")
        bad = 0
    except UnicodeDecodeError:
        enc = "NOT utf-8"
        bad = raw.decode("utf-8", errors="replace").count("�")
    text = raw.decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = [h for h in (reader.fieldnames or []) if h is not None]
    rows = [{k: (v or "").strip() for k, v in r.items() if k is not None} for r in reader]
    return headers, rows, {"encoding": enc, "replacement_chars": bad,
                           "delimiter": {",": "comma", ";": "semicolon", "\t": "tab"}.get(
                               dialect.delimiter, repr(dialect.delimiter))}


def mask(email: str) -> str:
    local, _, dom = email.partition("@")
    return f"{local[:1]}***@{dom[:1]}***.{dom.rsplit('.', 1)[-1]}" if dom else "***"


def title_quality(title: str | None) -> str:
    t = (title or "").strip().lower()
    if not t:
        return "empty"
    if t in JUNK_TITLES or not re.search(r"[a-z]{2}", t) or len(t) < 3:
        return "junk"
    words = re.findall(r"[a-z]+", t)
    if words and all(w in VAGUE_WORDS for w in words):
        return "vague"
    return "ok"


def parse_emp(v: str) -> int | None:
    v = v.replace(",", "").strip()
    return int(v) if v.isdigit() else None


def fuzzy_pairs(new_names: list[str], existing: list[str]) -> list[tuple[str, str, float]]:
    """Near names (ratio >= 0.9, not equal), blocked on the first word to stay fast."""
    block: dict[str, list[str]] = defaultdict(list)
    for e in existing:
        block[e.split(" ")[0][:4]].append(e)
    out = []
    for n in new_names:
        for e in block.get(n.split(" ")[0][:4], []):
            if e != n and abs(len(e) - len(n)) <= 4 and len(n) >= 5:
                r = SequenceMatcher(None, n, e).ratio()
                if r >= 0.9:
                    out.append((n, e, r))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    db = Path(a.db).resolve()
    if db.name == "jobhunter.db" or "analysis_copy" not in db.name:
        sys.exit("Refusing: pass the backup copy (analysis_copy*.db), never the real DB.")
    engine = create_engine(f"sqlite:///file:{db}?mode=ro&uri=true")
    s = Session(engine)

    # ------------------------------------------------------------- existing data (copy)
    comps = {c.id: c for c in s.exec(select(Company)).all()}
    comp_by_norm = {c.normalized_name: c.id for c in comps.values()}
    for al in s.exec(select(CompanyAlias)).all():
        comp_by_norm.setdefault(al.normalized_name, al.company_id)
    comp_domains: dict[str, set[int]] = defaultdict(set)
    comp_li: dict[str, int] = {}
    for c in comps.values():
        for d in {domains.clean_domain(c.domain), domains.clean_domain(c.email_domain),
                  *[domains.clean_domain(x.get("domain") if isinstance(x, dict) else x)
                    for x in (c.domains or [])]}:
            if d:
                comp_domains[d].add(c.id)
        if linkedin_slug(c.linkedin_url):
            comp_li[linkedin_slug(c.linkedin_url)] = c.id
    ex = s.exec(select(Contact)).all()
    by_email = {c.email_normalized: c for c in ex if c.email_normalized}
    by_li = {linkedin_slug(c.linkedin_url) or (c.linkedin_url or "").lower().rstrip("/"): c
             for c in ex if c.linkedin_url}
    by_name = {(c.company_id, c.normalized_name): c for c in ex if c.normalized_name}
    drafted = {d.contact_id for d in s.exec(select(OutreachDraft)).all() if d.contact_id}
    drafted |= {x.contact_id for x in s.exec(select(LinkedInOutreach)).all() if x.contact_id}
    sent_to: set[str] = set()
    from sqlalchemy import text
    for (to,) in s.connection().execute(text("select \"to\" from send_log")).all():
        sent_to |= {m.lower() for m in re.findall(r"[\w.+-]+@[\w.-]+\.\w+", to or "")}
    for (cid,) in s.connection().execute(text(
            "select distinct d.contact_id from send_log l join outreach_draft d on d.id=l.draft_id "
            "where d.contact_id is not null")).all():
        drafted.add(cid)
    ranking = contacts_svc.ranking_settings(s)
    group_labels = [g.get("label") for g in ranking.groups]

    # ------------------------------------------------------------------ open jobs (copy)
    open_set = open_jobs.open_ids(s)
    jobs = {j.id: j for j in s.exec(select(Job)).all() if j.id in open_set}
    apps = {ap_.job_id: ap_ for ap_ in s.exec(select(Application)).all() if ap_.job_id in jobs}
    apps = {k: v for k, v in apps.items() if v.stage != Stage.closed}
    fits = views.latest_fits(s, list(apps))
    jobs_by_company: dict[int, list[int]] = defaultdict(list)
    for jid in apps:
        jobs_by_company[jobs[jid].company_id].append(jid)

    # --------------------------------------------------------------------------- files
    files = sorted(Path(a.csv).glob("*.csv"), key=lambda p: (not p.name.startswith("new"), p.name))
    seen_email: dict[str, str] = {}
    seen_li: dict[str, str] = {}
    seen_name: dict[tuple[str, str], str] = {}
    per_file: dict[str, dict] = {}
    new_contacts: list[dict] = []  # internal: new, valid, unique, not excluded
    person_only: list[dict] = []
    matches: Counter = Counter()
    conflicts_examples: list[dict] = []
    company_rows: dict[str, dict] = {}  # norm -> info

    for f in files:
        raw = f.read_bytes()
        headers, rows, facts = parse(raw)
        mapping = detect_mapping(headers)
        extra = {k: col_for(headers, v) for k, v in EXTRA.items()}
        mapped_cols = {v for v in mapping.values() if v} | {v for v in extra.values() if v}
        unmapped = [h for h in headers if h not in mapped_cols]
        # Which Apollo columns hold the person's name parts, in addition to the mapping.
        st = Counter()
        fn = f.name
        info = {"file": fn, "rows": len(rows), **facts, "columns": len(headers),
                "mapped": {k: v for k, v in mapping.items() if v},
                "unmapped_importer_fields": [k for k, v in mapping.items() if not v],
                "extra_mapped": {k: v for k, v in extra.items() if v},
                "unmapped_columns": unmapped, "examples": []}
        stages = Counter()
        for row in rows:
            r = map_row(row, mapping)
            if isinstance(r, str):
                st[r] += 1
                st["unmappable"] += 1
                continue
            st["mappable"] += 1
            email_raw = " ".join((row.get(mapping["email"] or "") or "").split()).lower()
            local, _, dom = email_raw.partition("@")
            if not email_raw:
                es = "no_email"
            elif not _EMAIL.match(email_raw):
                es = "invalid_email"
            elif local in ROLE_LOCALS:
                es = "role_based"
            elif dom in FREE_MAIL:
                es = "free_mail"
            else:
                es = "ok"
            status = (row.get(extra["email_status"] or "") or "").strip().lower()
            if es == "ok" and status in {"invalid", "do_not_mail", "do not mail"}:
                es = "apollo_invalid"  # Apollo itself says the address is bad / do not mail
            st[es] += 1
            if es == "ok" and status and status != "verified":
                st[f"apollo_status_{status}"] += 1
            tq = title_quality(r.title)
            st[f"title_{tq}"] += 1
            dnc = (row.get(extra["dnc"] or "") or "").strip().lower() in {"true", "yes", "1"}
            lastc = bool((row.get(extra["last_contacted"] or "") or "").strip())
            stg = (row.get(extra["stage"] or "") or "").strip()
            stages[stg or "(empty)"] += 1
            st["do_not_call"] += dnc
            st["last_contacted_set"] += lastc
            cn = normalize_company(r.company)
            nn = contacts_svc.normalize_person(r.full_name)
            li = linkedin_slug(r.linkedin_url) or (r.linkedin_url or "").lower().rstrip("/")
            comp_domain = domains.clean_domain(r.domain)
            emp = parse_emp(row.get(extra["employees"] or "") or "")
            country = (row.get(extra["country"] or "") or "").strip()
            ci = company_rows.setdefault(cn, {"name": r.company, "domains": Counter(),
                                              "li": None, "contacts": 0, "files": set()})
            ci["contacts"] += 1
            ci["files"].add(fn)
            if comp_domain:
                ci["domains"][comp_domain] += 1
            ci["li"] = ci["li"] or linkedin_slug(row.get(extra["company_linkedin"] or "") or "")
            ci["emp"] = ci.get("emp") or emp
            if len(info["examples"]) < 3 and es == "ok":
                info["examples"].append(mask(email_raw))

            # --- duplicates (new files first, then old; the first file to carry a person wins)
            prior = (seen_email.get(email_raw) if email_raw else None)
            kind = "email"
            if prior is None and li and li in seen_li:
                prior, kind = seen_li[li], "linkedin"
            if prior is None and (cn, nn) in seen_name:
                prior, kind = seen_name[(cn, nn)], "name"
            if prior is not None:
                same = prior == fn
                st["dup_within_file" if same else "dup_across_files"] += 1
                if kind != "email" and email_raw and email_raw not in seen_email:
                    st["same_person_other_email_in_new_files"] += 1
                continue
            if email_raw:
                seen_email[email_raw] = fn
            if li:
                seen_li[li] = fn
            seen_name[(cn, nn)] = fn
            st["unique"] += 1
            if es == "ok":
                st["unique_valid_email"] += 1

            # --- match against the copy
            company_id = comp_by_norm.get(cn)
            hit = None
            how = ""
            if email_raw and email_raw in by_email:
                hit, how = by_email[email_raw], "email"
            elif li and li in by_li:
                hit, how = by_li[li], "linkedin"
            elif company_id is not None and (company_id, nn) in by_name:
                hit, how = by_name[(company_id, nn)], "company+name"
            if hit is not None:
                st["match_existing"] += 1
                st[f"match_by_{how}"] += 1
                tag = "identical"
                if (hit.email_normalized and email_raw and hit.email_normalized != email_raw
                        and es != "no_email"):
                    tag = "conflict_email"
                elif company_id is not None and hit.company_id != company_id:
                    tag = "newer_company"
                elif r.title and (hit.title or "").strip().lower() != r.title.strip().lower():
                    tag = "newer_title" if not hit.title else "different_title"
                matches[tag] += 1
                st[f"match_{tag}"] += 1
                if hit.left_at:
                    st["excluded_left"] += 1
                if hit.verified_at or (hit.notes or "").strip():
                    st["match_verified_or_edited"] += 1
                if hit.id in drafted or (hit.email_normalized or "") in sent_to:
                    st["excluded_emailed"] += 1
                continue
            if email_raw and email_raw in sent_to:
                st["excluded_emailed"] += 1
                st["emailed_but_no_contact_row"] += 1
                continue
            if dnc:
                st["excluded_do_not_call"] += 1
                continue
            rec = {"file": fn, "title": r.title, "tq": tq, "company_norm": cn, "company": r.company,
                   "company_id": company_id, "country": country, "emp": emp, "email_state": es,
                   "domain": comp_domain, "last_contacted": lastc}
            if es == "ok":
                st["new_valid"] += 1
                new_contacts.append(rec)
            else:
                st["new_person_no_usable_email"] += 1
                person_only.append(rec)
        info["counts"] = dict(st)
        info["apollo_stage"] = dict(stages.most_common(6))
        per_file[fn] = info

    # ------------------------------------------------------------------- companies
    new_norms = [n for n in company_rows if n not in comp_by_norm]
    existing_norms = [n for n in company_rows if n in comp_by_norm]
    ambiguous: list[dict] = []
    for n in existing_norms:  # same name, different domain
        ci = company_rows[n]
        c = comps[comp_by_norm[n]]
        known = {d for d, ids in comp_domains.items() if c.id in ids}
        top = ci["domains"].most_common(1)
        if top and known and top[0][0] not in known:
            ambiguous.append({"kind": "same_name_different_domain", "csv": ci["name"],
                              "db": c.name, "csv_domain": top[0][0],
                              "db_domain": sorted(known)[0], "contacts": ci["contacts"]})
    amb_names = set()
    for n in new_norms:  # new name that collides by domain or LinkedIn page
        ci = company_rows[n]
        top = ci["domains"].most_common(1)
        if top and top[0][0] in comp_domains:
            ids = comp_domains[top[0][0]]
            ambiguous.append({"kind": "new_name_known_domain", "csv": ci["name"],
                              "db": comps[next(iter(ids))].name, "csv_domain": top[0][0],
                              "contacts": ci["contacts"]})
            amb_names.add(n)
        elif ci["li"] and ci["li"] in comp_li:
            ambiguous.append({"kind": "new_name_known_linkedin_page", "csv": ci["name"],
                              "db": comps[comp_li[ci["li"]]].name, "contacts": ci["contacts"]})
            amb_names.add(n)
    for n, e, ratio in fuzzy_pairs([x for x in new_norms if x not in amb_names],
                                   list(comp_by_norm)):
        ambiguous.append({"kind": "similar_name", "csv": company_rows[n]["name"],
                          "db": comps[comp_by_norm[e]].name, "ratio": round(ratio, 2),
                          "contacts": company_rows[n]["contacts"]})
        amb_names.add(n)
    # PDL (local parquet, no network): does a new company's domain agree with PDL's?
    pdl = {"checked": 0, "has_pdl": 0, "domain_agrees": 0, "domain_disagrees": 0}
    pdl_path = Path(__file__).resolve().parents[2] / "data" / "pdl" / "companies.parquet"
    if pdl_path.exists() and new_norms:
        import duckdb
        con = duckdb.connect()
        con.execute("create table n(k varchar)")
        con.executemany("insert into n values (?)", [(k,) for k in new_norms])
        got: dict[str, set[str]] = defaultdict(set)
        for k, w in con.execute("select p.name_key, p.website from read_parquet(?) p "
                                "join n on n.k = p.name_key", [str(pdl_path)]).fetchall():
            d = domains.clean_domain(w)
            if d:
                got[k].add(d)
        con.close()
        pdl["checked"] = len(new_norms)
        for k in new_norms:
            if k in got:
                pdl["has_pdl"] += 1
                top = company_rows[k]["domains"].most_common(1)
                if top and top[0][0] in got[k]:
                    pdl["domain_agrees"] += 1
                elif top:
                    pdl["domain_disagrees"] += 1
    amb_by_kind = Counter(x["kind"] for x in ambiguous)

    # ------------------------------------------------------------ value for open jobs
    def usable(rec: dict) -> bool:
        return rec["company_id"] is not None and rec["company_norm"] not in amb_names

    at_open = [r for r in new_contacts if r["company_id"] in jobs_by_company]
    comp_new: dict[int, list[dict]] = defaultdict(list)
    for r in at_open:
        comp_new[r["company_id"]].append(r)

    def best_for(company_id: int, job: Job, cands: list[dict]) -> tuple[dict, int, str | None]:
        order = ranking.order_for(comps[company_id], job)
        scored = []
        for r in cands:
            g = contacts_svc.rank(r["title"], ranking.groups)[0]
            pos = order.index(g) if g in order else contacts_svc.UNRANKED
            scored.append((pos, g, r))
        pos, g, r = min(scored, key=lambda x: x[0])
        return r, pos, ranking.label(g)

    stage_new = Stage.new
    gain = []
    for cid, cands in comp_new.items():
        for jid in jobs_by_company[cid]:
            app = apps[jid]
            if app.contact_id is not None:
                continue
            job = jobs[jid]
            r, pos, label = best_for(cid, job, cands)
            fit = fits.get(jid)
            score = fit.score if fit is not None and fit.score is not None and \
                fit.prompt_version and fit.status == "ok" else None
            gain.append({"job": jid, "title": job.title, "company": comps[cid].name,
                         "track": job.matched_track or "(none)", "country": job.country or "(remote)",
                         "stage": str(app.stage), "fit": score,
                         "contact_title": r["title"] or "(no title)", "label": label,
                         "rank_pos": pos,
                         "size": contacts_svc.size_label(comps[cid]),
                         "small": contacts_svc.is_small(comps[cid], ranking.threshold)})
    gain_total = len(gain)
    gain_past_new = [g for g in gain if g["stage"] != str(stage_new)]
    top30 = sorted((g for g in gain if g["fit"] is not None), key=lambda g: (-g["fit"], g["rank_pos"]))[:30]
    for g in top30:
        who = g["label"] or "unranked title"
        g["why"] = (f"{who}; {'small' if g['small'] else 'large/unknown-size'} company "
                    f"({g['size']}) -> position {g['rank_pos'] + 1}" if g["rank_pos"] < 999
                    else f"{who}; not in the ranking order")

    def tally(items: list[dict], key: str) -> list[dict]:
        c = Counter(i[key] for i in items)
        return [{"group": k, "jobs": v} for k, v in c.most_common()]

    labels_count = Counter()
    for r in at_open:
        g = contacts_svc.rank(r["title"], ranking.groups)[0]
        labels_count[ranking.label(g) or "(unranked)"] += 1
    open_with_contact = sum(1 for a_ in apps.values() if a_.contact_id is not None)
    open_total = len(apps)
    cur = contacts_svc.report(s)

    totals = Counter()
    for pf in per_file.values():
        totals.update({k: v for k, v in pf["counts"].items() if isinstance(v, int)})
    totals["rows"] = sum(pf["rows"] for pf in per_file.values())
    tq_new = Counter(r["tq"] for r in new_contacts)
    result = {
        "files": per_file,
        "totals": dict(totals),
        "matches_vs_existing": dict(matches),
        "companies": {
            "distinct_in_csv": len(company_rows), "existing": len(existing_norms),
            "new": len(new_norms), "ambiguous_total": len(ambiguous),
            "ambiguous_by_kind": dict(amb_by_kind), "pdl_check_on_new": pdl,
            "ambiguous_examples": ambiguous[:40],
        },
        "new_valid_contacts": len(new_contacts),
        "new_person_no_usable_email": len(person_only),
        "new_by_company_state": {
            "company_exists": sum(1 for r in new_contacts if r["company_id"] is not None),
            "company_new": sum(1 for r in new_contacts if r["company_id"] is None),
            "company_ambiguous": sum(1 for r in new_contacts if r["company_norm"] in amb_names),
        },
        "title_quality_new": dict(tq_new),
        "new_valid_by_country": dict(Counter(r["country"] or "(empty)"
                                             for r in new_contacts).most_common(12)),
        "new_valid_last_contacted_in_apollo": sum(1 for r in new_contacts if r["last_contacted"]),
        "new_valid_by_file": dict(Counter(r["file"] for r in new_contacts)),
        "new_valid_by_size": dict(Counter(
            "unknown" if r["emp"] is None else "<200" if r["emp"] < 200 else ">=200"
            for r in new_contacts)),
        "open_jobs": {"open_applications": open_total, "with_contact": open_with_contact,
                      "current_report": cur["totals"],
                      "by_track": cur["by_track"], "by_country": cur["by_country"]},
        "value": {
            "new_contacts_at_open_job_companies": len(at_open),
            "new_contacts_at_open_job_companies_unambiguous": sum(1 for r in at_open if usable(r)),
            "companies_with_open_jobs_gaining_contacts": len(comp_new),
            "open_jobs_gaining_first_contact": gain_total,
            "of_which_past_new_stage": len(gain_past_new),
            "gain_by_track": tally(gain, "track"), "gain_by_country": tally(gain, "country"),
            "gain_past_new_by_track": tally(gain_past_new, "track"),
            "gain_past_new_by_country": tally(gain_past_new, "country"),
            "new_contacts_by_role_group": dict(labels_count),
            "role_groups_in_order": group_labels,
            "top30": top30,
        },
        "existing": {"contacts": len(ex), "left": sum(1 for c in ex if c.left_at),
                     "verified": sum(1 for c in ex if c.verified_at),
                     "with_notes": sum(1 for c in ex if (c.notes or "").strip()),
                     "drafted_or_sent_contacts": len(drafted), "sent_to_addresses": len(sent_to)},
    }
    Path(a.out).write_text(json.dumps(result, indent=1, default=str))
    print(json.dumps({"totals": result["totals"], "new_valid": len(new_contacts),
                      "gain": gain_total}, default=str))


if __name__ == "__main__":
    main()
