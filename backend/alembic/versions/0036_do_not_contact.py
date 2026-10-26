"""do-not-contact: contact flag (reason, date) and the do_not_contact_rule list

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-26 14:30:36.482807

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

import app.models.base  # noqa: F401

revision: str = "0036"
down_revision: Union[str, Sequence[str], None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "do_not_contact_rule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("value", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("do_not_contact_rule", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_do_not_contact_rule_value"), ["value"], unique=True)
    with op.batch_alter_table("contact", schema=None) as batch_op:
        batch_op.add_column(sa.Column("do_not_contact", sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
        batch_op.add_column(sa.Column("dnc_reason", sqlmodel.sql.sqltypes.AutoString(),
                                      nullable=True))
        batch_op.add_column(sa.Column("dnc_at", app.models.base.UTCDateTime(), nullable=True))
        batch_op.create_index(batch_op.f("ix_contact_do_not_contact"), ["do_not_contact"],
                              unique=False)


def downgrade() -> None:
    with op.batch_alter_table("contact", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_contact_do_not_contact"))
        batch_op.drop_column("dnc_at")
        batch_op.drop_column("dnc_reason")
        batch_op.drop_column("do_not_contact")
    with op.batch_alter_table("do_not_contact_rule", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_do_not_contact_rule_value"))
    op.drop_table("do_not_contact_rule")
