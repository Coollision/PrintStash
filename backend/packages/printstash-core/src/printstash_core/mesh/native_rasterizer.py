"""Optional bounded Rust visibility and lighting with custom callback fallback."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from .rasterizer import FloatArray, Shade, UInt8Array


# Bound interpolation and lighting temporaries independently of preview size.
_SHADE_BATCH_PIXELS = 16_384


class Kernel(Protocol):
    def rasterize(
        self, triangles: bytes, itemsize: int, depth: bytes, width: int, height: int
    ) -> tuple[bytes, int]: ...

    def shade_fragments(
        self,
        records: bytes,
        triangles: bytes,
        itemsize: int,
        normals: bytes,
        normal_itemsize: int,
        width: int,
        height: int,
        lighting: tuple[float, ...],
    ) -> bytes: ...

    def rasterize_phong(
        self,
        triangles: bytes,
        itemsize: int,
        depth: bytes,
        normals: bytes,
        normal_itemsize: int,
        width: int,
        height: int,
        lighting: tuple[float, ...],
    ) -> tuple[bytes, int]: ...


def kernel() -> Kernel | None:
    """Return the extension when installed; propagate broken installations."""
    try:
        return cast(Kernel, importlib.import_module("printstash_mesh_native"))
    except ModuleNotFoundError as exc:
        if exc.name != "printstash_mesh_native":
            raise
        return None


def rasterise_triangles(
    img: UInt8Array,
    zbuf: FloatArray,
    tri: FloatArray,
    vert_nrm: FloatArray,
    shade: Shade,
    base_color: FloatArray,
    width: int,
    height: int,
) -> int:
    import numpy as np

    from .rasterizer import _PhongShader

    native = kernel()
    if native is None:
        raise RuntimeError("Rust mesh renderer is not installed")
    if (
        tri.ndim != 3
        or tri.shape[1:] != (3, 3)
        or tri.dtype not in (np.dtype(np.float32), np.dtype(np.float64))
        or vert_nrm.shape != tri.shape
        or img.shape != (height, width, 3)
        or zbuf.shape != (height, width)
        or zbuf.dtype != np.dtype(np.float64)
    ):
        raise ValueError("invalid native rasterizer arrays")
    triangles = tri.tobytes()
    if (
        isinstance(shade, _PhongShader)
        and hasattr(native, "rasterize_phong")
        and vert_nrm.dtype in (np.dtype(np.float32), np.dtype(np.float64))
    ):
        payload, candidates = native.rasterize_phong(
            triangles,
            tri.dtype.itemsize,
            zbuf.tobytes(),
            vert_nrm.tobytes(),
            vert_nrm.dtype.itemsize,
            width,
            height,
            shade.parameters + tuple(float(value) for value in base_color),
        )
        # No face IDs or per-pixel normal arrays cross the native boundary.
        fragments = np.frombuffer(
            payload,
            dtype=np.dtype(
                [
                    ("pixel", "=u4"),
                    ("depth", "=f8"),
                    ("color", "u1", (3,)),
                ]
            ),
        )
        for start in range(0, len(fragments), _SHADE_BATCH_PIXELS):
            batch = fragments[start : start + _SHADE_BATCH_PIXELS]
            y, x = batch["pixel"] // width, batch["pixel"] % width
            zbuf[y, x] = batch["depth"]
            img[y, x] = batch["color"]
        return candidates
    payload, candidates = native.rasterize(
        triangles, tri.dtype.itemsize, zbuf.tobytes(), width, height
    )
    records = np.frombuffer(payload, dtype=np.uint64).reshape(-1, 3)
    if len(records) == 0:
        return candidates
    # Only the final RGB bytes scale with visible pixels. Interpolation and the
    # lighting callback work on bounded batches, with no whole-image gathers.
    if (
        isinstance(shade, _PhongShader)
        and hasattr(native, "shade_fragments")
        and vert_nrm.dtype in (np.dtype(np.float32), np.dtype(np.float64))
    ):
        # Rust allocates only the final RGB bytes, with constant per-pixel scratch.
        # The Python callback remains authoritative for custom shaders/old kernels.
        encoded = native.shade_fragments(
            payload,
            triangles,
            tri.dtype.itemsize,
            vert_nrm.tobytes(),
            vert_nrm.dtype.itemsize,
            width,
            height,
            shade.parameters + tuple(float(value) for value in base_color),
        )
        colors = np.frombuffer(encoded, dtype=np.uint8).reshape(-1, 3)
    else:
        colors = np.empty((len(records), 3), dtype=np.uint8)
        for start in range(0, len(records), _SHADE_BATCH_PIXELS):
            batch = records[start : start + _SHADE_BATCH_PIXELS]
            target, source = batch[:, 0], batch[:, 1]
            a, b, c = tri[source, 0], tri[source, 1], tri[source, 2]
            fx = target % width + 0.5
            fy = target // width + 0.5
            denom = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (
                a[:, 1] - c[:, 1]
            )
            w0 = (
                (b[:, 1] - c[:, 1]) * (fx - c[:, 0])
                + (c[:, 0] - b[:, 0]) * (fy - c[:, 1])
            ) / denom
            w1 = (
                (c[:, 1] - a[:, 1]) * (fx - c[:, 0])
                + (a[:, 0] - c[:, 0]) * (fy - c[:, 1])
            ) / denom
            w2 = 1.0 - w0 - w1
            vn = vert_nrm[source]
            n = w0[:, None] * vn[:, 0]
            n += w1[:, None] * vn[:, 1]
            n += w2[:, None] * vn[:, 2]
            nlen = np.linalg.norm(n, axis=1, keepdims=True)
            n /= np.where(nlen == 0, 1.0, nlen)
            colors[start : start + len(batch)] = np.clip(
                base_color * shade(n), 0, 255
            ).astype(np.uint8)
    # Commit only after every shading batch succeeds, including the last one.
    # Indexed writes also preserve non-contiguous framebuffer views.
    for start in range(0, len(records), _SHADE_BATCH_PIXELS):
        batch = records[start : start + _SHADE_BATCH_PIXELS]
        y, x = batch[:, 0] // width, batch[:, 0] % width
        zbuf[y, x] = batch[:, 2].view(np.float64)
        img[y, x] = colors[start : start + len(batch)]
    return candidates
