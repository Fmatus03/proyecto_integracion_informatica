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
    point_cloud_quality: dict[str, Any] = field(default_factory=dict)
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
    return 1.0


def _load_point_cloud(o3d: Any, point_cloud_path: Path):
    point_cloud = o3d.io.read_point_cloud(str(point_cloud_path))
    declared_vertex_count = _ply_declared_vertex_count(point_cloud_path)
    actual_point_count = len(point_cloud.points) if not point_cloud.is_empty() else 0
    if declared_vertex_count and actual_point_count < declared_vertex_count * 0.5:
        point_cloud = _load_binary_little_endian_ply(o3d, point_cloud_path)
    if point_cloud.is_empty():
        raise MeshProcessingError(
            "Point cloud is empty or unreadable",
            {"point_cloud_path": str(point_cloud_path)},
        )
    return point_cloud


def _read_ply_header(point_cloud_path: Path) -> tuple[list[str], int]:
    header_lines: list[str] = []
    with point_cloud_path.open("rb") as handle:
        while True:
            line = handle.readline()
            if not line:
                raise MeshProcessingError(
                    "PLY header is incomplete",
                    {"point_cloud_path": str(point_cloud_path)},
                )
            decoded = line.decode("ascii", errors="replace").strip()
            header_lines.append(decoded)
            if decoded == "end_header":
                return header_lines, handle.tell()


def _ply_declared_vertex_count(point_cloud_path: Path) -> int | None:
    try:
        header_lines, _ = _read_ply_header(point_cloud_path)
    except MeshProcessingError:
        return None
    for line in header_lines:
        parts = line.split()
        if len(parts) == 3 and parts[:2] == ["element", "vertex"]:
            return int(parts[2])
    return None


def _load_binary_little_endian_ply(o3d: Any, point_cloud_path: Path):
    header_lines, data_offset = _read_ply_header(point_cloud_path)
    if "format binary_little_endian 1.0" not in header_lines:
        raise MeshProcessingError(
            "PLY fallback only supports binary_little_endian 1.0",
            {"point_cloud_path": str(point_cloud_path)},
        )

    vertex_count = 0
    properties: list[tuple[str, str]] = []
    in_vertex = False
    type_map = {
        "float": "<f4",
        "float32": "<f4",
        "double": "<f8",
        "uchar": "u1",
        "uint8": "u1",
        "char": "i1",
        "int": "<i4",
        "uint": "<u4",
    }
    for line in header_lines:
        parts = line.split()
        if len(parts) == 3 and parts[:2] == ["element", "vertex"]:
            vertex_count = int(parts[2])
            in_vertex = True
            continue
        if parts[:1] == ["element"] and len(parts) >= 2 and parts[1] != "vertex":
            in_vertex = False
        if in_vertex and len(parts) == 3 and parts[0] == "property":
            if parts[1] not in type_map:
                raise MeshProcessingError(
                    "PLY fallback found unsupported vertex property type",
                    {"property_type": parts[1], "property_name": parts[2]},
                )
            properties.append((parts[2], type_map[parts[1]]))

    if vertex_count <= 0 or not properties:
        raise MeshProcessingError(
            "PLY fallback could not find vertex properties",
            {"point_cloud_path": str(point_cloud_path)},
        )

    dtype = np.dtype(properties)
    data = point_cloud_path.read_bytes()[data_offset:]
    vertices = np.frombuffer(data, dtype=dtype, count=vertex_count)
    points = np.column_stack([vertices["x"], vertices["y"], vertices["z"]]).astype(float)
    finite = np.isfinite(points).all(axis=1)
    points = points[finite]

    point_cloud = o3d.geometry.PointCloud()
    point_cloud.points = o3d.utility.Vector3dVector(points)
    if {"nx", "ny", "nz"}.issubset(vertices.dtype.names or ()):
        normals = np.column_stack([vertices["nx"], vertices["ny"], vertices["nz"]]).astype(float)[finite]
        point_cloud.normals = o3d.utility.Vector3dVector(normals)
    if {"red", "green", "blue"}.issubset(vertices.dtype.names or ()):
        colors = np.column_stack([vertices["red"], vertices["green"], vertices["blue"]]).astype(float)[finite] / 255.0
        point_cloud.colors = o3d.utility.Vector3dVector(colors)
    return point_cloud


def _point_cloud_quality(point_cloud: Any) -> dict[str, Any]:
    point_count = len(point_cloud.points)
    extent = np.asarray(point_cloud.get_axis_aligned_bounding_box().get_extent(), dtype=float)
    positive_extent = extent[extent > 0]
    bbox_volume = float(np.prod(positive_extent)) if positive_extent.size == 3 else 0.0
    axis_ratio = float(positive_extent.max() / positive_extent.min()) if positive_extent.size else float("inf")
    density_points_per_m3 = float(point_count / bbox_volume) if bbox_volume > 0 else 0.0
    return {
        "point_count": point_count,
        "bounding_box_extent": extent.tolist(),
        "axis_ratio": round(axis_ratio, 4) if np.isfinite(axis_ratio) else None,
        "density_points_per_m3": round(density_points_per_m3, 4),
    }


def _validate_point_cloud_geometry(
    point_cloud: Any,
    min_point_count: int,
    max_axis_ratio: float,
    min_density_points_per_m3: float,
) -> dict[str, Any]:
    quality = _point_cloud_quality(point_cloud)
    point_count = quality["point_count"]
    if point_count < min_point_count:
        raise MeshProcessingError(
            "Point cloud has insufficient density for Hito 0.5 meshing",
            {"point_count": point_count, "min_point_count": min_point_count},
        )

    extent = np.asarray(quality["bounding_box_extent"], dtype=float)
    if extent.size != 3 or np.any(extent <= 0):
        raise MeshProcessingError(
            "Point cloud geometry is degenerate before meshing",
            {"point_count": point_count, "bounding_box_extent": extent.tolist()},
        )
    if quality["axis_ratio"] is not None and quality["axis_ratio"] > max_axis_ratio:
        raise MeshProcessingError(
            "Point cloud geometry is too deformed for reliable woodpile volumetry",
            {**quality, "max_axis_ratio": max_axis_ratio},
        )
    if quality["density_points_per_m3"] < min_density_points_per_m3:
        raise MeshProcessingError(
            "Point cloud spatial density is too low for reliable meshing",
            {**quality, "min_density_points_per_m3": min_density_points_per_m3},
        )
    return quality


def _clean_point_cloud(
    point_cloud: Any,
    voxel_size_m: float | None,
    outlier_neighbors: int,
    outlier_std_ratio: float,
    min_retained_ratio: float,
) -> Any:
    original_count = len(point_cloud.points)
    if voxel_size_m and voxel_size_m > 0 and hasattr(point_cloud, "voxel_down_sample"):
        point_cloud = point_cloud.voxel_down_sample(voxel_size_m)
    if hasattr(point_cloud, "remove_statistical_outlier"):
        filtered, _ = point_cloud.remove_statistical_outlier(
            nb_neighbors=outlier_neighbors,
            std_ratio=outlier_std_ratio,
        )
        point_cloud = filtered
    retained_count = len(point_cloud.points)
    if original_count and retained_count / original_count < min_retained_ratio:
        raise MeshProcessingError(
            "Point cloud cleanup removed too much structure",
            {
                "original_point_count": original_count,
                "retained_point_count": retained_count,
                "min_retained_ratio": min_retained_ratio,
            },
        )
    return point_cloud


def _segment_woodpile_components(
    point_cloud: Any,
    segmentation_voxel_size_m: float | None,
    cluster_eps_m: float,
    cluster_min_points: int,
    max_components: int,
    min_component_ratio: float,
) -> tuple[Any, dict[str, Any]]:
    if (
        not segmentation_voxel_size_m
        or segmentation_voxel_size_m <= 0
        or not hasattr(point_cloud, "cluster_dbscan")
        or not hasattr(point_cloud, "select_by_index")
    ):
        return point_cloud, {"applied": False, "reason": "unsupported"}

    clustering_cloud = point_cloud
    if hasattr(point_cloud, "voxel_down_sample"):
        clustering_cloud = point_cloud.voxel_down_sample(segmentation_voxel_size_m)

    labels = np.asarray(
        clustering_cloud.cluster_dbscan(
            eps=cluster_eps_m,
            min_points=cluster_min_points,
            print_progress=False,
        )
    )
    cluster_labels = labels[labels >= 0]
    if cluster_labels.size == 0:
        raise MeshProcessingError(
            "Point cloud segmentation found no dense woodpile components",
            {
                "cluster_eps_m": cluster_eps_m,
                "cluster_min_points": cluster_min_points,
            },
        )

    values, counts = np.unique(cluster_labels, return_counts=True)
    order = np.argsort(counts)[::-1]
    main_count = int(counts[order[0]])
    selected_labels: list[int] = []
    for ordered_index in order:
        label = int(values[ordered_index])
        count = int(counts[ordered_index])
        if len(selected_labels) >= max_components:
            break
        if count / main_count < min_component_ratio:
            continue
        selected_labels.append(label)

    selected_indices = np.where(np.isin(labels, selected_labels))[0]
    if selected_indices.size < cluster_min_points:
        raise MeshProcessingError(
            "Point cloud segmentation removed too much structure",
            {
                "selected_point_count": int(selected_indices.size),
                "cluster_min_points": cluster_min_points,
            },
        )

    segmented_cloud = clustering_cloud.select_by_index(selected_indices.tolist())
    return segmented_cloud, {
        "applied": True,
        "method": "dbscan_dominant_components",
        "voxel_size_m": segmentation_voxel_size_m,
        "cluster_eps_m": cluster_eps_m,
        "cluster_min_points": cluster_min_points,
        "max_components": max_components,
        "min_component_ratio": min_component_ratio,
        "selected_labels": selected_labels,
        "selected_point_count": int(selected_indices.size),
        "cluster_counts": {str(int(values[i])): int(counts[i]) for i in order[:8]},
    }


def _prepare_normals(
    o3d: Any,
    point_cloud: Any,
    normal_radius_m: float,
    normal_max_nn: int,
    recompute_normals: bool,
) -> None:
    if recompute_normals or not point_cloud.has_normals():
        if hasattr(o3d.geometry, "KDTreeSearchParamHybrid"):
            point_cloud.estimate_normals(
                search_param=o3d.geometry.KDTreeSearchParamHybrid(
                    radius=normal_radius_m,
                    max_nn=normal_max_nn,
                )
            )
        else:
            point_cloud.estimate_normals()
    point_cloud.orient_normals_consistent_tangent_plane(normal_max_nn)


def _poisson_mesh(o3d: Any, point_cloud: Any, depth: int, density_quantile: float) -> Any:
    if density_quantile < 0 or density_quantile >= 1:
        raise MeshProcessingError(
            "density_quantile must be in the [0, 1) range",
            {"density_quantile": density_quantile},
        )
    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        point_cloud,
        depth=depth,
    )
    if len(densities) and density_quantile > 0:
        density_values = np.asarray(densities)
        keep = density_values >= np.quantile(density_values, density_quantile)
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


def _watertight_mesh(o3d: Any, point_cloud: Any, poisson_mesh: Any) -> tuple[Any, list[str], bool]:
    repair_cycles = _repair_mesh(poisson_mesh)
    if poisson_mesh.is_watertight():
        return poisson_mesh, repair_cycles, False

    if not hasattr(point_cloud, "compute_convex_hull"):
        return poisson_mesh, repair_cycles, False

    hull_mesh, _ = point_cloud.compute_convex_hull()
    hull_mesh.remove_degenerate_triangles()
    hull_mesh.remove_duplicated_vertices()
    hull_mesh.remove_unreferenced_vertices()
    hull_mesh.remove_duplicated_triangles()
    hull_mesh.compute_vertex_normals()
    repair_cycles.append("cycle_3_convex_hull_fallback")
    if hull_mesh.is_watertight():
        return hull_mesh, repair_cycles, True

    bbox = point_cloud.get_axis_aligned_bounding_box()
    extent = bbox.get_extent()
    box_mesh = o3d.geometry.TriangleMesh.create_box(
        width=float(extent[0]),
        height=float(extent[1]),
        depth=float(extent[2]),
    )
    if hasattr(bbox, "get_min_bound"):
        box_mesh.translate(bbox.get_min_bound())
    box_mesh.compute_vertex_normals()
    repair_cycles.append("cycle_4_bounding_box_envelope_fallback")
    return box_mesh, repair_cycles, True


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
    point_cloud_scale_m_per_unit: float | None = None,
    poisson_depth: int = 8,
    density_quantile: float = 0.01,
    min_point_count: int = 1000,
    max_axis_ratio: float = 18.0,
    min_density_points_per_m3: float = 1.0,
    voxel_size_m: float | None = None,
    outlier_neighbors: int = 24,
    outlier_std_ratio: float = 2.0,
    min_retained_ratio: float = 0.70,
    segmentation_voxel_size_m: float | None = 0.06,
    cluster_eps_m: float = 0.35,
    cluster_min_points: int = 20,
    max_woodpile_components: int = 2,
    min_component_ratio: float = 0.10,
    normal_radius_m: float = 0.05,
    normal_max_nn: int = 48,
    recompute_normals: bool = True,
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
    scale_factor_m = point_cloud_scale_m_per_unit or _scale_factor_meters(scale_px_per_cm)
    point_cloud.scale(scale_factor_m, center=(0.0, 0.0, 0.0))
    point_cloud = _clean_point_cloud(
        point_cloud,
        voxel_size_m=voxel_size_m,
        outlier_neighbors=outlier_neighbors,
        outlier_std_ratio=outlier_std_ratio,
        min_retained_ratio=min_retained_ratio,
    )
    point_cloud, segmentation_quality = _segment_woodpile_components(
        point_cloud,
        segmentation_voxel_size_m=segmentation_voxel_size_m,
        cluster_eps_m=cluster_eps_m,
        cluster_min_points=cluster_min_points,
        max_components=max_woodpile_components,
        min_component_ratio=min_component_ratio,
    )
    quality = _validate_point_cloud_geometry(
        point_cloud,
        min_point_count=min_point_count,
        max_axis_ratio=max_axis_ratio,
        min_density_points_per_m3=min_density_points_per_m3,
    )
    quality["segmentation"] = segmentation_quality
    _prepare_normals(
        o3d,
        point_cloud,
        normal_radius_m=normal_radius_m,
        normal_max_nn=normal_max_nn,
        recompute_normals=recompute_normals,
    )

    mesh = _poisson_mesh(o3d, point_cloud, poisson_depth, density_quantile)
    mesh, repair_cycles, hull_fallback_applied = _watertight_mesh(o3d, point_cloud, mesh)
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
        mesh_repair_applied=bool(repair_cycles) or hull_fallback_applied,
        repair_cycles=repair_cycles,
        volume_m3=volume_m3,
        bounding_box_m=_bounding_box_m(mesh),
        ground_truth_volume_m3=ground_truth_volume_m3,
        error_percentage=error_percentage,
        vertex_count=len(mesh.vertices),
        triangle_count=len(mesh.triangles),
        point_cloud_quality=quality,
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
        "point_cloud_quality": artifacts.point_cloud_quality,
        "warning": artifacts.warning,
    }
