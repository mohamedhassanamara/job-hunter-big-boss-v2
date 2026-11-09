"""experience_item.soft_skills: soft skills a job or volunteering item supports (skills list only)

Revision ID: 0039
Revises: 0038
Create Date: 2026-11-09 19:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: Union[str, Sequence[str], None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("experience_item") as batch:
        batch.add_column(sa.Column("soft_skills", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("experience_item") as batch:
        batch.drop_column("soft_skills")
