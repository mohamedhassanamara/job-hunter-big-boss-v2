"""contact providers: company cache, contact provenance, key usage and call log

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-19 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

import app.models.base  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = '0023'
down_revision: Union[str, Sequence[str], None] = '0022'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UTC = app.models.base.UTCDateTime
STR = sqlmodel.sql.sqltypes.AutoString


def _base() -> list[sa.Column]:
    return [sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('created_at', UTC(), nullable=False),
            sa.Column('updated_at', UTC(), nullable=False)]


def upgrade() -> None:
    with op.batch_alter_table('company', schema=None) as b:
        b.add_column(sa.Column('domain_source', STR(), nullable=True))
        b.add_column(sa.Column('industry', STR(), nullable=True))
        b.add_column(sa.Column('email_pattern', STR(), nullable=True))
        b.add_column(sa.Column('pattern_confidence', sa.Integer(), nullable=True))
        b.add_column(sa.Column('pattern_evidence', sa.JSON(), nullable=False, server_default='{}'))
        b.add_column(sa.Column('last_enriched_at', UTC(), nullable=True))
    with op.batch_alter_table('contact', schema=None) as b:
        b.add_column(sa.Column('found_by_provider', STR(), nullable=True))
        b.add_column(sa.Column('found_by_key', STR(), nullable=True))
        b.add_column(sa.Column('found_by_actor', STR(), nullable=True))
        b.add_column(sa.Column('found_at', UTC(), nullable=True))
        b.add_column(sa.Column('verification_status', STR(), nullable=True))

    op.create_table('company_provider_run', *_base(),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('provider', STR(), nullable=False),
        sa.Column('key_label', STR(), nullable=True),
        sa.Column('queried_at', UTC(), nullable=False),
        sa.Column('status', STR(), nullable=False),
        sa.Column('credits', sa.Float(), nullable=False),
        sa.Column('cost_usd', sa.Float(), nullable=False),
        sa.Column('candidates', sa.JSON(), nullable=False),
        sa.Column('note', STR(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['company.id']),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_company_provider_run_company_id', 'company_provider_run', ['company_id'])
    op.create_index('ix_company_provider_run_provider', 'company_provider_run', ['provider'])

    op.create_table('provider_key_state', *_base(),
        sa.Column('provider', STR(), nullable=False),
        sa.Column('key_label', STR(), nullable=False),
        sa.Column('disabled_at', UTC(), nullable=True),
        sa.Column('disabled_reason', STR(), nullable=True),
        sa.Column('monthly_limit', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'key_label'))

    op.create_table('provider_usage', *_base(),
        sa.Column('provider', STR(), nullable=False),
        sa.Column('key_label', STR(), nullable=False),
        sa.Column('period', STR(), nullable=False),
        sa.Column('credits', sa.Float(), nullable=False),
        sa.Column('cost_usd', sa.Float(), nullable=False),
        sa.Column('calls', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'key_label', 'period'))

    op.create_table('provider_call', *_base(),
        sa.Column('provider', STR(), nullable=False),
        sa.Column('key_label', STR(), nullable=True),
        sa.Column('endpoint', STR(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=True),
        sa.Column('credits', sa.Float(), nullable=False),
        sa.Column('cost_usd', sa.Float(), nullable=False),
        sa.Column('ok', sa.Boolean(), nullable=False),
        sa.Column('result', STR(), nullable=False),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_provider_call_provider', 'provider_call', ['provider'])
    op.create_index('ix_provider_call_company_id', 'provider_call', ['company_id'])


def downgrade() -> None:
    op.drop_table('provider_call')
    op.drop_table('provider_usage')
    op.drop_table('provider_key_state')
    op.drop_table('company_provider_run')
    with op.batch_alter_table('contact', schema=None) as b:
        for c in ('verification_status', 'found_at', 'found_by_actor', 'found_by_key',
                  'found_by_provider'):
            b.drop_column(c)
    with op.batch_alter_table('company', schema=None) as b:
        for c in ('last_enriched_at', 'pattern_evidence', 'pattern_confidence', 'email_pattern',
                  'industry', 'domain_source'):
            b.drop_column(c)
