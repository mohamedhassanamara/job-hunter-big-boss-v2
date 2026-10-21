# ruff: noqa: E501
"""Compare Gemini models with the approved Claude output for CV and email GENERATION.

Runs the production code (prompts, request builders, checks, fit loop, PDF compile, Claude claim
verifier) with only the generator swapped. Nothing touches the real workspace: the real DB is
copied (sqlite online backup) into a temp dir and every write (versions, drafts, events, PDFs)
goes there. No approval is touched and no setting or default model changes.

    .venv/bin/python scripts/cv_email_model_test.py --app 1622 --out ../docs/reports/raw/<dir>
    .venv/bin/python scripts/cv_email_model_test.py --keys-only

The user's phone, email and links are never sent: the request builders don't include them, and
`GeminiRunner` refuses to send a message that contains any of them (checked on every call).
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parents[2]
SCRATCH = Path(tempfile.mkdtemp(prefix="jh-model-test-"))
REAL_DB = REPO / "data" / "jobhunter.db"


def make_scratch_db() -> Path:
    path = SCRATCH / "scratch.db"
    src = sqlite3.connect(f"file:{REAL_DB}?mode=ro", uri=True)
    dst = sqlite3.connect(path)
    src.backup(dst)
    src.close()
    dst.close()
    return path


if "--keys-only" not in sys.argv:
    os.environ["DATABASE_URL"] = f"sqlite:///{make_scratch_db()}"
    os.environ["SEND_WORKER_ENABLED"] = "false"

from sqlmodel import Session, select  # noqa: E402

from app.db import engine  # noqa: E402
from app.models import Application, CVVersion, Job, OutreachDraft  # noqa: E402
from app.providers.base import CVGenerationFailed, CVPlanDraft  # noqa: E402
from app.providers.claude_cv import ClaudeCVGenerator, plan_schema  # noqa: E402
from app.providers.claude_email import ClaudeEmailDrafter  # noqa: E402
from app.providers.ollama import strip_fence  # noqa: E402
from app.services.gemini_keys import configured_keys, fingerprint  # noqa: E402

BASE = "https://generativelanguage.googleapis.com/v1beta"
BACKOFF = (5, 10, 20, 40, 60, 60, 60, 60)  # 429/503: seconds before the next try
NUMBER = re.compile(r"\d+(?:[.,]\d+)?\s?(?:%|k|K|M|x|\+)?")

CONFIGS = [
    {"name": "gemini-3.5-flash-lite__no-thinking", "model": "gemini-3.5-flash-lite",
     "thinking": {"thinkingLevel": "minimal"}},
    {"name": "gemini-3.5-flash-lite__dynamic-thinking", "model": "gemini-3.5-flash-lite",
     "thinking": {"thinkingBudget": -1}},
    {"name": "gemini-3.1-flash-lite__no-thinking", "model": "gemini-3.1-flash-lite",
     "thinking": {"thinkingLevel": "minimal"}},
]


# ------------------------------------------------------------------------------ Gemini client


class PrivacyError(RuntimeError):
    pass


class GeminiRunner:
    """One model + thinking config over the configured keys. Records every call."""

    def __init__(self, model: str, thinking: dict[str, Any], guard: list[str], raw_dir: Path):
        self.model, self.thinking, self.guard = model, thinking, guard
        self.raw_dir = raw_dir
        raw_dir.mkdir(parents=True, exist_ok=True)
        self.keys = configured_keys()
        self.next_key = 0
        self.calls: list[dict[str, Any]] = []
        self.phase = ""

    def _check_privacy(self, text: str) -> None:
        low, digits = text.lower(), re.sub(r"\D", "", text)
        for term in self.guard:
            hit = (term in digits) if term.isdigit() else (term in low)
            if hit:
                raise PrivacyError(f"private contact data ({hashlib.sha256(term.encode()).hexdigest()[:6]}) "
                                   "found in a request: not sent")

    def call(self, system: str, message: str, schema_model: type, label: str) -> Any:
        self._check_privacy(system + "\n" + message)
        schema = plan_schema(schema_model)
        n = len(self.calls) + 1
        stem = f"{self.phase}-{n:02d}-{label}"
        (self.raw_dir / f"{stem}.request.txt").write_text(
            f"## SYSTEM\n{system}\n\n## USER\n{message}\n\n## SCHEMA\n{json.dumps(schema, indent=1)}")
        rec: dict[str, Any] = {"phase": self.phase, "label": label, "attempts": [], "model": self.model,
                               "thinking": self.thinking, "tokens_in": 0, "tokens_out": 0,
                               "tokens_thinking": 0, "valid_json_first_try": None,
                               "valid_schema_first_try": None, "invalid_retry": False}
        self.calls.append(rec)
        contents = [{"role": "user", "parts": [{"text": message}]}]
        started = time.monotonic()
        result = None
        for round_ in range(2):  # round 1 = the answer; round 2 = one retry with the error fed back
            text = self._generate(system, contents, schema, rec, f"{stem}.r{round_ + 1}")
            try:
                data = json.loads(strip_fence(text))
                if round_ == 0:
                    rec["valid_json_first_try"] = True
            except ValueError as exc:
                data, error = None, f"not valid JSON ({exc})"
                if round_ == 0:
                    rec["valid_json_first_try"] = False
            else:
                try:
                    result = schema_model.model_validate(data)
                    if round_ == 0:
                        rec["valid_schema_first_try"] = True
                    break
                except Exception as exc:  # noqa: BLE001 pydantic ValidationError
                    error = str(exc.errors()[0]["loc"]) + ": " + str(exc.errors()[0]["msg"]) \
                        if hasattr(exc, "errors") else str(exc)
                    if round_ == 0:
                        rec["valid_schema_first_try"] = False
            if round_ == 0:
                rec["invalid_retry"] = True
                rec["first_error"] = error
                contents += [{"role": "model", "parts": [{"text": text or "{}"}]},
                             {"role": "user", "parts": [{"text": "Your answer was invalid: "
                              f"{error}. Reply again with JSON that matches the schema."}]}]
        rec["seconds"] = round(time.monotonic() - started, 1)
        if result is None:
            rec["failed"] = "invalid output after one retry"
            raise CVGenerationFailed(f"{self.model} returned invalid output twice")
        return result

    def _generate(self, system: str, contents: list[dict[str, Any]], schema: dict[str, Any],
                  rec: dict[str, Any], stem: str) -> str:
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                "generationConfig": {"responseMimeType": "application/json",
                                     "responseJsonSchema": schema,
                                     "thinkingConfig": self.thinking}}
        last = ""
        for attempt in range(len(BACKOFF) + 1):
            label, key = self.keys[self.next_key % len(self.keys)]
            self.next_key += 1
            t0 = time.monotonic()
            try:
                with httpx.Client(timeout=300) as client:
                    res = client.post(f"{BASE}/models/{self.model}:generateContent",
                                      params={"key": key}, json=body)
                status = res.status_code
            except httpx.HTTPError as exc:
                status, res = 0, None
                last = exc.__class__.__name__
            rec["attempts"].append({"status": status, "key": label,
                                    "seconds": round(time.monotonic() - t0, 1)})
            if status == 200 and res is not None:
                data = res.json()
                (self.raw_dir / f"{stem}.response.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=1))
                u = data.get("usageMetadata") or {}
                rec["tokens_in"] += u.get("promptTokenCount") or 0
                rec["tokens_out"] += u.get("candidatesTokenCount") or 0
                rec["tokens_thinking"] += u.get("thoughtsTokenCount") or 0
                try:
                    parts = data["candidates"][0]["content"]["parts"]
                except (KeyError, IndexError, TypeError):
                    last = f"no answer ({(data.get('candidates') or [{}])[0].get('finishReason')})"
                    continue
                return "".join(p.get("text", "") for p in parts if not p.get("thought"))
            if res is not None:
                last = f"{status}: {res.text[:160]!r}"
            if status not in (0, 429, 500, 503, 504):
                break
            if attempt < len(BACKOFF):
                time.sleep(BACKOFF[attempt])
        raise CVGenerationFailed(f"{self.model} did not answer ({last})")

    def summary(self, phase: str) -> dict[str, Any]:
        calls = [c for c in self.calls if c["phase"] == phase]
        attempts = [a for c in calls for a in c["attempts"]]
        return {
            "calls": len(calls),
            "valid_json_first_try": [c["valid_json_first_try"] for c in calls],
            "valid_schema_first_try": [c["valid_schema_first_try"] for c in calls],
            "invalid_retries": sum(1 for c in calls if c["invalid_retry"]),
            "http_attempts": len(attempts),
            "retries_429": sum(1 for a in attempts if a["status"] == 429),
            "retries_503": sum(1 for a in attempts if a["status"] == 503),
            "retries_other": sum(1 for a in attempts if a["status"] not in (200, 429, 503)),
            "model_seconds": round(sum(c.get("seconds", 0) for c in calls), 1),
            "tokens_in": sum(c["tokens_in"] for c in calls),
            "tokens_out": sum(c["tokens_out"] for c in calls),
            "tokens_thinking": sum(c["tokens_thinking"] for c in calls),
            "keys_used": sorted({a["key"] for a in attempts if a["status"] == 200}),
        }


class _GeminiMixin:
    runner: GeminiRunner
    phase: str

    def command(self, system: str | None = None, schema: type = CVPlanDraft) -> list[Any]:  # type: ignore[override]
        return ["gemini", system or self.system_prompt, schema]  # type: ignore[attr-defined]

    def _call(self, cmd: list[Any], message: str, model: type) -> Any:
        self.runner.phase = self.phase
        summary_prompt = getattr(self, "summary_prompt", "")
        label = "summary-retry" if summary_prompt and summary_prompt in cmd[1] else "main"
        started = time.monotonic()
        try:
            return self.runner.call(cmd[1], message, model, label)
        finally:
            self.last_duration_ms = int((time.monotonic() - started) * 1000)  # type: ignore[attr-defined]


class GeminiCV(_GeminiMixin, ClaudeCVGenerator):
    phase = "cv"

    def __init__(self, runner: GeminiRunner, name: str):
        super().__init__(name)
        self.runner, self.via = runner, "gemini api"


class GeminiEmail(_GeminiMixin, ClaudeEmailDrafter):
    phase = "email"

    def __init__(self, runner: GeminiRunner, name: str):
        super().__init__(name)
        self.runner, self.via = runner, "gemini api"


class RecordingVerifier:
    """Wraps the Claude verifier and keeps every request/answer (the CV's adapted-bullet check)."""

    def __init__(self, inner: Any):
        self.inner, self.records = inner, []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def verify(self, request: dict[str, Any]) -> Any:
        plan = self.inner.verify(request)
        self.records.append({"kind": request["kind"], "text": request["text"],
                             "claims": [c.model_dump() for c in plan.claims]})
        return plan


# ------------------------------------------------------------------------------------ keys


def keys_report() -> dict[str, Any]:
    rows = []
    for label, key in configured_keys():
        row: dict[str, Any] = {"key": label, "fingerprint": fingerprint(key)}
        r = httpx.get(f"{BASE}/models", params={"key": key, "pageSize": 200}, timeout=30)
        row["list_models"] = r.status_code
        for model in ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite"):
            result = None
            for _attempt in range(4):  # 503 = the model is busy, not the key
                r = httpx.post(f"{BASE}/models/{model}:generateContent", params={"key": key},
                               timeout=60, json={"contents": [{"role": "user", "parts": [
                                   {"text": "Reply with the word ok"}]}]})
                result = r.status_code
                if result != 503:
                    break
                time.sleep(5)
            row[model] = result
        rows.append(row)
    return {"keys": rows}


# ------------------------------------------------------------------------------- analysis


def numbers(text: str) -> set[str]:
    return {re.sub(r"\s", "", m.group(0)) for m in NUMBER.finditer(text)}


def private_terms(profile: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if profile.get("email"):
        out.append(str(profile["email"]).strip().lower())
    digits = re.sub(r"\D", "", str(profile.get("phone") or ""))
    if len(digits) >= 7:
        out.append(digits)
    for link in profile.get("links") or []:
        url = str(link.get("url") or "").strip().lower().rstrip("/")
        if url:
            out.append(re.sub(r"^https?://(www\.)?", "", url))
    return out


def split_violations(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    def fmt(v: dict[str, Any]) -> str:
        return f"[{v.get('type', '?')}] {v.get('where', '')}: {v.get('message', '')}".strip()
    return {"errors": [fmt(v) for v in items if v.get("severity") == "error"],
            "warnings": [fmt(v) for v in items if v.get("severity") != "error"]}


def analyze_cv(s: Session, v: CVVersion) -> dict[str, Any]:
    from app.services import bullet_tailor
    from app.services.cv_pool import load_pool

    pool = load_pool(s)
    plan = (v.plan or {}).get("plan") or {}
    diffs, dropped_all, added_all = [], set(), set()
    for group in ("roles", "projects", "volunteering"):
        for entry in plan.get(group) or []:
            item = pool.get(entry["item_id"])
            for b in entry.get("bullets") or []:
                original = bullet_tailor.original_of(pool, entry["item_id"], b["source_index"])
                if original is None or bullet_tailor.plain(b["text"]) == bullet_tailor.plain(original):
                    continue
                n_drop, n_add = numbers(original) - numbers(b["text"]), \
                    numbers(b["text"]) - numbers(original)
                t_drop = bullet_tailor.pool_terms_in(original, pool) - \
                    bullet_tailor.pool_terms_in(b["text"], pool)
                t_add = bullet_tailor.pool_terms_in(b["text"], pool) - \
                    bullet_tailor.pool_terms_in(original, pool)
                dropped_all |= n_drop | {str(t) for t in t_drop}
                added_all |= n_add | {str(t) for t in t_add}
                diffs.append({"item": f"{item.title if item else entry['item_id']} "
                                      f"({item.org if item else ''})",
                              "bullet": f"{entry['item_id']}:{b['source_index']}",
                              "original": original, "final": b["text"],
                              "numbers_dropped": sorted(n_drop), "numbers_added": sorted(n_add),
                              "terms_dropped": sorted(map(str, t_drop)),
                              "terms_added": sorted(map(str, t_add))})
    content = v.content or {}
    summary = content.get("summary", "")
    pool_text = pool.all_text()
    summary_new_numbers = sorted(n for n in numbers(summary) if n not in numbers(pool_text))
    tailoring = ((v.plan or {}).get("tailoring") or {})
    return {
        "page_count": v.page_count, "fill_pct": round((v.fill or 0) * 100, 1),
        "violations": split_violations(v.violations or []),
        "bullets_changed": diffs, "numbers_or_terms_added": sorted(added_all),
        "numbers_or_terms_dropped": sorted(dropped_all),
        "summary": summary, "summary_numbers_not_in_pool": summary_new_numbers,
        "skills": [f"{g['category']}: {', '.join(g['items'])}" for g in content.get("skills") or []],
        "tailoring_report": {k: tailoring.get(k) for k in ("adapted", "original", "fallbacks",
                                                           "verifier")},
        "summary_grounding": (v.plan or {}).get("summary_grounding"),
    }


def email_text(s: Session, d: OutreachDraft) -> str:
    from app.services import verifier as vs
    return vs.email_text(s, d)


def analyze_email(s: Session, d: OutreachDraft, expected_language: str) -> dict[str, Any]:
    from app.services import applied_check as ac
    from app.services import language as lang

    plan = d.plan or {}
    body = d.body
    text = email_text(s, d)
    return {
        "language_chosen": plan.get("language"), "language_rule": expected_language,
        "language_matches_rule": plan.get("language") == expected_language,
        "detected_language_of_text": lang.detect(body) if hasattr(lang, "detect") else None,
        "words": len(re.findall(r"\w+", body)), "words_range": f"{ac.MIN_WORDS}-{ac.MAX_WORDS}",
        "attempts": plan.get("attempts"), "violations": split_violations(d.violations or []),
        "subject": d.subject, "full_text": text,
    }


def claims_table(record: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [{k: c.get(k) for k in ("sentence", "claim", "about", "verdict", "source_id",
                                   "source_quote", "reason")}
            for c in (record or {}).get("claims") or []]


# ------------------------------------------------------------------------------ one config


def save_cv(s: Session, v: CVVersion, folder: Path) -> None:
    (folder / "cv.json").write_text(json.dumps({
        "version": v.version, "status": str(v.status), "generator_model": v.generator_model,
        "page_count": v.page_count, "fill": v.fill, "content": v.content, "plan": v.plan,
        "violations": v.violations, "overrides": v.overrides}, ensure_ascii=False, indent=1,
        default=str))
    if v.pdf_path and Path(v.pdf_path).exists():
        shutil.copy(v.pdf_path, folder / "cv.pdf")


def save_email(s: Session, d: OutreachDraft, folder: Path, info: dict[str, Any]) -> None:
    claims = claims_table(d.verification)
    lines = [f"# {d.subject}", "", "```text", email_text(s, d), "```", "",
             f"model: {d.model} | prompt: {d.prompt_version} | language: {info['language_chosen']} "
             f"(rule: {info['language_rule']}) | words: {info['words']}", "",
             "## Code checks", *(f"- ERROR {m}" for m in info["violations"]["errors"]),
             *(f"- warning {m}" for m in info["violations"]["warnings"]),
             "" if info["violations"]["errors"] or info["violations"]["warnings"] else "- none", "",
             f"## Claude claim verifier: {(d.verification or {}).get('status', 'not run')}"]
    lines += [f"- **{c['verdict']}** “{c['claim']}” (source {c['source_id'] or '-'}"
              f"{'; ' + c['reason'] if c['reason'] else ''})" for c in claims]
    (folder / "email.md").write_text("\n".join(lines) + "\n")
    (folder / "email_verification.json").write_text(json.dumps(d.verification, ensure_ascii=False,
                                                               indent=1, default=str))


def run_config(cfg: dict[str, Any], app_id: int, out: Path, cverifier: Any,
               guard: list[str], expected_language: str) -> dict[str, Any]:
    from app.services import cv_service, outreach
    from app.services import verifier as vs

    folder = out / cfg["name"]
    folder.mkdir(parents=True, exist_ok=True)
    cv_service.CV_DIR = folder / "cvfiles"  # renders never go near data/cv
    runner = GeminiRunner(cfg["model"], cfg["thinking"], guard, folder / "raw")
    result: dict[str, Any] = {"config": cfg}

    # ---- CV
    rec = RecordingVerifier(cverifier)
    started = time.monotonic()
    try:
        v = cv_service.generate(engine, app_id, GeminiCV(runner, cfg["name"]), verifier=rec)
        result["cv_total_seconds"] = round(time.monotonic() - started, 1)
        with Session(engine) as s:
            v = s.get(CVVersion, v.id)
            result["cv"] = analyze_cv(s, v)
            save_cv(s, v, folder)
        result["cv_verifier_records"] = rec.records
        (folder / "cv_adapted_bullets_verifier.json").write_text(
            json.dumps(rec.records, ensure_ascii=False, indent=1))
    except Exception as exc:  # noqa: BLE001 a failed generation is a result, not a crash
        result["cv_error"] = f"{type(exc).__name__}: {exc}"
    result["cv_model"] = runner.summary("cv")

    # ---- email (written from the approved Claude CV, as in production)
    started = time.monotonic()
    try:
        draft = outreach.generate_applied(engine, app_id, GeminiEmail(runner, cfg["name"]))
        result["email_total_seconds"] = round(time.monotonic() - started, 1)
        with Session(engine) as s:
            d = s.get(OutreachDraft, draft.id)
            blocked_by_code = bool([x for x in d.violations or [] if x["severity"] == "error"])
            vs.verify_email(s, d, cverifier)  # run even when production would stop at the code errors
            s.commit()
            s.refresh(d)
            info = analyze_email(s, d, expected_language)
            info["verifier_status"] = (d.verification or {}).get("status")
            info["verifier_would_run_in_production"] = not blocked_by_code
            info["claims"] = claims_table(d.verification)
            result["email"] = info
            save_email(s, d, folder, info)
    except Exception as exc:  # noqa: BLE001
        result["email_error"] = f"{type(exc).__name__}: {exc}"
    result["email_model"] = runner.summary("email")
    (folder / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=1,
                                                    default=str))
    (folder / "calls.json").write_text(json.dumps(runner.calls, indent=1))
    return result


def save_baseline(app_id: int, out: Path) -> dict[str, Any]:
    from app.services import outreach

    folder = out / "claude-baseline"
    folder.mkdir(parents=True, exist_ok=True)
    with Session(engine) as s:
        app = s.get(Application, app_id)
        v = outreach.approved_cv(s, app)
        d = s.exec(select(OutreachDraft).where(
            OutreachDraft.application_id == app_id,
            OutreachDraft.status.in_(["approved", "queued", "sent"]))  # type: ignore[attr-defined]
        ).first()
        save_cv(s, v, folder)
        info = analyze_email(s, d, (d.plan or {}).get("language_choice", {}).get("language", "en"))
        info["verifier_status"] = (d.verification or {}).get("status")
        info["claims"] = claims_table(d.verification)
        save_email(s, d, folder, info)
        base = {"cv": analyze_cv(s, v), "email": info, "cv_version": v.version,
                "draft_id": d.id, "model": v.generator_model, "email_model": d.model,
                "cv_generation_ms": (v.plan or {}).get("generation_ms"),
                "email_duration_ms": d.duration_ms}
    (folder / "metrics.json").write_text(json.dumps(base, ensure_ascii=False, indent=1,
                                                    default=str))
    return base


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", type=int, default=1622)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--keys-only", action="store_true")
    ap.add_argument("--only", help="comma-separated config names")
    args = ap.parse_args()
    if args.keys_only:
        args.out.mkdir(parents=True, exist_ok=True)
        report = keys_report()
        (args.out / "keys.json").write_text(json.dumps(report, indent=1))
        print(json.dumps(report, indent=1))
        return
    from app.providers.registry import verifier as make_verifier
    from app.services import outreach
    from app.services.cv_pool import load_pool

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    assert str(engine.url).endswith("scratch.db"), "must run on the scratch copy"
    with Session(engine) as s:
        app = s.get(Application, args.app)
        job = s.get(Job, app.job_id)
        guard = private_terms(load_pool(s).profile)
        expected_language = outreach.language_choice(s, job, app, None).language
    verifier = make_verifier(mock=False)
    keys_file = out / "keys.json"  # written by --keys-only (slow when a model answers 503)
    summary: dict[str, Any] = {"app_id": args.app,
                               "keys": json.loads(keys_file.read_text()) if keys_file.exists() else None,
                               "baseline": save_baseline(args.app, out), "configs": []}
    for cfg in CONFIGS:
        if args.only and cfg["name"] not in args.only.split(","):
            continue
        print(f"== {cfg['name']}", flush=True)
        summary["configs"].append(run_config(cfg, args.app, out, verifier, guard,
                                             expected_language))
        (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1,
                                                     default=str))
    print("done", out, flush=True)


if __name__ == "__main__":
    main()
