"""Feedback on several screens: feedback.area -> feedback.areas (a JSON list).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-11 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('feedback', schema=None) as batch_op:
        batch_op.add_column(sa.Column('areas', sa.JSON(), nullable=True))
    # One area becomes a one-item list; no area becomes an empty list.
    op.execute("UPDATE feedback SET areas = CASE WHEN area IS NULL THEN '[]' ELSE json_array(area) END")
    with op.batch_alter_table('feedback', schema=None) as batch_op:
        batch_op.alter_column('areas', existing_type=sa.JSON(), nullable=False)
        batch_op.drop_column('area')


def downgrade() -> None:
    with op.batch_alter_table('feedback', schema=None) as batch_op:
        batch_op.add_column(sa.Column('area', sa.String(length=40), nullable=True))
    # Only the first area survives a downgrade.
    op.execute("UPDATE feedback SET area = json_extract(areas, '$[0]')")
    with op.batch_alter_table('feedback', schema=None) as batch_op:
        batch_op.drop_column('areas')
