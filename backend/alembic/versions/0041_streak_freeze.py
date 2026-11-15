"""streak_freeze: freezes bought with tokens (owned until used, one per frozen day)

Revision ID: 0041
Revises: 0040
Create Date: 2026-11-16 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import app.models.base  # noqa: F401

revision: str = "0041"
down_revision: Union[str, Sequence[str], None] = "0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "streak_freeze",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(), nullable=False),
        sa.Column("bought_at", app.models.base.UTCDateTime(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("used_on", sa.Date(), nullable=True),
        sa.Column("purchase_entry_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["purchase_entry_id"], ["token_entry.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_streak_freeze_used_on", "streak_freeze", ["used_on"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_streak_freeze_used_on", table_name="streak_freeze")
    op.drop_table("streak_freeze")
