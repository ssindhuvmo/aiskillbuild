"""Alembic environment. Uses the app's engine, or a connection handed over in
config.attributes["connection"] (init_db and the tests pass one)."""
from alembic import context

from core import models  # noqa: F401  (register tables)
from core.db import Base, engine

target_metadata = Base.metadata


def _run(connection) -> None:
    # Batch mode lets SQLite alter and drop columns (it rebuilds the table).
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    _run(connection)
else:
    with engine.connect() as conn:
        _run(conn)
        conn.commit()
