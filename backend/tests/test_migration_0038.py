"""Migration 0038: the role-based LinkedIn groups (other/alumni -> peer, alumni keeps its flag)
and the linkedin_profile table. Replays the SHAPE of the 3 real linkedin_outreach rows (temp DB)."""

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from tests.conftest import BACKEND

NOW = "2026-10-29 10:00:00"


def _cfg(db: Path) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    return cfg


def _insert(con: sqlite3.Connection, table: str, **values: object) -> None:
    """A row with every NOT NULL column that has no default filled in (the migration only cares
    about the linkedin_* columns)."""
    info = con.execute(f"PRAGMA table_info({table})").fetchall()
    for _, name, kind, notnull, default, pk in info:
        if name in values or pk or not notnull or default is not None:
            continue
        values[name] = NOW if "DATE" in kind.upper() else 0 if kind.upper() in (
            "INTEGER", "BOOLEAN") else "[]" if "JSON" in kind.upper() else "x"
    cols = ", ".join(f'"{c}"' for c in values)
    con.execute(f"INSERT INTO {table} ({cols}) VALUES ({', '.join('?' * len(values))})",
                list(values.values()))


def _seed(con: sqlite3.Connection) -> None:
    _insert(con, "company", id=1, name="Co", normalized_name="co")
    _insert(con, "job", id=1, source="linkedin", external_id="x", url="u", title="T", company_id=1)
    _insert(con, "application", id=1, job_id=1, stage="new")
    for i in (1, 2, 3):
        _insert(con, "contact", id=i, company_id=1, full_name=f"P{i}", normalized_name=f"p{i}",
                source="linkedin")
    # the same three shapes as the real rows: recruiter + hiring team, alumni, other + hiring team
    rows = [(1, "recruiter", 0, 1, "sent"), (2, "alumni", 1, 0, "to_contact"),
            (3, "other", 0, 1, "to_contact")]
    for i, group, alumni, hiring, status in rows:
        _insert(con, "linkedin_outreach", id=i, application_id=1, contact_id=i, group=group,
                alumni=alumni, hiring_team=hiring, status=status)
    con.commit()


def test_the_three_real_row_shapes_map_as_decided(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    cfg = _cfg(db)
    command.upgrade(cfg, "0037")
    con = sqlite3.connect(db)
    _seed(con)
    con.close()
    command.upgrade(cfg, "0038")
    con = sqlite3.connect(db)
    got = con.execute('SELECT id, "group", alumni, hiring_team, status FROM linkedin_outreach '
                      "ORDER BY id").fetchall()
    assert got == [(1, "recruiter", 0, 1, "sent"),    # untouched
                   (2, "peer", 1, 0, "to_contact"),   # alumni -> peer, still an alum
                   (3, "peer", 0, 1, "to_contact")]   # other -> peer, still the hiring team
    cols = {r[1] for r in con.execute("PRAGMA table_info(linkedin_profile)")}
    assert {"contact_id", "persona", "persona_source", "is_alum", "capture_sources"} <= cols
    con.close()


def test_the_profile_is_deleted_with_its_contact_and_the_migration_reverses(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    cfg = _cfg(db)
    command.upgrade(cfg, "0037")
    con = sqlite3.connect(db)
    _seed(con)
    con.close()
    command.upgrade(cfg, "0038")
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=ON")
    _insert(con, "linkedin_profile", contact_id=2)
    con.execute("DELETE FROM linkedin_outreach WHERE contact_id = 2")
    con.execute("DELETE FROM contact WHERE id = 2")
    assert con.execute("SELECT COUNT(*) FROM linkedin_profile").fetchone()[0] == 0  # cascade
    con.commit()
    con.close()
    command.downgrade(cfg, "0037")
    con = sqlite3.connect(db)
    assert con.execute('SELECT id, "group" FROM linkedin_outreach ORDER BY id').fetchall() == \
        [(1, "recruiter"), (3, "other")]  # (the alumni row was deleted above)
    assert "linkedin_profile" not in {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
