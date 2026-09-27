"""CV generation: Claude CLI call (mocked), no-fabrication checks, the one-page fit loop (with a
fake compiler), overrides and versioning."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import Application, AppSetting, CVVersion, ExperienceItem
from app.providers.base import CVGenerationFailed, CVPlan, CVRequest, PlanBullet, PlanEntry
from app.providers.claude_cv import ClaudeCVGenerator, plan_schema
from app.providers.mock import MockCVGenerator
from app.services import cv_build, cv_service
from app.services.cv_build import FitState, build_document, fit_to_page, initial_state
from app.services.cv_check import check_plan
from app.services.cv_pool import load_pool, prompt_pool, readiness
from app.services.cv_render import CompileResult, CVProfile, load_template

# ------------------------------------------------------------------------------ Claude CLI


def fake_run(stdout: dict | str, returncode: int = 0, calls: list | None = None,
             auth: str = "none"):
    """A stream-json transcript: init event (with the auth source), then the result."""
    def run(cmd, **kw):  # noqa: ANN001, ANN202
        if calls is not None:
            calls.append((cmd, kw))
        init = json.dumps({"type": "system", "subtype": "init", "apiKeySource": auth})
        body = stdout if isinstance(stdout, str) else json.dumps({"type": "result", **stdout})
        return SimpleNamespace(stdout=f"{init}\n{body}\n", stderr="", returncode=returncode)
    return run


PLAN = {"summary": "Engineer.", "summary_short": "Engineer.", "roles": [
    {"item_id": 1, "relevance": 9,
     "bullets": [{"source_index": 0, "text": "Did x", "priority": 1}]}]}
REQUEST = CVRequest(job={"title": "Data Engineer"}, pool={"roles": []})


def test_cli_call_is_isolated_and_structured() -> None:
    calls: list = []
    gen = ClaudeCVGenerator("claude-sonnet-5", runner=fake_run(
        {"is_error": False, "structured_output": PLAN, "total_cost_usd": 0.02}, calls=calls))
    plan = gen.generate(REQUEST)
    assert plan.roles[0].bullets[0].text == "Did x" and gen.last_cost_usd == 0.02
    cmd, kw = calls[0]
    assert cmd[1] == "-p" and "--json-schema" in cmd and "--no-session-persistence" in cmd
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-5"
    assert "--system-prompt" in cmd and "--strict-mcp-config" in cmd
    assert "EXPERIENCE POOL" in kw["input"] and kw["timeout"] > 0 and kw["cwd"]  # temp dir
    assert gen.auth_source == "none"
    schema = json.loads(cmd[cmd.index("--json-schema") + 1])
    assert schema == plan_schema() and "$defs" not in json.dumps(schema)


@pytest.mark.parametrize(
    ("stdout", "code", "message"),
    [
        ({"is_error": True, "result": "Not logged in · Please run /login"}, 1, "sign in"),
        ("garbage", 0, "no JSON"),
        ({"is_error": False, "structured_output": {"summary": 3}}, 0, "didn't match"),
        ({"is_error": False, "result": "not json"}, 0, "wasn't valid JSON"),
    ],
)
def test_cli_failures_are_visible(stdout, code: int, message: str) -> None:  # noqa: ANN001
    gen = ClaudeCVGenerator(runner=fake_run(stdout, code))
    with pytest.raises(CVGenerationFailed, match=message):
        gen.generate(REQUEST)


def test_refuses_api_key_auth_and_strips_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    gen = ClaudeCVGenerator(runner=fake_run({"is_error": False, "structured_output": PLAN},
                                            auth="ANTHROPIC_API_KEY"))
    with pytest.raises(CVGenerationFailed, match="API key"):
        gen.generate(REQUEST)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "parent")
    monkeypatch.setenv("CLAUDECODE", "1")
    env = ClaudeCVGenerator.child_env()
    assert "ANTHROPIC_API_KEY" not in env and "CLAUDE_CODE_SESSION_ID" not in env
    assert "CLAUDECODE" not in env and "PATH" in env


def test_cli_timeout() -> None:
    def slow(cmd, **kw):  # noqa: ANN001, ANN202
        raise subprocess.TimeoutExpired(cmd, 1)
    with pytest.raises(CVGenerationFailed, match="timed out"):
        ClaudeCVGenerator(runner=slow).generate(REQUEST)


# --------------------------------------------------------------------------------- checks


@pytest.fixture
def pool(seeded: None):  # noqa: ANN201
    with Session(engine) as s:
        return load_pool(s)


def test_checks_numbers_ids_skills_tools_and_restore_roles(pool) -> None:  # noqa: ANN001
    roles = pool.of("job")
    first = roles[0]
    fact = pool.facts(first)[0]
    skill = pool.of("skill")[0]
    plan = CVPlan(
        summary="Built systems with DeepSpeed.", summary_short="Built systems.",
        roles=[PlanEntry(item_id=first.id, relevance=9, bullets=[
            PlanBullet(source_index=0, text=fact + " Improved it by 73%.", priority=1),
            PlanBullet(source_index=99, text="Invented bullet", priority=2),
        ]), PlanEntry(item_id=999999, relevance=5, bullets=[])],
        skills=[{"item_id": skill.id, "items": [skill.tags[0], "COBOL"]}],
        education_ids=[],
    )
    repaired, issues = check_plan(plan, pool)
    kinds = {(i["type"], i["severity"]) for i in issues}
    assert ("number", "error") in kinds  # 73% isn't in the source
    assert ("unknown_fact", "error") in kinds and ("unknown_item", "error") in kinds
    assert ("new_skill", "error") in kinds and ("new_tool", "warning") in kinds  # COBOL, DeepSpeed
    assert [b.source_index for b in repaired.roles[0].bullets] == [0]
    assert {e.item_id for e in repaired.roles} == {r.id for r in roles}  # nothing dropped
    assert all(e.bullets for e in repaired.roles if pool.facts(pool.get(e.item_id)))
    assert "COBOL" not in repaired.skills[0].items
    assert repaired.education_ids == [e.id for e in pool.of("education")]


def test_readiness_needs_a_full_name(pool) -> None:  # noqa: ANN001
    pool.profile["full_name"] = ""
    assert any(r["key"] == "full_name" and r["severity"] == "blocker" for r in readiness(pool))
    pool.profile["full_name"] = "Ada"
    assert not any(r["severity"] == "blocker" for r in readiness(pool))


def test_prompt_pool_has_ids_and_no_contact_data(pool) -> None:  # noqa: ANN001
    pool.profile.update({"email": "secret@example.com", "phone": "+1 555"})
    data = json.dumps(prompt_pool(pool))
    assert "secret@example.com" not in data and "+1 555" not in data
    assert all("id" in r and "facts" in r for r in prompt_pool(pool)["roles"])


# ---------------------------------------------------------------------------- fit loop


def plan_for(pool) -> CVPlan:  # noqa: ANN001
    plan = MockCVGenerator().generate(CVRequest(job={"title": "Data Engineer"},
                                                pool=prompt_pool(pool)))
    return check_plan(plan, pool)[0]


def fake_compiler(capacity: int, calls: list):
    """Pages/fill from the number of bullet lines: `capacity` lines fit on a page."""
    def compile_tex(tex: str, out_dir: Path, name: str = "cv") -> CompileResult:
        lines = tex.count(r"\resumeItem{") * 2 + tex.count(r"\section{") * 2 + 4
        calls.append(lines)
        pages = 1 + (lines - 1) // capacity
        fill = (lines - (pages - 1) * capacity) / capacity
        return CompileResult(True, out_dir / f"{name}.pdf", pages, fill)
    return compile_tex


def test_overflow_drops_bullets_but_keeps_one_per_role(pool, monkeypatch, tmp_path) -> None:  # noqa: ANN001
    calls: list = []
    monkeypatch.setattr(cv_build, "compile_tex", fake_compiler(capacity=24, calls=calls))
    plan = plan_for(pool)
    result = fit_to_page(plan, pool, CVProfile(full_name="Ada"), load_template("default"),
                         tmp_path)
    assert result.compiled.pages == 1
    assert all(len(r.bullets) >= 1 for r in result.document.roles if r.bullets is not None)
    assert len(result.document.roles) == len(pool.of("job"))  # no job dropped
    assert len(calls) <= cv_build.MAX_PASSES + 2  # ≤ 4 adjustments (+ final re-render)


def test_underfill_adds_bullets(pool, monkeypatch, tmp_path) -> None:  # noqa: ANN001
    calls: list = []
    monkeypatch.setattr(cv_build, "compile_tex", fake_compiler(capacity=400, calls=calls))
    plan = plan_for(pool)
    start = sum(initial_state(plan).counts.values())
    result = fit_to_page(plan, pool, CVProfile(full_name="Ada"), load_template("default"),
                         tmp_path)
    assert sum(result.state.counts.values()) > start  # grew toward a full page
    assert result.compiled.pages == 1 and result.passes <= cv_build.MAX_PASSES


def test_overrides_force_in_out_and_edit(pool) -> None:  # noqa: ANN001
    plan = plan_for(pool)
    role = plan.roles[0]
    first, *rest = role.bullets
    key = f"role:{role.item_id}"
    state = FitState(counts={**initial_state(plan).counts, key: 1})
    overrides = {"force_out": [f"{key}:{first.source_index}"],
                 "text": {f"{key}:{rest[0].source_index}": "Edited bullet."} if rest else {},
                 "force_in": [f"cert:{c.id}" for c in pool.of("certification")]}
    doc = build_document(plan, pool, state, overrides)
    shown = next(r for r in doc.roles if r.item_id == role.item_id).bullets
    assert first.text not in shown and len(shown) == 1
    if rest:
        assert shown == ["Edited bullet."]
    assert {c.item_id for c in doc.certifications} == {c.id for c in pool.of("certification")}


# --------------------------------------------------------------------------- versioning


def test_generate_twice_supersedes_the_draft(seeded: None, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(cv_build, "compile_tex", fake_compiler(capacity=60, calls=[]))
    with Session(engine) as s:
        row = s.exec(select(AppSetting).where(AppSetting.key == "profile")).one()
        row.value = {**row.value, "full_name": "Ada"}
        s.add(row)
        s.commit()
        app_id = s.exec(select(Application.id)).first()
    v1 = cv_service.generate(engine, app_id, MockCVGenerator())
    v2 = cv_service.generate(engine, app_id, MockCVGenerator())
    assert v2.version == v1.version + 1 and v2.status == "draft"
    with Session(engine) as s:
        assert s.get(CVVersion, v1.id).status == "superseded"
        assert s.get(CVVersion, v2.id).plan["plan"]["roles"]
    assert v2.template == "default" and v2.page_count == 1


# ------------------------------------------------------------------------------ migration


def test_migration_moves_credential_ids_and_clears_the_header(monkeypatch) -> None:  # noqa: ANN001
    import importlib.util

    import sqlalchemy as sa

    path = next(Path(__file__).parents[1].glob("alembic/versions/0006_*.py"))
    spec = importlib.util.spec_from_file_location("m0006", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    db = sa.create_engine("sqlite://")
    with db.begin() as conn:
        conn.exec_driver_sql("create table experience_item (id int, kind text, summary text, "
                             "credential_id text)")
        conn.exec_driver_sql("create table app_setting (key text, value text)")
        conn.exec_driver_sql("insert into experience_item values (1, 'certification', "
                             "'Credential ID AB123', null), (2, 'certification', "
                             "'Covers Spark and dbt', null), (3, 'job', 'Credential ID X', null)")
        conn.exec_driver_sql("insert into app_setting values ('profile', ?)", (json.dumps(
            {"full_name": "A", "email": "a@b.c", "based_in": "X", "languages": ["en"]}),))
        monkeypatch.setattr(module.op, "get_bind", lambda: conn, raising=False)
        module._data()
        rows = conn.exec_driver_sql("select id, summary, credential_id from experience_item "
                                    "order by id").all()
        profile = json.loads(conn.exec_driver_sql("select value from app_setting").scalar())
    assert rows == [(1, None, "AB123"), (2, "Covers Spark and dbt", None),
                    (3, "Credential ID X", None)]
    assert profile["full_name"] == profile["email"] == profile["based_in"] == ""
    assert profile["languages"] == ["en"] and profile["links"] == []


def test_experience_items_keep_their_new_fields(client) -> None:  # noqa: ANN001
    body = {"kind": "certification", "title": "Cert", "org": "Issuer",
            "credential_id": "ID-1", "url": "https://example.com/c/1"}
    item = client.post("/api/experience", json=body).json()
    assert item["credential_id"] == "ID-1" and item["url"] == "https://example.com/c/1"
    with Session(engine) as s:
        assert s.get(ExperienceItem, item["id"]).credential_id == "ID-1"
