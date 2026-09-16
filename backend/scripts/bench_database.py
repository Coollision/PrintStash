"""Disposable databases and read-only inspection for the import benchmark.

PostgreSQL uses the same test-container owner as the contract suite. No caller
can supply an existing vault URL: each run owns a fresh database and removes
only that database after the application has stopped.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Connection, Engine, make_url

from app.db.url import normalize_database_url


@contextmanager
def disposable_database(root: Path, dialect: str) -> Iterator[Engine]:
    if dialect == "sqlite":
        path = root / "vault.sqlite"
        path.touch(exist_ok=False)
        engine = create_engine(f"sqlite:///{path}")
        try:
            yield engine
        finally:
            engine.dispose()
        return
    if dialect != "postgres":
        raise ValueError(f"Unsupported benchmark database: {dialect}")

    # Lazy import keeps the default SQLite benchmark independent of Docker.
    from tests.containers import postgres_url

    base_url = make_url(normalize_database_url(postgres_url()))
    admin = create_engine(base_url, isolation_level="AUTOCOMMIT")
    name = "import_bench_" + uuid4().hex
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
        try:
            engine = create_engine(base_url.set(database=name))
            try:
                yield engine
            finally:
                engine.dispose()
        finally:
            with admin.connect() as connection:
                connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
    finally:
        admin.dispose()


def database_record(connection: Connection) -> dict:
    """Identify comparable database versions without publishing connection URLs."""
    return {
        "backend": connection.dialect.name,
        "server_version": list(connection.dialect.server_version_info or ()),
    }


def read_rows(connection: Connection, statement: str) -> list[tuple]:
    """Return portable, JSON-serializable rows from benchmark-owned queries."""
    return [tuple(row) for row in connection.exec_driver_sql(statement)]


def pending_enrichment(
    connection: Connection, *, similarity: bool = False
) -> tuple[int, dict[str, int]]:
    schema = inspect(connection)
    tables = set(schema.get_table_names())
    pending = 0
    failed = {}
    for table in (
        "artifact_analysis_generations",
        "thumbnail_generations",
        "search_projection_requests",
        "similarity_runs",
    ):
        if table not in tables or (table == "similarity_runs" and not similarity):
            continue
        columns = {column["name"] for column in schema.get_columns(table)}
        policy = (
            "processing_policy = 'background' AND "
            if "processing_policy" in columns
            else ""
        )
        condition = (
            policy + "state IN ('pending','queued','running','cancelling')"
            if "state" in columns
            else "1=1"
        )
        pending += connection.exec_driver_sql(
            f"SELECT COUNT(*) FROM {table} WHERE {condition}"
        ).scalar_one()
        if "state" in columns:
            failed[table] = connection.exec_driver_sql(
                f"SELECT COUNT(*) FROM {table} WHERE {policy}state = 'failed'"
            ).scalar_one()
    return pending, failed
