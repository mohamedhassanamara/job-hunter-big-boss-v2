"""Draft history (parent, feedback) and approval without verification

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-21 17:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

import app.models.base  # noqa: F401


revision: str = '0030'
down_revision: Union[str, Sequence[str], None] = '0029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('outreach_draft', schema=None) as b:
        b.add_column(sa.Column('parent_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('feedback', sa.Text(), nullable=False, server_default=''))
        b.add_column(sa.Column('unverified_approval', sa.JSON(), nullable=True))
        b.create_foreign_key('fk_outreach_draft_parent', 'outreach_draft', ['parent_id'], ['id'])
    with op.batch_alter_table('cover_letter', schema=None) as b:
        b.add_column(sa.Column('feedback', sa.Text(), nullable=False, server_default=''))


def downgrade() -> None:
    with op.batch_alter_table('cover_letter', schema=None) as b:
        b.drop_column('feedback')
    with op.batch_alter_table('outreach_draft', schema=None) as b:
        b.drop_constraint('fk_outreach_draft_parent', type_='foreignkey')
        b.drop_column('unverified_approval')
        b.drop_column('feedback')
        b.drop_column('parent_id')
