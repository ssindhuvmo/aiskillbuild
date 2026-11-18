"""Job Match (milestone 12): job_searches, job_marks.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-09 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('job_marks',
    sa.Column('user_id', sa.String(length=255), nullable=False),
    sa.Column('job_id', sa.String(length=40), nullable=False),
    sa.Column('job', sa.JSON(), nullable=False),
    sa.Column('saved', sa.Boolean(), nullable=False),
    sa.Column('applied', sa.Boolean(), nullable=False),
    sa.Column('applied_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('user_id', 'job_id')
    )
    op.create_table('job_searches',
    sa.Column('user_id', sa.String(length=255), nullable=False),
    sa.Column('query', sa.JSON(), nullable=False),
    sa.Column('jobs', sa.JSON(), nullable=False),
    sa.Column('notice', sa.Text(), nullable=True),
    sa.Column('found_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('user_id')
    )


def downgrade() -> None:
    op.drop_table('job_searches')
    op.drop_table('job_marks')
