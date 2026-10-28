"""Career Profile (milestone 8): capability assessment, background, preferences, constraints,
context and the resumes table.

The single `ai_experience` answer is copied into the Machine Learning and AI / LLMs ratings and
then dropped. Every profile is un-confirmed (the other three ratings and years of experience are
still missing), and so is its gap analysis.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-17 21:12:15.042031
"""
import json

from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

profiles = sa.table(
    'profiles',
    sa.column('user_id', sa.String),
    sa.column('ai_experience', sa.String),
    sa.column('capabilities', sa.JSON),
    sa.column('confirmed', sa.Boolean),
)


def upgrade() -> None:
    op.create_table('resumes',
    sa.Column('user_id', sa.String(length=255), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('stored_path', sa.String(length=1000), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('draft', sa.JSON(), nullable=True),
    sa.Column('data', sa.JSON(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('uploaded_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('user_id')
    )
    with op.batch_alter_table('profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('years_experience', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('capabilities', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('learning_preferences', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('constraints', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('additional_context', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('resume_skipped', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('field_sources', sa.JSON(), nullable=True))

    conn = op.get_bind()
    for user_id, level in conn.execute(sa.select(profiles.c.user_id, profiles.c.ai_experience)).all():
        caps = {"machine_learning": level, "ai_llms": level} if level else None
        conn.execute(profiles.update().where(profiles.c.user_id == user_id).values(capabilities=caps, confirmed=False))
    op.execute("UPDATE gap_analyses SET confirmed = 0")

    with op.batch_alter_table('profiles', schema=None) as batch_op:
        batch_op.drop_column('ai_experience')


def downgrade() -> None:
    with op.batch_alter_table('profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ai_experience', sa.VARCHAR(length=20), nullable=True))

    conn = op.get_bind()
    for user_id, caps in conn.execute(sa.select(profiles.c.user_id, profiles.c.capabilities)).all():
        caps = json.loads(caps) if isinstance(caps, str) else caps
        level = (caps or {}).get("ai_llms") or (caps or {}).get("machine_learning")
        conn.execute(profiles.update().where(profiles.c.user_id == user_id).values(ai_experience=level))

    with op.batch_alter_table('profiles', schema=None) as batch_op:
        batch_op.drop_column('field_sources')
        batch_op.drop_column('resume_skipped')
        batch_op.drop_column('additional_context')
        batch_op.drop_column('constraints')
        batch_op.drop_column('learning_preferences')
        batch_op.drop_column('capabilities')
        batch_op.drop_column('years_experience')

    op.drop_table('resumes')
