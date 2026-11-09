"""Progress Review and Dashboard (milestone 11): skill_progress, progress_notes, readiness_history.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-09 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('progress_notes',
    sa.Column('user_id', sa.String(length=255), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('readiness_history',
    sa.Column('user_id', sa.String(length=255), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('score', sa.Integer(), nullable=False),
    sa.Column('covered', sa.Integer(), nullable=False),
    sa.Column('needed', sa.Integer(), nullable=False),
    sa.Column('completion', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('user_id', 'day')
    )
    op.create_table('skill_progress',
    sa.Column('user_id', sa.String(length=255), nullable=False),
    sa.Column('skill', sa.String(length=120), nullable=False),
    sa.Column('completed', sa.Boolean(), nullable=False),
    sa.Column('confidence', sa.Integer(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('user_id', 'skill')
    )


def downgrade() -> None:
    op.drop_table('skill_progress')
    op.drop_table('readiness_history')
    op.drop_table('progress_notes')
