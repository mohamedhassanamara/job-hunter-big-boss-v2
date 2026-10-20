"""fit confirmation: a second opinion (Ask Claude) stored next to the main score

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-20 18:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

import app.models.base  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = '0028'
down_revision: Union[str, Sequence[str], None] = '0027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fit_confirmation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('source', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('model', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('via', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('prompt_version', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('confirm_prompt_version', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('experience_version', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column('sub_scores', sa.JSON(), nullable=False),
        sa.Column('red_flags', sa.JSON(), nullable=False),
        sa.Column('core_requirements', sa.JSON(), nullable=False),
        sa.Column('strengths', sa.JSON(), nullable=False),
        sa.Column('gaps', sa.JSON(), nullable=False),
        sa.Column('summary', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('confidence', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('verdict', sa.JSON(), nullable=False),
        sa.Column('notes', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['job.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fit_confirmation_job_id'), 'fit_confirmation', ['job_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_fit_confirmation_job_id'), table_name='fit_confirmation')
    op.drop_table('fit_confirmation')
