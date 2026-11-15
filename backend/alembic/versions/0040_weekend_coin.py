"""weekend_coin: one +1 token per job marked Applied on a weekend

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-15 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import app.models.base  # noqa: F401

revision: str = "0040"
down_revision: Union[str, Sequence[str], None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "weekend_coin",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("awarded_at", app.models.base.UTCDateTime(), nullable=False),
        sa.Column("token_entry_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["application.id"]),
        sa.ForeignKeyConstraint(["token_entry_id"], ["token_entry.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_weekend_coin_application_id", "weekend_coin", ["application_id"],
                    unique=True)


def downgrade() -> None:
    op.drop_index("ix_weekend_coin_application_id", table_name="weekend_coin")
    op.drop_table("weekend_coin")
