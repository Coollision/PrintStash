"""The benchmark proves import completion against a fresh real application."""

import hashlib
import json
import zipfile

import pytest

from scripts.bench_import import run
from tests.factories.geometry import tetrahedron


class TestImportBenchmark:
    @pytest.mark.parametrize(
        "dialect", ["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)]
    )
    def test_benchmarks_a_complete_import(self, tmp_path, dialect):
        source = tetrahedron().export(file_type="stl")
        archive = tmp_path / "models.zip"
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("part.stl", source)
        output = tmp_path / "report.json"

        report = run(archive, output, 120, database=dialect)

        assert report["status"]["state"] == "completed"
        assert report["catalog"] == [(hashlib.sha256(source).hexdigest(), len(source))]
        assert report["geometry_catalog"][0][-1] == 4
        assert report["preview_pixel_catalog"][0][-1] == "ready"
        assert report["database"]["backend"] == (
            "postgresql" if dialect == "postgres" else "sqlite"
        )
        assert json.loads(output.read_text())["database"] == report["database"]
