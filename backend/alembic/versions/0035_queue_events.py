"""send_queue.paused_reason and the queue_event log (idle / running / paused changes)

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-26 20:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import app.models.base

revision: str = "0035"
down_revision: Union[str, Sequence[str], None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("send_queue") as batch:
        batch.add_column(sa.Column("paused_reason", sa.String(), nullable=True))
    op.create_table(
        "queue_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(), nullable=False),
        sa.Column("at", app.models.base.UTCDateTime(), nullable=False),
        sa.Column("from_status", sa.String(), nullable=False),
        sa.Column("to_status", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("actor", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_queue_event_at"), "queue_event", ["at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_queue_event_at"), table_name="queue_event")
    op.drop_table("queue_event")
    with op.batch_alter_table("send_queue") as batch:
        batch.drop_column("paused_reason")
