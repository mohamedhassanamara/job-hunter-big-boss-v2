"""fit score: core requirements of the role (prompt v5) and which ones the candidate lacks

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-20 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

import app.models.base  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = '0027'
down_revision: Union[str, Sequence[str], None] = '0026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('fit_score', schema=None) as b:
        b.add_column(sa.Column('core_requirements', sa.JSON(), nullable=False, server_default='[]'))


def downgrade() -> None:
    with op.batch_alter_table('fit_score', schema=None) as b:
        b.drop_column('core_requirements')
