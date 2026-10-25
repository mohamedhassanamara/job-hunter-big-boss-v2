"""job sources and source_urls

Revision ID: 0032
Revises: afe287de393c
Create Date: 2026-10-25 15:45:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

# revision identifiers, used by Alembic.
revision: str = '0032'
down_revision: Union[str, Sequence[str], None] = 'afe287de393c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sources', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('source_urls', sa.JSON(), nullable=True))

    conn = op.get_bind()
    # Populate existing rows
    rows = conn.execute(sa.text("SELECT id, source, url, duplicate_of_id, description FROM job")).fetchall()
    
    # 1. Backfill all canonical jobs
    for r in rows:
        j_id, j_src, j_url, dup_of, _ = r
        if not dup_of:
            s_list = json.dumps([str(j_src)])
            s_map = json.dumps({str(j_src): str(j_url)})
            conn.execute(
                sa.text("UPDATE job SET sources = :s_list, source_urls = :s_map WHERE id = :id"),
                {"s_list": s_list, "s_map": s_map, "id": j_id},
            )

    # 2. Merge existing duplicate rows into parent canonical rows
    for r in rows:
        j_id, j_src, j_url, dup_of, dup_desc = r
        if dup_of:
            parent = conn.execute(
                sa.text("SELECT id, sources, source_urls, description FROM job WHERE id = :p_id"),
                {"p_id": dup_of},
            ).fetchone()
            if parent:
                p_sources = json.loads(parent[1]) if parent[1] else []
                p_urls = json.loads(parent[2]) if parent[2] else {}
                p_desc = parent[3] or ""
                if str(j_src) not in p_sources:
                    p_sources.append(str(j_src))
                p_urls[str(j_src)] = str(j_url)
                
                # If duplicate description is longer, update parent
                new_desc = dup_desc if dup_desc and len(dup_desc) > len(p_desc) else p_desc
                conn.execute(
                    sa.text("UPDATE job SET sources = :s_list, source_urls = :s_map, description = :desc WHERE id = :id"),
                    {"s_list": json.dumps(p_sources), "s_map": json.dumps(p_urls), "desc": new_desc, "id": dup_of},
                )


def downgrade() -> None:
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.drop_column('source_urls')
        batch_op.drop_column('sources')
