"""A compression experiment must still reject any changed preview pixels."""

import pytest

from scripts.bench_import import compare_previews


class TestComparePreviews:
    def test_allows_changed_lossless_compression(self) -> None:
        pixels = [["source", "rgba", 320, 240, "ready"]]
        before = {
            "preview_catalog": [["source", "old"]],
            "preview_pixel_catalog": pixels,
        }
        after = {
            "preview_catalog": [["source", "new"]],
            "preview_pixel_catalog": pixels,
        }

        compare_previews(before, after, mode="pixels")

    def test_rejects_changed_bytes_by_default(self) -> None:
        with pytest.raises(SystemExit, match="preview bytes differ"):
            compare_previews({"preview_catalog": ["old"]}, {"preview_catalog": ["new"]})

    @pytest.mark.parametrize(
        "changed",
        [
            ["source", "changed", 320, 240, "ready"],
            ["source", "rgba", 240, 320, "ready"],
            ["source", "rgba", 320, 240, "failed"],
        ],
        ids=["pixels", "dimensions", "state"],
    )
    def test_rejects_changed_preview(self, changed: list) -> None:
        with pytest.raises(SystemExit, match="preview pixels differ"):
            compare_previews(
                {"preview_pixel_catalog": [["source", "rgba", 320, 240, "ready"]]},
                {"preview_pixel_catalog": [changed]},
                mode="pixels",
            )

    def test_rejects_missing_reference_pixels(self) -> None:
        with pytest.raises(SystemExit, match="no decoded pixel catalog"):
            compare_previews({}, {"preview_pixel_catalog": []}, mode="pixels")
