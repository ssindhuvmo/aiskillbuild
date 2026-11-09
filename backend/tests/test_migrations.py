"""Alembic migrations: head matches the models, the career-profile migration moves old data, and
init_db stamps and backs up a database made before Alembic."""
import json

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text

from core import db as dbmod
from core.db import Base, _alembic_config, backup_path


def _engine(path):
    return create_engine(f"sqlite:///{path}")


def _upgrade(engine, revision="head"):
    config = _alembic_config()
    with engine.begin() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, revision)


def test_head_matches_the_models(tmp_path):
    engine = _engine(tmp_path / "fresh.db")
    _upgrade(engine)
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []


def test_career_profile_migration_moves_ai_experience(tmp_path):
    engine = _engine(tmp_path / "old.db")
    _upgrade(engine, "0001")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (user_id, created_at) VALUES ('m1', '2026-01-01')"))
        conn.execute(text(
            "INSERT INTO profiles (user_id, current_role, target_role, ai_experience, domain, hours_per_week, "
            "confirmed, updated_at) VALUES ('m1', 'Backend Engineer', 'AI Engineer', 'Beginner', 'FinTech', 8, 1, "
            "'2026-01-01')"
        ))
    _upgrade(engine)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT capabilities, confirmed, current_role, resume_skipped FROM profiles")).one()
        columns = [r[1] for r in conn.execute(text("PRAGMA table_info(profiles)"))]
    assert json.loads(row[0]) == {"machine_learning": "Beginner", "ai_llms": "Beginner"}
    assert row[1] == 0 and row[2] == "Backend Engineer" and row[3] == 0
    assert "ai_experience" not in columns


@pytest.fixture()
def pre_alembic_db(tmp_path, monkeypatch):
    """A database as milestone 7 left it: the baseline tables without an alembic_version table."""
    path = tmp_path / "career_strategist.db"
    engine = _engine(path)
    _upgrade(engine, "0001")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE alembic_version"))
    monkeypatch.setattr(dbmod, "engine", engine)
    return path


def test_init_db_stamps_backs_up_and_upgrades(pre_alembic_db):
    dbmod.init_db()
    backup = backup_path(pre_alembic_db)
    assert backup.name == "career_strategist.backup.db" and backup.exists()
    with _engine(backup).connect() as conn:  # the backup is the database before migrating
        assert "ai_experience" in [r[1] for r in conn.execute(text("PRAGMA table_info(profiles)"))]
    with dbmod.engine.connect() as conn:
        assert MigrationContext.configure(conn).get_current_revision() == "0005"


def test_init_db_never_overwrites_an_existing_backup(pre_alembic_db):
    backup = backup_path(pre_alembic_db)
    backup.write_bytes(b"first backup")
    dbmod.init_db()
    assert backup.read_bytes() == b"first backup"
