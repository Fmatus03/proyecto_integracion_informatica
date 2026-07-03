"""Canonical point-cloud access for ForestVol.

This module is the single source of truth for the NodeODM cloud consumed by
production volumetry and by experiments that benchmark the production pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from backend.app.config import Settings


@dataclass(frozen=True)
class _PipelinePointCloud:
    session_id: str
    path: Path
    sha256: str
    size_bytes: int
    point_count: int
    bbox_min: tuple[float, float, float]
    bbox_max: tuple[float, float, float]
    bbox_extent: tuple[float, float, float]
    centroid: tuple[float, float, float]

    def fingerprint(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "path": str(self.path),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "point_count": self.point_count,
            "bbox_min": [round(v, 9) for v in self.bbox_min],
            "bbox_max": [round(v, 9) for v in self.bbox_max],
            "bbox_extent": [round(v, 9) for v in self.bbox_extent],
            "centroid": [round(v, 9) for v in self.centroid],
        }


def load_pipeline_point_cloud(session_id: str, settings: Settings) -> _PipelinePointCloud:
    """Return the canonical NodeODM point_cloud.ply for a session.

    Consumers must use this function instead of hard-coded experiment paths or
    historical exported clouds. The expected source is always the session's
    persisted `point_cloud_path`, falling back only to the canonical production
    location `processed_path/<session_id>/point_cloud.ply`.
    """

    session_file = settings.upload_path / session_id / "session.json"
    session = _read_session(session_file)
    stored_path = session.get("point_cloud_path") if session else None
    cloud_path = _resolve_cloud_path(stored_path, settings) if stored_path else settings.processed_path / session_id / "point_cloud.ply"
    canonical_path = (settings.processed_path / session_id / "point_cloud.ply").resolve()
    resolved = cloud_path.resolve()
    if resolved != canonical_path:
        raise ValueError(
            "non_canonical_point_cloud_path:"
            f" session_id={session_id} stored_path={resolved} expected={canonical_path}"
        )
    if not resolved.exists():
        raise FileNotFoundError(f"pipeline_point_cloud_not_found:{resolved}")
    points = _read_ply_points(resolved)
    if points.size == 0:
        raise ValueError(f"pipeline_point_cloud_empty:{resolved}")
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    return _PipelinePointCloud(
        session_id=session_id,
        path=resolved,
        sha256=_sha256(resolved),
        size_bytes=int(resolved.stat().st_size),
        point_count=int(points.shape[0]),
        bbox_min=tuple(float(v) for v in mins.tolist()),
        bbox_max=tuple(float(v) for v in maxs.tolist()),
        bbox_extent=tuple(float(v) for v in (maxs - mins).tolist()),
        centroid=tuple(float(v) for v in points.mean(axis=0).tolist()),
    )


def _read_session(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_cloud_path(path_value: str, settings: Settings) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    candidates = [
        path.resolve(),
        (settings.upload_path.parent.parent / path).resolve(),
        (settings.upload_path.parent / path).resolve(),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_ply_points(path: Path) -> np.ndarray:
    header, data_offset = _read_ply_header(path)
    format_line = next((line for line in header if line.startswith("format ")), "")
    vertex_count = _vertex_count(header)
    if vertex_count <= 0:
        return np.empty((0, 3), dtype=np.float64)
    if "binary_little_endian" not in format_line:
        return _read_ascii_ply_points(path, data_offset, vertex_count)
    return _read_binary_xyz_points(path, header, data_offset, vertex_count)


def _read_ply_header(path: Path) -> tuple[list[str], int]:
    header: list[str] = []
    with path.open("rb") as handle:
        while True:
            line_bytes = handle.readline()
            if not line_bytes:
                raise ValueError(f"invalid_ply_missing_end_header:{path}")
            header.append(line_bytes.decode("utf-8", errors="replace").strip())
            if header[-1] == "end_header":
                return header, handle.tell()


def _vertex_count(header: list[str]) -> int:
    for line in header:
        if line.startswith("element vertex "):
            return int(line.split()[-1])
    return 0


def _read_ascii_ply_points(path: Path, data_offset: int, vertex_count: int) -> np.ndarray:
    points = np.empty((vertex_count, 3), dtype=np.float64)
    with path.open("rb") as handle:
        handle.seek(data_offset)
        for index in range(vertex_count):
            parts = handle.readline().decode("utf-8", errors="replace").split()
            points[index] = (float(parts[0]), float(parts[1]), float(parts[2]))
    return points[np.all(np.isfinite(points), axis=1)]


__all__ = ["load_pipeline_point_cloud"]


def _read_binary_xyz_points(path: Path, header: list[str], data_offset: int, vertex_count: int) -> np.ndarray:
    properties: list[str] = []
    in_vertex = False
    for line in header:
        if line.startswith("element vertex "):
            in_vertex = True
            continue
        if line.startswith("element ") and in_vertex:
            break
        if in_vertex and line.startswith("property "):
            properties.append(line)
    dtype_fields: list[tuple[str, str]] = []
    type_map = {
        "float": "<f4",
        "float32": "<f4",
        "double": "<f8",
        "float64": "<f8",
        "uchar": "u1",
        "uint8": "u1",
        "char": "i1",
        "int8": "i1",
        "ushort": "<u2",
        "uint16": "<u2",
        "short": "<i2",
        "int16": "<i2",
        "uint": "<u4",
        "uint32": "<u4",
        "int": "<i4",
        "int32": "<i4",
    }
    for prop in properties:
        parts = prop.split()
        if len(parts) == 3:
            dtype_fields.append((parts[2], type_map[parts[1]]))
    if not {"x", "y", "z"}.issubset({name for name, _ in dtype_fields}):
        raise ValueError(f"invalid_ply_missing_xyz:{path}")
    with path.open("rb") as handle:
        handle.seek(data_offset)
        arr = np.frombuffer(handle.read(), dtype=np.dtype(dtype_fields), count=vertex_count)
    points = np.column_stack((arr["x"], arr["y"], arr["z"])).astype(np.float64, copy=False)
    return points[np.all(np.isfinite(points), axis=1)]
