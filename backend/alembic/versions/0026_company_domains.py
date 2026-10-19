"""company domains: email domain, known domains with MX status, and the domain a provider run searched

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-19 17:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

import app.models.base  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = '0026'
down_revision: Union[str, Sequence[str], None] = '0025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('company', schema=None) as b:
        b.add_column(sa.Column('email_domain', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        b.add_column(sa.Column('domains', sa.JSON(), nullable=False, server_default='{}'))
    with op.batch_alter_table('company_provider_run', schema=None) as b:
        b.add_column(sa.Column('domain', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('company_provider_run', schema=None) as b:
        b.drop_column('domain')
    with op.batch_alter_table('company', schema=None) as b:
        b.drop_column('domains')
        b.drop_column('email_domain')
