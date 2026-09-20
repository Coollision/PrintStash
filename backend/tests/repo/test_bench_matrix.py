"""Performance evidence must expose regressions, noise and incomplete comparisons."""

import pytest

from scripts.bench_matrix import (
    Profile,
    benchmark_cases,
    benchmark_plan,
    compare_queue_contracts,
    comparison,
    container_measurement_script,
    container_resources,
    measure_case,
    preview_comparison_mode,
    revision,
)


def _report(value):
    return {
        "saved_seconds": value,
        "total_seconds": value,
        "navigation_latency": {"p95_ms": value},
        "server_tree_cpu_seconds": value,
        "sampled_peak_server_tree_rss_bytes": value,
        "container_memory_peak_bytes": value,
    }


def _gcode_report(value):
    return {
        "total_seconds": value,
        "parse_latency": {"p95_ms": value},
        "process_cpu_seconds": value,
        "process_peak_rss_bytes": value,
        "container_memory_peak_bytes": value,
    }


def _archive_report(value):
    return {
        "total_seconds": value,
        "archive_latency": {"p95_ms": value},
        "process_cpu_seconds": value,
        "process_peak_rss_bytes": value,
        "container_memory_peak_bytes": value,
    }


def _mesh_report(value):
    return {
        "total_seconds": value,
        "preview_latency": {"p95_ms": value},
        "process_cpu_seconds": value,
        "process_peak_rss_bytes": value,
        "container_memory_peak_bytes": value,
    }


def _similarity_report(value):
    return {
        "total_seconds": value,
        "fingerprint_latency": {"p95_ms": value},
        "verification_latency": {"p95_ms": value},
        "process_cpu_seconds": value,
        "process_peak_rss_bytes": value,
        "container_memory_peak_bytes": value,
    }


def _acquisition_report(value):
    return {
        "total_seconds": value,
        "download_latency": {
            "small": {"p95_ms": value},
            "large": {"p95_ms": value},
            "redirect": {"p95_ms": value},
        },
        "process_cpu_seconds": value,
        "process_peak_rss_bytes": value,
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

    def test_reads_container_cgroup_evidence(self, tmp_path):
        output = tmp_path / "run.json"
        output.with_suffix(".cpu-usec").write_text("1250000\n")
        output.with_suffix(".memory-peak").write_text("4096\n")

        assert container_resources(output) == {
            "container_cpu_seconds": 1.25,
            "container_memory_peak_bytes": 4096,
        }
        assert '"$@"' in container_measurement_script()

    def test_compares_gcode_resource_metrics(self):
        result = comparison(
            [_gcode_report(10)] * 7,
            [_gcode_report(11)] * 7,
            gcode=True,
        )
        assert set(result["metrics"]) == {
            "complete_s",
            "parse_p95_ms",
            "app_cpu_s",
            "app_rss_bytes",
            "container_peak_bytes",
        }
        assert result["metrics"]["parse_p95_ms"]["pairs_above_threshold"] == 7

    def test_refuses_a_case_with_two_measurement_protocols(self):
        with pytest.raises(ValueError, match="two measurement protocols"):
            comparison([_gcode_report(1)], [_gcode_report(1)], queue=True, gcode=True)

    def test_compares_archive_metrics(self):
        result = comparison(
            [_archive_report(10)] * 7,
            [_archive_report(11)] * 7,
            archive=True,
        )

        assert set(result["metrics"]) == {
            "complete_s",
            "archive_p95_ms",
            "app_cpu_s",
            "app_rss_bytes",
            "container_peak_bytes",
        }
        assert result["metrics"]["archive_p95_ms"]["pairs_above_threshold"] == 7

    def test_compares_mesh_preview_metrics(self):
        result = comparison(
            [_mesh_report(10)] * 7,
            [_mesh_report(11)] * 7,
            mesh=True,
        )

        assert set(result["metrics"]) == {
            "complete_s",
            "preview_p95_ms",
            "app_cpu_s",
            "app_rss_bytes",
            "container_peak_bytes",
        }
        assert result["metrics"]["preview_p95_ms"]["pairs_above_threshold"] == 7

    def test_compares_similarity_metrics(self):
        result = comparison(
            [_similarity_report(10)] * 7,
            [_similarity_report(11)] * 7,
            similarity=True,
        )

        assert set(result["metrics"]) == {
            "complete_s",
            "fingerprint_p95_ms",
            "verification_p95_ms",
            "app_cpu_s",
            "app_rss_bytes",
            "container_peak_bytes",
        }
        assert result["metrics"]["verification_p95_ms"]["pairs_above_threshold"] == 7

    def test_compares_acquisition_metrics(self):
        result = comparison(
            [_acquisition_report(10)] * 7,
            [_acquisition_report(11)] * 7,
            acquisition=True,
        )

        assert set(result["metrics"]) == {
            "complete_s",
            "small_p95_ms",
            "large_p95_ms",
            "redirect_p95_ms",
            "app_cpu_s",
            "app_rss_bytes",
            "container_peak_bytes",
        }
        assert result["metrics"]["large_p95_ms"]["pairs_above_threshold"] == 7


class TestLocalQuickBenchmark:
    def test_uses_one_bounded_profile(self):
        plan = benchmark_plan(
            quick=True,
            database=None,
            cpus=None,
            original="original",
            base="parent",
        )

        assert plan.dialects == ("sqlite",)
        assert plan.cpu_profiles == (4,)
        assert plan.ancestors == ("original",)
        assert plan.minimum_pairs == 3
        assert plan.maximum_pairs == 3
        assert plan.preserve_release_images is False

    def test_selects_first_wave_cases(self):
        corpus = {
            "archives": [
                {"name": "small.zip"},
                {"name": "large-mesh.zip"},
                {"name": "similarity.zip"},
            ]
        }

        assert [case["name"] for case in benchmark_cases(corpus, quick=True)] == [
            "large-mesh.zip",
            "gcode-parse",
            "archive-extract",
            "geometric-similarity",
        ]

    def test_rejects_missing_quick_case(self):
        with pytest.raises(ValueError, match="large-mesh.zip"):
            benchmark_cases({"archives": []}, quick=True)

    @pytest.mark.parametrize(
        ("database", "cpus"),
        [("sqlite", None), (None, 4)],
    )
    def test_rejects_quick_profile_overrides(self, database, cpus):
        with pytest.raises(ValueError, match="fixes the database"):
            benchmark_plan(
                quick=True,
                database=database,
                cpus=cpus,
                original="original",
                base="parent",
            )

    def test_retains_full_protocol(self):
        plan = benchmark_plan(
            quick=False,
            database=None,
            cpus=None,
            original="original",
            base="parent",
        )

        assert plan.dialects == ("sqlite", "postgres")
        assert plan.cpu_profiles == (2, 4)
        assert plan.ancestors == ("original", "parent")
        assert plan.minimum_pairs == 7
        assert plan.maximum_pairs == 14
        assert plan.preserve_release_images is True

    def test_runs_three_alternating_pairs(self, tmp_path):
        class FakeProfile:
            dialect = "sqlite"
            cpus = 4
            evidence = tmp_path

            def __init__(self):
                self.names = []

            def run(
                self,
                image,
                name,
                archive,
                reference,
                *,
                preview_comparison,
            ):
                self.names.append(name)
                return _report(1)

        profile = FakeProfile()
        result = measure_case(
            profile,
            {"name": "large-mesh.zip"},
            "original",
            "head",
            {
                "original": {"benchmark_id": "base-image"},
                "head": {"benchmark_id": "head-image"},
            },
            minimum_pairs=3,
            maximum_pairs=3,
        )

        assert result["pairs"] == 3
        assert len(profile.names) == 8

    def test_refuses_github_actions(self, monkeypatch, capsys):
        from scripts import bench_matrix

        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setattr(
            "sys.argv",
            [
                "bench_matrix.py",
                "--head",
                "a" * 40,
                "--output",
                "/tmp/unused-benchmark",
            ],
        )

        with pytest.raises(SystemExit, match="2"):
            bench_matrix.main()

        assert "must run on a local host" in capsys.readouterr().err


class TestProfilePreviewComparison:
    def test_passes_quality_mode_to_complete_import(self, monkeypatch, tmp_path):
        from scripts import bench_matrix

        evidence = tmp_path / "evidence"
        (evidence / "runs").mkdir(parents=True)
        reference = evidence / "runs" / "reference.json"
        reference.write_text("{}")
        commands = []

        def fake_command(args, *, log=None):
            commands.append(args)
            if log is not None:
                log.with_suffix(".json").write_text("{}")
                log.with_suffix(".cpu-usec").write_text("1000000\n")
                log.with_suffix(".memory-peak").write_text("4096\n")
            return ""

        monkeypatch.setattr(bench_matrix, "command", fake_command)
        profile = Profile(
            evidence=evidence,
            dialect="sqlite",
            cpus=2,
            network="isolated",
            env_file=tmp_path / "unused.env",
            database_container=None,
        )

        profile.run(
            "image",
            "case",
            {"name": "large-mesh.zip", "similarity": False},
            reference,
            preview_comparison="quality",
        )

        command = commands[0]
        index = command.index("--preview-comparison")
        assert command[index + 1] == "quality"


class TestPreviewComparisonMode:
    def test_uses_approved_quality_for_the_original_renderer(self):
        assert preview_comparison_mode("original", "original") == "quality"

    def test_requires_identical_bytes_for_the_immediate_parent(self):
        assert preview_comparison_mode("parent", "original") == "bytes"


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
        assert result["metrics"]["complete_s"]["paired_delta_percent"] == 0

    @pytest.mark.parametrize("difference", ["missing", "changed"])
    def test_rejects_non_equivalent_queue_outcomes(self, difference):
        before = {
            "measurement_protocol": "durable-queue-steady-v1",
            "scope": "queue repositories",
            "database": {"dialect": "sqlite", "version": "3.50.4"},
            "accepted_count": 4,
            "completed_count": 4,
            "rollback_orphans": 0,
            "duplicate_claims": 0,
            "fault_injection": "not_run",
        }
        after = dict(before)
        if difference == "missing":
            del after["completed_count"]
        else:
            after["completed_count"] = 3
        with pytest.raises(ValueError, match="completed_count"):
            compare_queue_contracts(before, after)

    @pytest.mark.parametrize("protocol", ["durable-queue-baseline-v1", "unknown"])
    def test_refuses_fault_injection_timings(self, protocol):
        report = {"measurement_protocol": protocol}
        with pytest.raises(ValueError, match="steady-state protocol"):
            compare_queue_contracts(report, report)
