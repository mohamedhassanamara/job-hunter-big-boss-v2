"""search_profile.remote_scope

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-27 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('search_profile', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('remote_scope', sa.String(length=32), nullable=False,
                      server_default='anywhere')
        )


def downgrade() -> None:
    with op.batch_alter_table('search_profile', schema=None) as batch_op:
        batch_op.drop_column('remote_scope')
