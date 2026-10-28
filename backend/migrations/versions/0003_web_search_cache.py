"""Web search cache (shared first-pass results per skill, level and domain) and approved web
resources that are candidates for the knowledge base.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-25 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('web_search_cache',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('skill', sa.String(length=200), nullable=False),
    sa.Column('level', sa.String(length=20), nullable=False),
    sa.Column('domain', sa.String(length=200), nullable=False),
    sa.Column('results', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('skill', 'level', 'domain')
    )
    op.create_table('web_resource_candidates',
    sa.Column('resource_id', sa.String(length=80), nullable=False),
    sa.Column('resource', sa.JSON(), nullable=False),
    sa.Column('gaps', sa.JSON(), nullable=False),
    sa.Column('approvals', sa.Integer(), nullable=False),
    sa.Column('first_approved_at', sa.DateTime(), nullable=False),
    sa.Column('last_approved_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('resource_id')
    )


def downgrade() -> None:
    op.drop_table('web_resource_candidates')
    op.drop_table('web_search_cache')
