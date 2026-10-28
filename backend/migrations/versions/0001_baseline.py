"""Baseline: the schema as of milestone 7, when tables were made with create_all.

An existing pre-Alembic database is stamped at this revision (core/db.py::init_db).

Revision ID: 0001
Revises:
Create Date: 2026-10-17 21:11:45.378962
"""
from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('user_id', sa.String(length=255), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=True),
    sa.Column('picture', sa.String(length=1000), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('agent_outputs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=255), nullable=False),
    sa.Column('agent', sa.String(length=32), nullable=False),
    sa.Column('output', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('agent_outputs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agent_outputs_user_id'), ['user_id'], unique=False)

    op.create_table('approved_lists',
    sa.Column('user_id', sa.String(length=255), nullable=False),
    sa.Column('items', sa.JSON(), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.Column('approved_via', sa.String(length=32), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('conversations',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=255), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('messages', sa.JSON(), nullable=False),
    sa.Column('state', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_conversations_user_id'), ['user_id'], unique=False)

    op.create_table('gap_analyses',
    sa.Column('user_id', sa.String(length=255), nullable=False),
    sa.Column('analysis', sa.JSON(), nullable=False),
    sa.Column('corrections', sa.JSON(), nullable=False),
    sa.Column('profile_snapshot', sa.JSON(), nullable=False),
    sa.Column('confirmed', sa.Boolean(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('profiles',
    sa.Column('user_id', sa.String(length=255), nullable=False),
    sa.Column('current_role', sa.String(length=200), nullable=True),
    sa.Column('target_role', sa.String(length=200), nullable=True),
    sa.Column('ai_experience', sa.String(length=20), nullable=True),
    sa.Column('domain', sa.String(length=200), nullable=True),
    sa.Column('hours_per_week', sa.Integer(), nullable=True),
    sa.Column('confirmed', sa.Boolean(), nullable=False),
    sa.Column('inferred_skills', sa.JSON(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('resource_lists',
    sa.Column('user_id', sa.String(length=255), nullable=False),
    sa.Column('items', sa.JSON(), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('roadmaps',
    sa.Column('user_id', sa.String(length=255), nullable=False),
    sa.Column('roadmap', sa.JSON(), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('user_id')
    )


def downgrade() -> None:
    op.drop_table('roadmaps')
    op.drop_table('resource_lists')
    op.drop_table('profiles')
    op.drop_table('gap_analyses')
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_conversations_user_id'))

    op.drop_table('conversations')
    op.drop_table('approved_lists')
    with op.batch_alter_table('agent_outputs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agent_outputs_user_id'))

    op.drop_table('agent_outputs')
    op.drop_table('users')
