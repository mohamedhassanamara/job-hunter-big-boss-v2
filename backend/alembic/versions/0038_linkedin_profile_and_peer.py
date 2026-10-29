"""linkedin_profile (the captured profile snapshot) and the role-based LinkedIn groups

LinkedIn people are classified by ROLE only (hiring_team | lead | recruiter | peer); being an alum
is the separate `linkedin_outreach.alumni` flag. Data only for the old groups: the column is
VARCHAR(32) with no CHECK constraint, so there is no batch alter.

  other   -> peer
  alumni  -> peer, alumni = 1

Revision ID: 0038
Revises: 0037
Create Date: 2026-10-29 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: Union[str, Sequence[str], None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "linkedin_profile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=False),
        sa.Column("profile_url", sa.String(), nullable=False, server_default=""),
        sa.Column("public_id", sa.String(), nullable=False, server_default=""),
        sa.Column("headline", sa.String(), nullable=False, server_default=""),
        sa.Column("current_title", sa.String(), nullable=False, server_default=""),
        sa.Column("current_company", sa.String(), nullable=False, server_default=""),
        sa.Column("company_linkedin_url", sa.String(), nullable=True),
        sa.Column("location", sa.String(), nullable=False, server_default=""),
        sa.Column("connection_degree", sa.Integer(), nullable=True),
        sa.Column("education", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("experience", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("about", sa.Text(), nullable=False, server_default=""),
        sa.Column("badges", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("persona", sa.String(length=32), nullable=False, server_default="peer"),
        sa.Column("persona_source", sa.String(), nullable=False, server_default="auto"),
        sa.Column("persona_reasons", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_alum", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("capture_sources", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("captured_at", sa.DateTime(), nullable=True),
        sa.Column("extension_version", sa.String(), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["contact_id"], ["contact.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contact_id"),
    )
    op.create_index("ix_linkedin_profile_public_id", "linkedin_profile", ["public_id"])

    # Order matters: `alumni` rows are moved first, so they never meet the `other` rule.
    op.execute("UPDATE linkedin_outreach SET \"group\" = 'peer', alumni = 1 "
               "WHERE \"group\" = 'alumni'")
    op.execute("UPDATE linkedin_outreach SET \"group\" = 'peer' WHERE \"group\" = 'other'")


def downgrade() -> None:
    # peers that are alumni go back to the `alumni` group, the rest to `other`
    op.execute("UPDATE linkedin_outreach SET \"group\" = 'alumni' "
               "WHERE \"group\" = 'peer' AND alumni = 1")
    op.execute("UPDATE linkedin_outreach SET \"group\" = 'other' WHERE \"group\" = 'peer'")
    op.drop_index("ix_linkedin_profile_public_id", table_name="linkedin_profile")
    op.drop_table("linkedin_profile")
