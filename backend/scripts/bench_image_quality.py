"""Shared, bounded preview-quality probes for controlled benchmarks."""

from __future__ import annotations

import base64
import binascii

import numpy as np
from PIL import Image

PROBE_SIZE = (32, 24)
PROBE_BYTES = PROBE_SIZE[0] * PROBE_SIZE[1] * 3
MAX_MEAN_ABSOLUTE_ERROR = 24.0


def encode_rgb_probe(image: Image.Image) -> str:
    """Encode one deterministic low-resolution RGB quality probe."""
    probe = image.convert("RGB").resize(PROBE_SIZE, Image.Resampling.LANCZOS)
    return base64.b64encode(probe.tobytes()).decode("ascii")


def probe_mean_absolute_error(left: str, right: str) -> float:
    """Return RGB probe error, rejecting malformed or differently sized probes."""
    try:
        first = base64.b64decode(left, validate=True)
        second = base64.b64decode(right, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid preview quality probe") from exc
    if len(first) != PROBE_BYTES or len(second) != PROBE_BYTES:
        raise ValueError("invalid preview quality probe")
    a = np.frombuffer(first, dtype=np.uint8).astype(np.int16)
    b = np.frombuffer(second, dtype=np.uint8).astype(np.int16)
    return float(np.abs(a - b).mean())


def probes_match(
    left: str,
    right: str,
    *,
    max_mean_absolute_error: float = MAX_MEAN_ABSOLUTE_ERROR,
) -> bool:
    """Apply the approved M10 mean-error threshold to two probes."""
    if (
        not isinstance(max_mean_absolute_error, (int, float))
        or isinstance(max_mean_absolute_error, bool)
        or not 0 <= max_mean_absolute_error <= 255
    ):
        raise ValueError("invalid preview quality threshold")
    return probe_mean_absolute_error(left, right) <= max_mean_absolute_error
