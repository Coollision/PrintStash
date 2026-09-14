"""Native binary STL loading retains the portable loader for other inputs."""

import numpy as np
import trimesh

from printstash_core.mesh import native_rasterizer, stl


class TestLoadBinaryStlFallback:
    def test_missing_extension_uses_legacy_loader(self, monkeypatch, tmp_path):
        monkeypatch.setattr(stl, "kernel", lambda: None)

        assert stl.load_binary_stl(tmp_path / "absent.stl") is None

    def test_older_extension_uses_legacy_loader(self, monkeypatch, tmp_path):
        monkeypatch.setattr(stl, "kernel", lambda: object())

        assert stl.load_binary_stl(tmp_path / "absent.stl") is None


if hasattr(native_rasterizer.kernel(), "load_binary_stl"):

    class TestLoadBinaryStl:
        def test_retains_full_mesh(self, tmp_path):
            path = tmp_path / "cube.stl"
            path.write_bytes(
                trimesh.creation.box(extents=[2, 3, 4]).export(file_type="stl")
            )
            expected = trimesh.load_mesh(path, process=False)

            actual = stl.load_binary_stl(path)

            np.testing.assert_array_equal(actual.vertices, expected.vertices)
            np.testing.assert_array_equal(actual.faces, expected.faces)

        def test_defers_ascii_to_existing_loader(self, tmp_path):
            path = tmp_path / "ascii.stl"
            path.write_text(trimesh.creation.box().export(file_type="stl_ascii"))

            assert stl.load_binary_stl(path) is None

        def test_defers_empty_mesh_to_existing_loader(self, tmp_path):
            path = tmp_path / "empty.stl"
            path.write_bytes(bytes(84))

            assert stl.load_binary_stl(path) is None
