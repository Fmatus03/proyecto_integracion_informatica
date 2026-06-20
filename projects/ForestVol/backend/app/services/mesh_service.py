"""Preliminary mesh and volume service for ForestVol Hito 0.5."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


class MeshProcessingError(Exception):
    """Raised when Hito 0.5 mesh generation or volume estimation cannot proceed."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


@dataclass(frozen=True)
class MeshArtifacts:
    """Artifacts and metrics produced by preliminary volumetry."""

    point_cloud_path: str
    mesh_ply_path: str
    mesh_glb_path: str | None
    mesh_watertight: bool
    mesh_repair_applied: bool
    repair_cycles: list[str] = field(default_factory=list)
    volume_m3: float | None = None
    bounding_box_m: dict[str, float] | None = None
    ground_truth_volume_m3: float | None = None
    error_percentage: float | None = None
    vertex_count: int = 0
    triangle_count: int = 0
    warning: str | None = None


def _require_open3d():
    try:
        import open3d as o3d  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - covered through service behavior
        raise MeshProcessingError(
            "Open3D is required for Hito 0.5 mesh generation",
            {"dependency": "open3d"},
        ) from exc
    return o3d


def _scale_factor_meters(scale_px_per_cm: float | None) -> float:
    if scale_px_per_cm is None or scale_px_per_cm <= 0:
        raise MeshProcessingError(
            "A positive scale_px_per_cm is required before volumetry",
            {"scale_px_per_cm": scale_px_per_cm},
        )
    return 0.01 / scale_px_per_cm


def _load_point_cloud(o3d: Any, point_cloud_path: Path):
    point_cloud = o3d.io.read_point_cloud(str(point_cloud_path))
    if point_cloud.is_empty():
        raise MeshProcessingError(
            "Point cloud is empty or unreadable",
            {"point_cloud_path": str(point_cloud_path)},
        )
    return point_cloud


def _prepare_normals(point_cloud: Any) -> None:
    if not point_cloud.has_normals():
        point_cloud.estimate_normals()
    point_cloud.orient_normals_consistent_tangent_plane(30)


def _poisson_mesh(o3d: Any, point_cloud: Any, depth: int) -> Any:
    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        point_cloud,
        depth=depth,
    )
    if len(densities):
        density_values = np.asarray(densities)
        keep = density_values >= np.quantile(density_values, 0.05)
        mesh.remove_vertices_by_mask(~keep)
    return mesh


def _repair_mesh(mesh: Any) -> list[str]:
    repair_cycles: list[str] = []
    if mesh.is_watertight():
        return repair_cycles

    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_vertices()
    mesh.remove_unreferenced_vertices()
    mesh.remove_duplicated_triangles()
    repair_cycles.append("cycle_1_topology_cleanup")

    if not mesh.is_watertight():
        mesh.compute_vertex_normals()
        repair_cycles.append("cycle_2_normals_recomputed")

    return repair_cycles


def _bounding_box_m(mesh: Any) -> dict[str, float]:
    extent = mesh.get_axis_aligned_bounding_box().get_extent()
    return {
        "length_m": round(float(extent[0]), 4),
        "width_m": round(float(extent[1]), 4),
        "height_m": round(float(extent[2]), 4),
    }


def _export_mesh(o3d: Any, mesh: Any, output_dir: Path, mesh_name: str) -> tuple[Path, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    mesh_ply_path = output_dir / f"{mesh_name}.ply"
    mesh_glb_path = output_dir / f"{mesh_name}.glb"
    o3d.io.write_triangle_mesh(str(mesh_ply_path), mesh)
    glb_written = bool(o3d.io.write_triangle_mesh(str(mesh_glb_path), mesh))
    return mesh_ply_path, mesh_glb_path if glb_written and mesh_glb_path.exists() else None


def generate_preliminary_volumetry(
    point_cloud_path: Path,
    output_dir: Path,
    scale_px_per_cm: float | None,
    ground_truth_volume_m3: float | None = None,
    poisson_depth: int = 8,
    mesh_name: str = "preliminary_mesh",
) -> MeshArtifacts:
    """Generate a Hito 0.5 watertight mesh and preliminary volume estimate."""

    o3d = _require_open3d()
    point_cloud_path = Path(point_cloud_path)
    if not point_cloud_path.exists():
        raise MeshProcessingError(
            "Point cloud artifact does not exist",
            {"point_cloud_path": str(point_cloud_path)},
        )

    point_cloud = _load_point_cloud(o3d, point_cloud_path)
    scale_factor_m = _scale_factor_meters(scale_px_per_cm)
    point_cloud.scale(scale_factor_m, center=(0.0, 0.0, 0.0))
    _prepare_normals(point_cloud)

    mesh = _poisson_mesh(o3d, point_cloud, poisson_depth)
    repair_cycles = _repair_mesh(mesh)
    mesh.compute_vertex_normals()
    is_watertight = bool(mesh.is_watertight())
    if not is_watertight:
        raise MeshProcessingError(
            "Generated mesh is not watertight after repair cycles",
            {
                "point_cloud_path": str(point_cloud_path),
                "repair_cycles": repair_cycles,
                "mesh_watertight": False,
            },
        )

    volume_m3 = round(float(mesh.get_volume()), 4)
    error_percentage = None
    if ground_truth_volume_m3 is not None:
        error_percentage = round(abs(volume_m3 - ground_truth_volume_m3) / ground_truth_volume_m3 * 100.0, 4)

    mesh_ply_path, mesh_glb_path = _export_mesh(o3d, mesh, output_dir, mesh_name)
    return MeshArtifacts(
        point_cloud_path=str(point_cloud_path),
        mesh_ply_path=str(mesh_ply_path),
        mesh_glb_path=None if mesh_glb_path is None else str(mesh_glb_path),
        mesh_watertight=True,
        mesh_repair_applied=bool(repair_cycles),
        repair_cycles=repair_cycles,
        volume_m3=volume_m3,
        bounding_box_m=_bounding_box_m(mesh),
        ground_truth_volume_m3=ground_truth_volume_m3,
        error_percentage=error_percentage,
        vertex_count=len(mesh.vertices),
        triangle_count=len(mesh.triangles),
    )


def mesh_artifacts_to_session_payload(artifacts: MeshArtifacts) -> dict[str, Any]:
    """Serialize preliminary volumetry output for session persistence."""

    return {
        "point_cloud_path": artifacts.point_cloud_path,
        "mesh_ply_path": artifacts.mesh_ply_path,
        "mesh_glb_path": artifacts.mesh_glb_path,
        "mesh_watertight": artifacts.mesh_watertight,
        "mesh_repair_applied": artifacts.mesh_repair_applied,
        "repair_cycles": artifacts.repair_cycles,
        "volume_m3": artifacts.volume_m3,
        "bounding_box_m": artifacts.bounding_box_m,
        "ground_truth_volume_m3": artifacts.ground_truth_volume_m3,
        "error_percentage": artifacts.error_percentage,
        "vertex_count": artifacts.vertex_count,
        "triangle_count": artifacts.triangle_count,
        "warning": artifacts.warning,
    }
