"""Performance evidence must expose regressions, noise and incomplete comparisons."""

import pytest

from scripts.bench_matrix import compare_queue_contracts, comparison, revision


def _report(value):
    return {
        "saved_seconds": value,
        "total_seconds": value,
        "navigation_latency": {"p95_ms": value},
        "server_tree_cpu_seconds": value,
        "sampled_peak_server_tree_rss_bytes": value,
        "container_memory_peak_bytes": value,
    }


class TestPerformanceComparison:
    def test_flags_a_repeatable_regression(self):
        result = comparison([_report(10)] * 7, [_report(12)] * 7)
        assert result["pairs"] == 7
        assert result["noisy"] is False
        for metric in result["metrics"].values():
            assert metric["paired_delta_percent"] == pytest.approx(20)
            assert metric["pairs_above_threshold"] == 7

    def test_requires_more_samples_when_baseline_is_noisy(self):
        reports = [_report(value) for value in (5, 20, 5, 20, 5, 20, 5)]
        result = comparison(reports, reports)
        assert result["noisy"] is True
        assert result["metrics"]["complete_s"]["paired_delta_percent"] == 0

    @pytest.mark.parametrize("before,after", [([], []), ([_report(1)], [])])
    def test_refuses_incomplete_pairs(self, before, after):
        with pytest.raises(ValueError, match="complete paired runs"):
            comparison(before, after)

    @pytest.mark.parametrize(
        "value", [None, True, "10", 0, -1, float("nan"), float("inf")]
    )
    def test_refuses_invalid_measurements(self, value):
        with pytest.raises(ValueError, match="Invalid benchmark metric"):
            comparison([_report(10)], [_report(value)])

    def test_refuses_missing_measurements(self):
        report = _report(10)
        del report["navigation_latency"]
        with pytest.raises(ValueError, match="Missing benchmark metric"):
            comparison([_report(10)], [report])


class TestBenchmarkRevision:
    @pytest.mark.parametrize(
        "value", ["main", "--help", "12345678", "a" * 40 + "; echo unsafe"]
    )
    def test_refuses_ambiguous_or_option_like_revisions(self, value):
        with pytest.raises(ValueError, match="full lowercase commit hashes"):
            revision(value)


class TestQueueComparison:
    def test_distinguishes_latency_from_resource_regressions(self):
        before = {
            "total_seconds": 120,
            "recovery_seconds": 120,
            "acceptance": {"p95_ms": 10},
            "claim": {"p95_ms": 10},
            "completion": {"p95_ms": 10},
            "idle": {"cpu_seconds": 1},
            "coordinator_cpu_seconds": 1,
            "container_memory_peak_bytes": 1000,
        }
        after = {
            **before,
            "claim": {"p95_ms": 10.6},
            "idle": {"cpu_seconds": 1.06},
        }
        result = comparison([before] * 7, [after] * 7, queue=True)
        assert result["metrics"]["claim_p95_ms"]["pairs_above_threshold"] == 7
        assert result["metrics"]["idle_cpu_s"]["pairs_above_threshold"] == 0
        assert result["metrics"]["recovery_s"]["paired_delta_percent"] == 0

    @pytest.mark.parametrize("difference", ["missing", "changed"])
    def test_rejects_non_equivalent_queue_outcomes(self, difference):
        before = {
            "measurement_protocol": "durable-queue-baseline-v1",
            "scope": "queue repositories",
            "database": {"dialect": "sqlite", "version": "3.50.4"},
            "accepted_count": 4,
            "completed_count": 4,
            "rollback_orphans": 0,
            "duplicate_claims": 0,
            "stale_completion_rejected": True,
            "production_lease_seconds": 120,
            "terminated_worker_exit_code": -9,
        }
        after = dict(before)
        if difference == "missing":
            del after["completed_count"]
        else:
            after["completed_count"] = 3
        with pytest.raises(ValueError, match="completed_count"):
            compare_queue_contracts(before, after)
