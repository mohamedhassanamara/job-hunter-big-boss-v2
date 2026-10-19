"""interview prep: STAR stories and a pitch per job

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-19 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

import app.models.base  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = '0025'
down_revision: Union[str, Sequence[str], None] = '0024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('interview_prep',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', app.models.base.UTCDateTime(), nullable=False),
        sa.Column('updated_at', app.models.base.UTCDateTime(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('language', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('violations', sa.JSON(), nullable=False),
        sa.Column('verification', sa.JSON(), nullable=False),
        sa.Column('generator_model', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('prompt_version', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('plan', sa.JSON(), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['application.id']),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_interview_prep_application_id', 'interview_prep', ['application_id'])


def downgrade() -> None:
    op.drop_table('interview_prep')
