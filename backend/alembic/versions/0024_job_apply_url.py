"""job apply url (where the listing says to apply), used to find the company's domain

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-19 13:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

import app.models.base  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = '0024'
down_revision: Union[str, Sequence[str], None] = '0023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('job', schema=None) as b:
        b.add_column(sa.Column('apply_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('job', schema=None) as b:
        b.drop_column('apply_url')
