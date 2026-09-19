"""Bounded orthographic surface voxelization, with optional closed-solid fill.

All meshes use one supplied physical cube. Triangle intersections are computed
at voxel-column centers; duplicate intersections along shared edges count once.
Open surfaces retain surface occupancy without inventing an enclosed volume.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .fingerprint import GeometryError

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


def voxelize(
    vertices: NDArray[np.float64],
    faces: NDArray[np.int64],
    *,
    half_width: float,
    resolution: int = 64,
    fill: bool = True,
) -> NDArray[np.bool_]:
    import numpy as np

    from ..native_rasterizer import kernel

    if resolution not in (16, 32, 64) or not np.isfinite(half_width) or half_width <= 0:
        raise GeometryError("invalid_voxel_recipe")
    try:
        packed = kernel().voxelize(
            np.asarray(vertices, dtype="=f8").tobytes(),
            np.asarray(faces, dtype="=i8").tobytes(),
            half_width,
            resolution,
            fill,
        )
    except ValueError as exc:
        raise GeometryError(str(exc)) from exc
    return np.frombuffer(packed, dtype=np.bool_).reshape((resolution,) * 3).copy()


def _project(
    triangles: NDArray[np.float64], *, axis: int, resolution: int, fill: bool
) -> NDArray[np.bool_]:
    import numpy as np

    axes = [i for i in range(3) if i != axis] + [axis]
    triangles = triangles[:, :, axes]
    columns: list[NDArray[np.int64]] = []
    depths: list[NDArray[np.float64]] = []
    total = 0
    for start in range(0, len(triangles), 64):
        tri = triangles[start : start + 64]
        low = np.maximum(np.ceil(tri[:, :, :2].min(axis=1) - 0.5).astype(np.int64), 0)
        high = np.minimum(
            np.floor(tri[:, :, :2].max(axis=1) - 0.5).astype(np.int64), resolution - 1
        )
        sizes = np.maximum(high - low + 1, 0)
        counts = sizes[:, 0] * sizes[:, 1]
        owners = np.repeat(np.arange(len(tri)), counts)
        local = np.arange(int(counts.sum())) - np.repeat(
            np.cumsum(counts) - counts, counts
        )
        # Empty projected faces generate no owners and cannot divide by zero.
        xy = low[owners] + np.column_stack(
            (local % sizes[owners, 0], local // sizes[owners, 0])
        )
        a, b, c = tri[owners, 0], tri[owners, 1], tri[owners, 2]
        x, y = xy[:, 0] + 0.5, xy[:, 1] + 0.5
        denominator = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (
            c[:, 0] - b[:, 0]
        ) * (a[:, 1] - c[:, 1])
        valid = np.abs(denominator) > 1e-12
        safe = np.where(valid, denominator, 1)
        u = (
            (b[:, 1] - c[:, 1]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (y - c[:, 1])
        ) / safe
        v = (
            (c[:, 1] - a[:, 1]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (y - c[:, 1])
        ) / safe
        inside = valid & (u >= -1e-10) & (v >= -1e-10) & (u + v <= 1 + 1e-10)
        z = (u * a[:, 2] + v * b[:, 2] + (1 - u - v) * c[:, 2])[inside]
        ids = (xy[:, 0] * resolution + xy[:, 1])[inside]
        total += len(z)
        if total > 2_000_000:
            raise GeometryError("voxel_resource_limit")
        columns.append(ids)
        depths.append(z)
    grid = np.zeros((resolution * resolution, resolution), dtype=np.bool_)
    if total:
        ids, z = np.concatenate(columns), np.concatenate(depths)
        order = np.lexsort((z, ids))
        ids, z = ids[order], z[order]
        unique = np.r_[True, (np.diff(ids) != 0) | (np.abs(np.diff(z)) > 1e-7)]
        ids, z = ids[unique], z[unique]
        if fill:
            events = np.zeros((resolution * resolution, resolution + 1), dtype=np.int32)
            boundary = np.clip(np.ceil(z - 0.5).astype(np.int64), 0, resolution)
            np.add.at(events, (ids, boundary), 1)
            grid |= np.cumsum(events[:, :resolution], axis=1) % 2 == 1
        surface = np.clip(np.floor(z).astype(np.int64), 0, resolution - 1)
        grid[ids, surface] = True
    return grid.reshape((resolution,) * 3).transpose(np.argsort(axes))
