"""Performance evidence must expose regressions, noise and incomplete comparisons."""

import pytest

from scripts.bench_matrix import comparison, revision


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
