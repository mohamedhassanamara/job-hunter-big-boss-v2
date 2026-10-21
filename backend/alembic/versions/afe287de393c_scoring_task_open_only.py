"""scoring task open_only

Revision ID: afe287de393c
Revises: 0031
Create Date: 2026-10-21 22:55:22.071561

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

import app.models.base  # noqa: F401

# revision identifiers, used by Alembic.
revision: str = 'afe287de393c'
down_revision: Union[str, Sequence[str], None] = '0031'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('scoring_task', schema=None) as batch_op:
        batch_op.add_column(sa.Column('open_only', sa.Boolean(), nullable=False,
                                      server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table('scoring_task', schema=None) as batch_op:
        batch_op.drop_column('open_only')
