"""The baseline diagnostic must recover the same real job after process death."""

import json
import signal

import pytest

from scripts.bench_queue import run


class TestQueueBenchmark:
    @pytest.mark.parametrize(
        "database", ["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)]
    )
    def test_recovers_a_terminated_worker_without_losing_jobs(self, tmp_path, database):
        output = tmp_path / "queue.json"

        report = run(output, database=database, count=3, idle_seconds=1)

        assert report["accepted_count"] == report["completed_count"] == 4
        assert report["rollback_orphans"] == 0
        assert report["duplicate_claims"] == 0
        assert report["stale_completion_rejected"] is True
        assert report["terminated_worker_exit_code"] == -signal.SIGKILL
        assert report["recovery_seconds"] > 0
        assert report["claim"]["count"] == 3
        assert json.loads(output.read_text()) == report
