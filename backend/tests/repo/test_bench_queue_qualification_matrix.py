"""The queue qualification matrix bounds identities and database evidence."""

import sqlite3

import pytest

from scripts.bench_queue_qualification_matrix import (
    CandidateProfile,
    postgres_database_bytes,
    sqlite_database_bytes,
)


def test_reads_real_sqlite_page_allocation(tmp_path):
    database = tmp_path / "candidate.sqlite"
    assert sqlite_database_bytes(database) == 0
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE queue_probe (value TEXT NOT NULL)")
        connection.execute("INSERT INTO queue_probe VALUES ('measured')")

    assert sqlite_database_bytes(database) > 0


def test_rejects_untrusted_postgres_database_name_before_docker(monkeypatch):
    monkeypatch.setattr(
        "scripts.bench_queue_qualification_matrix.command",
        lambda _args: pytest.fail("invalid identity reached Docker"),
    )

    with pytest.raises(ValueError, match="database name is invalid"):
        postgres_database_bytes("database-container", "postgres'; DROP DATABASE postgres")


def test_rejects_unknown_candidate_before_container_execution(tmp_path):
    profile = CandidateProfile(
        evidence=tmp_path,
        database="sqlite",
        cpus=2,
        network="isolated",
        image="sha256:candidate",
        password="secret",
        database_container=None,
    )

    with pytest.raises(ValueError, match="unsupported queue candidate"):
        profile.run("unknown", "run", recovery=False)
