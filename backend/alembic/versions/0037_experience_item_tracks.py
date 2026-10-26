"""experience_item.tracks: the tracks a project is meant for (empty = all)

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-26 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: Union[str, Sequence[str], None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("experience_item") as batch:
        batch.add_column(sa.Column("tracks", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("experience_item") as batch:
        batch.drop_column("tracks")
