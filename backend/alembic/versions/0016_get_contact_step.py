"""get contact step: verification on contacts, contact search on companies, lookup queue removed

The old per-company lookup queue (company_lookup) becomes company.contact_search:
never → never, not_found → not_found, anything else (queued, skipped, found) → none; its date
and notes are kept. Contact tiers and sources are renamed:
apollo_dump → imported, lookup_found → found, lookup_queued → to_get (tiers);
apollo_lookup → found (sources). Contacts you entered by hand count as verified on entry.

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-30 19:15:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

import app.models.base  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = '0016'
down_revision: Union[str, Sequence[str], None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('contact', schema=None) as batch_op:
        batch_op.add_column(sa.Column('verified_at', app.models.base.UTCDateTime(), nullable=True))
        batch_op.add_column(sa.Column('verified_how', sqlmodel.sql.sqltypes.AutoString(),
                                      nullable=True))
        batch_op.add_column(sa.Column('left_at', app.models.base.UTCDateTime(), nullable=True))
        batch_op.add_column(sa.Column('left_reason', sqlmodel.sql.sqltypes.AutoString(),
                                      nullable=True))
    with op.batch_alter_table('company', schema=None) as batch_op:
        batch_op.add_column(sa.Column('contact_search', sa.String(length=32), nullable=False,
                                      server_default='none'))
        batch_op.add_column(sa.Column('contact_search_at', app.models.base.UTCDateTime(),
                                      nullable=True))
        batch_op.add_column(sa.Column('contact_search_notes', sa.Text(), nullable=False,
                                      server_default=''))

    # The lookup queue's answers move to the company.
    op.execute("""
        UPDATE company SET
          contact_search = (SELECT l.status FROM company_lookup l
                            WHERE l.company_id = company.id),
          contact_search_at = (SELECT coalesce(l.resolved_at, l.updated_at) FROM company_lookup l
                               WHERE l.company_id = company.id),
          contact_search_notes = coalesce((SELECT l.notes FROM company_lookup l
                                           WHERE l.company_id = company.id), '')
        WHERE id IN (SELECT company_id FROM company_lookup
                     WHERE status IN ('never', 'not_found'))
    """)
    op.execute("UPDATE application SET contact_tier = 'imported' "
               "WHERE contact_tier = 'apollo_dump'")
    op.execute("UPDATE application SET contact_tier = 'found' WHERE contact_tier = 'lookup_found'")
    op.execute("UPDATE application SET contact_tier = 'to_get' "
               "WHERE contact_tier = 'lookup_queued'")
    op.execute("UPDATE contact SET source = 'found' WHERE source = 'apollo_lookup'")
    # Contacts you entered yourself were verified when you entered them.
    op.execute("UPDATE contact SET verified_at = created_at, verified_how = 'entered' "
               "WHERE source IN ('found', 'manual')")

    with op.batch_alter_table('company_lookup', schema=None) as batch_op:
        batch_op.drop_index('ix_company_lookup_company_id')
        batch_op.drop_index('ix_company_lookup_status')
    op.drop_table('company_lookup')


def downgrade() -> None:
    op.create_table(
        'company_lookup',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', app.models.base.UTCDateTime(), nullable=False),
        sa.Column('updated_at', app.models.base.UTCDateTime(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('queued_at', app.models.base.UTCDateTime(), nullable=False),
        sa.Column('resolved_at', app.models.base.UTCDateTime(), nullable=True),
        sa.Column('snoozed_until', app.models.base.UTCDateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['company.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('company_lookup', schema=None) as batch_op:
        batch_op.create_index('ix_company_lookup_company_id', ['company_id'], unique=True)
        batch_op.create_index('ix_company_lookup_status', ['status'], unique=False)
    op.execute("""
        INSERT INTO company_lookup (created_at, updated_at, company_id, status, priority,
                                    queued_at, resolved_at, notes)
        SELECT coalesce(contact_search_at, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP, id,
               contact_search, 0, coalesce(contact_search_at, CURRENT_TIMESTAMP),
               contact_search_at, contact_search_notes
        FROM company WHERE contact_search IN ('never', 'not_found')
    """)
    op.execute("UPDATE application SET contact_tier = 'apollo_dump' "
               "WHERE contact_tier = 'imported'")
    op.execute("UPDATE application SET contact_tier = 'lookup_found' WHERE contact_tier = 'found'")
    op.execute("UPDATE application SET contact_tier = 'lookup_queued' "
               "WHERE contact_tier = 'to_get'")
    op.execute("UPDATE contact SET source = 'apollo_lookup' WHERE source IN ('found', 'hunter')")
    with op.batch_alter_table('company', schema=None) as batch_op:
        batch_op.drop_column('contact_search_notes')
        batch_op.drop_column('contact_search_at')
        batch_op.drop_column('contact_search')
    with op.batch_alter_table('contact', schema=None) as batch_op:
        batch_op.drop_column('left_reason')
        batch_op.drop_column('left_at')
        batch_op.drop_column('verified_how')
        batch_op.drop_column('verified_at')
