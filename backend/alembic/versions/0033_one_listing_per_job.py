"""one listing per real job: country back in the dedupe key, old duplicates folded in

Data only (no schema change). Recomputes every dedupe key, gives each main listing the sources
and URLs of its duplicate rows (which stay, hidden, with their own text), and marks the score of
a job whose description changed as stale (nothing is rescored). The downgrade can't restore old
keys; it is a no-op (the database is backed up before this runs).

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0033"
down_revision: Union[str, Sequence[str], None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """`DEDUPE_ORIGINALS_DB` (optional): a backup from before migration 0032. Main rows whose
    text 0032 overwrote with a duplicate's get their own text back (see listing_merge.backfill)."""
    import os
    import sqlite3

    from app.services.listing_merge import backfill

    originals = None
    if path := os.environ.get("DEDUPE_ORIGINALS_DB"):
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as old:
            originals = {i: d or "" for i, d in old.execute(
                "SELECT id, description FROM job WHERE duplicate_of_id IS NULL")}
    backfill(op.get_bind(), apply=True, originals=originals)


def downgrade() -> None:
    pass
