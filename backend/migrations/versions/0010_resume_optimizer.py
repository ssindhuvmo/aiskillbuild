"""Resume Optimizer (milestone 13): tailored_resumes.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-18 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('tailored_resumes',
    sa.Column('user_id', sa.String(length=255), nullable=False),
    sa.Column('job_id', sa.String(length=40), nullable=False),
    sa.Column('job', sa.JSON(), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.Column('text', sa.JSON(), nullable=False),
    sa.Column('edits', sa.JSON(), nullable=True),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('notice', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('user_id', 'job_id')
    )


def downgrade() -> None:
    op.drop_table('tailored_resumes')
