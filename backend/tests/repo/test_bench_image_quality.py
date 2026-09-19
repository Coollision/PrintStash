"""Preview-quality probes keep renderer comparisons bounded and explicit."""

from __future__ import annotations

import base64

import pytest
from PIL import Image

from scripts.bench_image_quality import (
    PROBE_BYTES,
    encode_rgb_probe,
    probe_mean_absolute_error,
    probes_match,
)


def probe(value: int) -> str:
    return base64.b64encode(bytes([value]) * PROBE_BYTES).decode("ascii")


class TestPreviewQualityProbe:
    def test_encodes_a_deterministic_rgb_probe(self) -> None:
        image = Image.new("RGBA", (64, 48), (10, 20, 30, 128))

        first = encode_rgb_probe(image)
        second = encode_rgb_probe(image.copy())

        assert first == second
        assert len(base64.b64decode(first)) == PROBE_BYTES

    def test_applies_the_approved_mean_error_threshold(self) -> None:
        assert probe_mean_absolute_error(probe(10), probe(34)) == 24
        assert probes_match(probe(10), probe(34))
        assert not probes_match(probe(10), probe(35))

    @pytest.mark.parametrize("value", ["not-base64", probe(1)[:-4]])
    def test_rejects_malformed_probes(self, value: str) -> None:
        with pytest.raises(ValueError, match="invalid preview quality probe"):
            probe_mean_absolute_error(probe(0), value)

    @pytest.mark.parametrize("value", [True, -1, 256])
    def test_rejects_invalid_thresholds(self, value: object) -> None:
        with pytest.raises(ValueError, match="invalid preview quality threshold"):
            probes_match(probe(0), probe(0), max_mean_absolute_error=value)
