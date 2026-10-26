"""usage_event: the local usage log (screens, key actions, waits, idle gaps)

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-26 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import app.models.base

revision: str = "0034"
down_revision: Union[str, Sequence[str], None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(), nullable=False),
        sa.Column("at", app.models.base.UTCDateTime(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("screen", sa.String(length=100), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("wall_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_usage_event_at"), "usage_event", ["at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_usage_event_at"), table_name="usage_event")
    op.drop_table("usage_event")
