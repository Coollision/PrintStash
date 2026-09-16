"""The benchmark proves import completion against a fresh real application."""

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from scripts.bench_import import run
from tests.factories.geometry import tetrahedron


class TestImportBenchmark:
    @pytest.mark.parametrize(
        "dialect",
        [
            "sqlite",
            pytest.param("postgres", marks=pytest.mark.postgres),
            pytest.param("postgres-managed", marks=pytest.mark.postgres),
        ],
    )
    def test_benchmarks_a_complete_import(self, tmp_path, dialect):
        source = tetrahedron().export(file_type="stl")
        gcode = (
            Path(__file__).parents[1] / "fixtures/real_prusa_mk4_spatula.gcode"
        ).read_bytes()
        archive = tmp_path / "models.zip"
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("part.stl", source)
            package.writestr("spatula.gcode", gcode)
        output = tmp_path / "report.json"

        postgres_admin_url = None
        if dialect == "postgres-managed":
            from sqlalchemy.engine import make_url

            from tests.containers import postgres_url

            postgres_admin_url = (
                make_url(postgres_url())
                .set(database="postgres")
                .render_as_string(hide_password=False)
            )
            dialect = "postgres"
        report = run(
            archive,
            output,
            120,
            database=dialect,
            postgres_admin_url=postgres_admin_url,
        )

        assert report["status"]["state"] == "completed"
        assert report["catalog"] == sorted(
            (hashlib.sha256(data).hexdigest(), len(data)) for data in (source, gcode)
        )
        geometry = {row[0]: row for row in report["geometry_catalog"]}
        assert geometry[hashlib.sha256(source).hexdigest()][-1] == 4
        facts = report["metadata_catalog"]["metadata"]
        assert len(facts) == 2
        by_source = {row["source_sha256"]: row for row in facts}
        mesh_facts = by_source[hashlib.sha256(source).hexdigest()]
        assert mesh_facts["triangle_count"] == 4
        slicer_facts = by_source[hashlib.sha256(gcode).hexdigest()]
        assert slicer_facts["slicer_name"] == "PrusaSlicer"
        assert slicer_facts["estimated_time_s"] == 1598
        assert slicer_facts["layer_height_mm"] == 0.15
        assert slicer_facts["material_type"] == "PLA"
        assert all("file_id" not in row and "created_at" not in row for row in facts)
        requirements = report["metadata_catalog"]["artifact_material_requirements"]
        assert requirements == [
            {
                "source_sha256": hashlib.sha256(gcode).hexdigest(),
                "tool_index": 0,
                "material_type": "PLA",
                "color_hex": "#FF8000",
            }
        ]
        assert report["preview_pixel_catalog"][0][-1] == "ready"
        assert report["database"]["backend"] == (
            "postgresql" if dialect == "postgres" else "sqlite"
        )
        assert json.loads(output.read_text())["database"] == report["database"]
