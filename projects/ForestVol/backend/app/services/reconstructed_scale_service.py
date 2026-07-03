"""3D scale recovery from the reconstructed ArUco marker."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


class ReconstructedScaleError(Exception):
    """Raised when the reconstructed marker cannot certify metric scale."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


@dataclass(frozen=True)
class ReconstructedArucoCandidate:
    point_count: int
    centroid: list[float]
    pca_extent: list[float]
    reconstructed_side_m: float
    scale_factor_m_per_unit: float
    plane_thickness: float
    flatness_ratio: float
    square_ratio: float
    distance_to_expected_center: float
    confidence: float

    def to_payload(self) -> dict[str, Any]:
        return {
            "point_count": self.point_count,
            "centroid": self.centroid,
            "pca_extent": self.pca_extent,
            "reconstructed_side_units": round(self.reconstructed_side_m, 6),
            "scale_factor_m_per_unit": round(self.scale_factor_m_per_unit, 8),
            "plane_thickness_units": round(self.plane_thickness, 6),
            "flatness_ratio": round(self.flatness_ratio, 6),
            "square_ratio": round(self.square_ratio, 6),
            "distance_to_expected_center_units": round(self.distance_to_expected_center, 6),
            "confidence": round(self.confidence, 6),
        }


@dataclass(frozen=True)
class ReconstructedArucoScale:
    marker_size_m: float
    point_cloud_path: str
    point_count: int
    color_candidate_points: int
    evaluated_candidates: list[ReconstructedArucoCandidate] = field(default_factory=list)
    selected_candidate: ReconstructedArucoCandidate | None = None

    @property
    def scale_factor_m_per_unit(self) -> float:
        if self.selected_candidate is None:
            raise ReconstructedScaleError("No reconstructed ArUco candidate selected")
        return self.selected_candidate.scale_factor_m_per_unit

    def to_payload(self) -> dict[str, Any]:
        return {
            "method": "reconstructed_aruco_3d",
            "marker_size_m": self.marker_size_m,
            "point_cloud_path": self.point_cloud_path,
            "point_count": self.point_count,
            "color_candidate_points": self.color_candidate_points,
            "candidate_count": len(self.evaluated_candidates),
            "scale_factor_m_per_unit": round(self.scale_factor_m_per_unit, 8),
            "selected_candidate": None if self.selected_candidate is None else self.selected_candidate.to_payload(),
            "candidates": [candidate.to_payload() for candidate in self.evaluated_candidates[:10]],
        }


def estimate_reconstructed_aruco_scale(
    point_cloud_path: Path,
    marker_size_m: float,
    *,
    max_candidate_points: int = 250_000,
    min_candidate_points: int = 80,
    color_saturation_tolerance: int = 45,
    dark_threshold: int = 80,
    bright_threshold: int = 175,
    voxel_size_units: float | None = None,
    min_square_ratio: float = 0.45,
    max_flatness_ratio: float = 0.35,
    min_side_ratio: float = 0.25,
    max_side_ratio: float = 5.0,
) -> ReconstructedArucoScale:
    """Estimate cloud metric scale by measuring a reconstructed ArUco square.

    The detector intentionally combines color and geometry. Color isolates
    black/white marker-like points; connected components and PCA then reject
    non-planar or non-square structures.
    """

    if marker_size_m <= 0:
        raise ReconstructedScaleError(
            "ArUco marker size must be positive",
            {"marker_size_m": marker_size_m},
        )
    points, colors = _read_ply_points_and_colors(point_cloud_path)
    if len(points) < min_candidate_points:
        raise ReconstructedScaleError(
            "Point cloud has too few points for reconstructed ArUco scale",
            {"point_count": int(len(points)), "min_candidate_points": min_candidate_points},
        )
    if colors is None:
        raise ReconstructedScaleError(
            "Point cloud colors are required to locate the reconstructed ArUco marker",
            {"point_cloud_path": str(point_cloud_path)},
        )

    candidate_mask = _black_white_color_mask(
        colors,
        saturation_tolerance=color_saturation_tolerance,
        dark_threshold=dark_threshold,
        bright_threshold=bright_threshold,
    )
    candidate_points = points[candidate_mask]
    if len(candidate_points) > max_candidate_points:
        indices = np.linspace(0, len(candidate_points) - 1, max_candidate_points, dtype=np.int64)
        candidate_points = candidate_points[indices]
    if len(candidate_points) < min_candidate_points:
        raise ReconstructedScaleError(
            "Not enough black/white ArUco-like points in reconstructed cloud",
            {
                "color_candidate_points": int(len(candidate_points)),
                "min_candidate_points": min_candidate_points,
            },
        )

    voxel_size = voxel_size_units or max(marker_size_m * 0.10, 0.05)
    components = _voxel_components(candidate_points, voxel_size, min_candidate_points)
    candidates = _evaluate_components(
        components,
        marker_size_m=marker_size_m,
        expected_center=np.array([marker_size_m / 2.0, marker_size_m / 2.0, 0.0], dtype=float),
        min_square_ratio=min_square_ratio,
        max_flatness_ratio=max_flatness_ratio,
        min_side=marker_size_m * min_side_ratio,
        max_side=marker_size_m * max_side_ratio,
    )
    if not candidates:
        raise ReconstructedScaleError(
            "No planar square ArUco candidate found in reconstructed cloud",
            {
                "point_count": int(len(points)),
                "color_candidate_points": int(len(candidate_points)),
                "component_count": len(components),
                "min_square_ratio": min_square_ratio,
                "max_flatness_ratio": max_flatness_ratio,
            },
        )
    candidates.sort(key=lambda candidate: candidate.confidence, reverse=True)
    return ReconstructedArucoScale(
        marker_size_m=float(marker_size_m),
        point_cloud_path=str(point_cloud_path),
        point_count=int(len(points)),
        color_candidate_points=int(len(candidate_points)),
        evaluated_candidates=candidates,
        selected_candidate=candidates[0],
    )


def _black_white_color_mask(
    colors: np.ndarray,
    *,
    saturation_tolerance: int,
    dark_threshold: int,
    bright_threshold: int,
) -> np.ndarray:
    color_i = colors.astype(np.int16)
    brightness = color_i.mean(axis=1)
    saturation = color_i.max(axis=1) - color_i.min(axis=1)
    return (saturation <= saturation_tolerance) & ((brightness <= dark_threshold) | (brightness >= bright_threshold))


def _evaluate_components(
    components: list[np.ndarray],
    *,
    marker_size_m: float,
    expected_center: np.ndarray,
    min_square_ratio: float,
    max_flatness_ratio: float,
    min_side: float,
    max_side: float,
) -> list[ReconstructedArucoCandidate]:
    candidates: list[ReconstructedArucoCandidate] = []
    for component in components:
        if len(component) < 3:
            continue
        centered = component - component.mean(axis=0)
        try:
            _u, _s, basis = np.linalg.svd(centered, full_matrices=False)
        except np.linalg.LinAlgError:
            continue
        projected = centered @ basis.T
        planar_extent = _minimum_area_rect_extent(projected[:, :2])
        z_low, z_high = np.percentile(projected[:, 2], [2.0, 98.0])
        extent = np.array([planar_extent[0], planar_extent[1], max(float(z_high - z_low), 0.0)], dtype=float)
        major = float(max(planar_extent[0], planar_extent[1]))
        minor = float(min(planar_extent[0], planar_extent[1]))
        thickness = float(extent[2])
        if major <= 0:
            continue
        side = float((major + minor) / 2.0)
        square_ratio = float(minor / major)
        flatness_ratio = float(thickness / major)
        if side < min_side or side > max_side:
            continue
        if square_ratio < min_square_ratio or flatness_ratio > max_flatness_ratio:
            continue
        distance = float(np.linalg.norm(component.mean(axis=0) - expected_center))
        scale_factor = float(marker_size_m / side)
        confidence = float(
            square_ratio
            * max(0.0, 1.0 - flatness_ratio)
            * min(1.0, len(component) / 500.0)
            / (1.0 + distance / max(marker_size_m, 1e-9))
        )
        candidates.append(
            ReconstructedArucoCandidate(
                point_count=int(len(component)),
                centroid=[round(float(value), 6) for value in component.mean(axis=0).tolist()],
                pca_extent=[round(float(value), 6) for value in extent.tolist()],
                reconstructed_side_m=side,
                scale_factor_m_per_unit=scale_factor,
                plane_thickness=thickness,
                flatness_ratio=flatness_ratio,
                square_ratio=square_ratio,
                distance_to_expected_center=distance,
                confidence=confidence,
            )
        )
    return candidates


def _minimum_area_rect_extent(points_2d: np.ndarray) -> tuple[float, float]:
    """Return robust extents of the lowest-area rectangle over projected points."""

    if len(points_2d) == 0:
        return 0.0, 0.0
    centered = points_2d - np.median(points_2d, axis=0)
    best_extent = (0.0, 0.0)
    best_area = float("inf")
    for angle in np.linspace(0.0, np.pi / 2.0, 181):
        cos_a = float(np.cos(angle))
        sin_a = float(np.sin(angle))
        rotation = np.array([[cos_a, -sin_a], [sin_a, cos_a]], dtype=float)
        rotated = centered @ rotation
        low = np.percentile(rotated, 2.0, axis=0)
        high = np.percentile(rotated, 98.0, axis=0)
        extent = np.maximum(high - low, 0.0)
        area = float(extent[0] * extent[1])
        if area < best_area:
            best_area = area
            best_extent = (float(extent[0]), float(extent[1]))
    return best_extent


def _voxel_components(points: np.ndarray, voxel_size: float, min_points: int) -> list[np.ndarray]:
    voxel_index = np.floor(points / voxel_size).astype(np.int32)
    voxel_to_indices: dict[tuple[int, int, int], list[int]] = {}
    for index, voxel in enumerate(voxel_index):
        voxel_to_indices.setdefault((int(voxel[0]), int(voxel[1]), int(voxel[2])), []).append(index)

    visited: set[tuple[int, int, int]] = set()
    components: list[np.ndarray] = []
    neighbors = [
        (dx, dy, dz)
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        for dz in (-1, 0, 1)
        if not (dx == 0 and dy == 0 and dz == 0)
    ]
    occupied = set(voxel_to_indices)
    for start in list(occupied):
        if start in visited:
            continue
        stack = [start]
        visited.add(start)
        component_indices: list[int] = []
        while stack:
            current = stack.pop()
            component_indices.extend(voxel_to_indices[current])
            cx, cy, cz = current
            for dx, dy, dz in neighbors:
                neighbor = (cx + dx, cy + dy, cz + dz)
                if neighbor in occupied and neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        if len(component_indices) >= min_points:
            components.append(points[np.asarray(component_indices, dtype=np.int64)])
    components.sort(key=len, reverse=True)
    return components


def _read_ply_points_and_colors(path: Path) -> tuple[np.ndarray, np.ndarray | None]:
    header, offset = _read_ply_header(path)
    vertex_count = _vertex_count(header)
    if vertex_count <= 0:
        return np.empty((0, 3), dtype=np.float64), None
    format_line = next((line for line in header if line.startswith("format ")), "")
    if "ascii" in format_line:
        return _read_ascii_ply(path, offset, vertex_count)
    if "binary_little_endian" in format_line:
        return _read_binary_little_endian_ply(path, header, offset, vertex_count)
    raise ReconstructedScaleError(
        "Unsupported PLY format for reconstructed ArUco scale",
        {"format": format_line, "point_cloud_path": str(path)},
    )


def _read_ply_header(path: Path) -> tuple[list[str], int]:
    header: list[str] = []
    with path.open("rb") as handle:
        while True:
            line = handle.readline()
            if not line:
                raise ReconstructedScaleError("Invalid PLY: missing end_header", {"point_cloud_path": str(path)})
            decoded = line.decode("ascii", errors="replace").strip()
            header.append(decoded)
            if decoded == "end_header":
                return header, handle.tell()


def _vertex_count(header: list[str]) -> int:
    for line in header:
        parts = line.split()
        if len(parts) == 3 and parts[:2] == ["element", "vertex"]:
            return int(parts[2])
    return 0


def _vertex_properties(header: list[str]) -> list[tuple[str, str]]:
    properties: list[tuple[str, str]] = []
    in_vertex = False
    for line in header:
        parts = line.split()
        if len(parts) == 3 and parts[:2] == ["element", "vertex"]:
            in_vertex = True
            continue
        if parts[:1] == ["element"] and len(parts) >= 2 and parts[1] != "vertex":
            in_vertex = False
        if in_vertex and len(parts) == 3 and parts[0] == "property":
            properties.append((parts[2], parts[1]))
    return properties


def _read_ascii_ply(path: Path, offset: int, vertex_count: int) -> tuple[np.ndarray, np.ndarray | None]:
    points = np.empty((vertex_count, 3), dtype=np.float64)
    colors = np.empty((vertex_count, 3), dtype=np.uint8)
    has_colors = False
    with path.open("rb") as handle:
        handle.seek(offset)
        for index in range(vertex_count):
            parts = handle.readline().decode("utf-8", errors="replace").split()
            points[index] = (float(parts[0]), float(parts[1]), float(parts[2]))
            if len(parts) >= 6:
                colors[index] = (int(float(parts[3])), int(float(parts[4])), int(float(parts[5])))
                has_colors = True
    finite = np.all(np.isfinite(points), axis=1)
    return points[finite], colors[finite] if has_colors else None


def _read_binary_little_endian_ply(
    path: Path,
    header: list[str],
    offset: int,
    vertex_count: int,
) -> tuple[np.ndarray, np.ndarray | None]:
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
    dtype_fields: list[tuple[str, str]] = []
    for name, type_name in _vertex_properties(header):
        if type_name not in type_map:
            raise ReconstructedScaleError(
                "Unsupported PLY vertex property type",
                {"property": name, "type": type_name, "point_cloud_path": str(path)},
            )
        dtype_fields.append((name, type_map[type_name]))
    names = {name for name, _ in dtype_fields}
    if not {"x", "y", "z"}.issubset(names):
        raise ReconstructedScaleError("PLY is missing XYZ vertex properties", {"point_cloud_path": str(path)})
    with path.open("rb") as handle:
        handle.seek(offset)
        arr = np.frombuffer(handle.read(), dtype=np.dtype(dtype_fields), count=vertex_count)
    points = np.column_stack([arr["x"], arr["y"], arr["z"]]).astype(np.float64)
    colors = None
    if {"red", "green", "blue"}.issubset(names):
        colors = np.column_stack([arr["red"], arr["green"], arr["blue"]]).astype(np.uint8)
    finite = np.all(np.isfinite(points), axis=1)
    return points[finite], colors[finite] if colors is not None else None
