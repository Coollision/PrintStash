"""Benchmark inspection uses isolated real databases for both supported dialects."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app.db.url import normalize_database_url
from scripts.bench_database import (
    database_record,
    disposable_database,
    pending_enrichment,
)
from tests.containers import postgres_url


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)])
def database(request, tmp_path):
    with disposable_database(tmp_path, request.param) as engine:
        yield engine


class TestEnrichmentInspection:
    def test_counts_only_background_analysis(self, database):
        with database.begin() as db:
            db.exec_driver_sql(
                "CREATE TABLE artifact_analysis_generations "
                "(state TEXT, processing_policy TEXT)"
            )
            db.exec_driver_sql(
                "INSERT INTO artifact_analysis_generations VALUES "
                "('pending', 'background'), ('running', 'foreground'), "
                "('failed', 'background'), ('failed', 'foreground')"
            )
        with database.connect() as db:
            assert pending_enrichment(db) == (1, {"artifact_analysis_generations": 1})

    def test_includes_similarity_only_when_requested(self, database):
        with database.begin() as db:
            db.exec_driver_sql("CREATE TABLE similarity_runs (state TEXT)")
            db.exec_driver_sql("INSERT INTO similarity_runs VALUES ('queued')")
        with database.connect() as db:
            assert pending_enrichment(db) == (0, {})
            assert pending_enrichment(db, similarity=True) == (
                1,
                {"similarity_runs": 0},
            )

    def test_counts_projection_requests_without_a_state(self, database):
        with database.begin() as db:
            db.exec_driver_sql("CREATE TABLE search_projection_requests (id INTEGER)")
            db.exec_driver_sql("INSERT INTO search_projection_requests VALUES (1), (2)")
        with database.connect() as db:
            assert pending_enrichment(db) == (2, {})

    def test_records_database_version_without_connection_details(self, database):
        with database.connect() as db:
            record = database_record(db)
        assert record["backend"] == database.dialect.name
        assert record["server_version"]
        assert set(record) == {"backend", "server_version"}


class TestDisposableDatabase:
    @pytest.mark.parametrize(
        "dialect", ["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)]
    )
    def test_isolates_each_run(self, tmp_path, dialect):
        first_root, second_root = tmp_path / "first", tmp_path / "second"
        first_root.mkdir()
        second_root.mkdir()
        with disposable_database(first_root, dialect) as first:
            with first.begin() as db:
                db.exec_driver_sql("CREATE TABLE sentinel (value INTEGER)")
            with disposable_database(second_root, dialect) as second:
                assert "sentinel" not in inspect(second).get_table_names()
            assert "sentinel" in inspect(first).get_table_names()

    def test_refuses_an_existing_sqlite_file(self, tmp_path):
        path = tmp_path / "vault.sqlite"
        path.write_bytes(b"existing vault")
        with pytest.raises(FileExistsError):
            with disposable_database(tmp_path, "sqlite"):
                pytest.fail("existing file was accepted")
        assert path.read_bytes() == b"existing vault"

    @pytest.mark.postgres
    def test_removes_its_postgres_database_after_failure(self, tmp_path):
        with pytest.raises(RuntimeError, match="interrupted benchmark"):
            with disposable_database(tmp_path, "postgres") as engine:
                name = engine.url.database
                raise RuntimeError("interrupted benchmark")
        admin = create_engine(normalize_database_url(postgres_url()))
        try:
            with admin.connect() as db:
                assert (
                    db.execute(
                        text("SELECT COUNT(*) FROM pg_database WHERE datname = :name"),
                        {"name": name},
                    ).scalar_one()
                    == 0
                )
        finally:
            admin.dispose()

    def test_rejects_an_unsupported_database(self, tmp_path: Path):
        with pytest.raises(ValueError, match="Unsupported benchmark database"):
            with disposable_database(tmp_path, "mysql"):
                pytest.fail("unsupported dialect was accepted")
