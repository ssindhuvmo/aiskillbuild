import logging
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from core.config import BACKEND_DIR, DATABASE_URL

log = logging.getLogger(__name__)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

BASELINE = "0001"  # the schema made by create_all before Alembic (milestones 1-7)


class Base(DeclarativeBase):
    pass


def _alembic_config():
    from alembic.config import Config

    return Config(str(BACKEND_DIR / "alembic.ini"))


def backup_path(db_file: Path) -> Path:
    return db_file.with_name(f"{db_file.stem}.backup{db_file.suffix}")


def _backup(db_file: Path) -> None:
    """Copy the database before migrating it, so a failed migration can be rolled back. The first
    backup is kept: a later run never overwrites it."""
    target = backup_path(db_file)
    if target.exists():
        log.info("Database backup already exists at %s; leaving it unchanged.", target)
        return
    src, dst = sqlite3.connect(db_file), sqlite3.connect(target)
    try:
        src.backup(dst)  # the SQLite backup API also copies what is still in the WAL file
    finally:
        src.close()
        dst.close()
    log.info("Backed up the database to %s before migrating.", target)


def init_db() -> None:
    """Bring the schema up to date with Alembic. A database made before Alembic (tables but no
    alembic_version) is stamped at the baseline first. A file database is backed up before any
    pending migration runs."""
    from alembic import command
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    from core import models  # noqa: F401  (register tables)

    config = _alembic_config()
    head = ScriptDirectory.from_config(config).get_current_head()
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        current = MigrationContext.configure(conn).get_current_revision()
    if current == head:
        return
    db_file = engine.url.database
    if engine.url.get_backend_name() == "sqlite" and db_file and db_file != ":memory:" and tables:
        _backup(Path(db_file))
    with engine.begin() as conn:
        config.attributes["connection"] = conn
        if current is None and "users" in tables:
            command.stamp(config, BASELINE)
        command.upgrade(config, "head")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
