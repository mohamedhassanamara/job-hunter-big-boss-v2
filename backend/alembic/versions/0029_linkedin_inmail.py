"""LinkedIn Premium: InMail per person (draft, sent, credit refunded), where a person came from
(viewed my profile) and leads whose company has no job yet

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-20 20:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

import app.models.base  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = '0029'
down_revision: Union[str, Sequence[str], None] = '0028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('linkedin_outreach', schema=None) as b:
        b.add_column(sa.Column('inmail', sa.JSON(), nullable=True))
        b.add_column(sa.Column('inmail_sent_at', sa.DateTime(), nullable=True))
        b.add_column(sa.Column('inmail_refunded_at', sa.DateTime(), nullable=True))
        b.add_column(sa.Column('source', sqlmodel.sql.sqltypes.AutoString(), nullable=False,
                               server_default='manual'))
        b.add_column(sa.Column('reason', sqlmodel.sql.sqltypes.AutoString(), nullable=False,
                               server_default=''))
        b.add_column(sa.Column('viewed_on', sa.Date(), nullable=True))
    op.create_table(
        'linkedin_lead',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('full_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('company_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('linkedin_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('viewed_on', sa.Date(), nullable=True),
        sa.Column('reason', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('linked_outreach_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['linked_outreach_id'], ['linkedin_outreach.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('linkedin_lead')
    with op.batch_alter_table('linkedin_outreach', schema=None) as b:
        b.drop_column('viewed_on')
        b.drop_column('reason')
        b.drop_column('source')
        b.drop_column('inmail_refunded_at')
        b.drop_column('inmail_sent_at')
        b.drop_column('inmail')
