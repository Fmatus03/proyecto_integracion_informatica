"""Preliminary mesh and volume service for ForestVol Hito 0.5."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage
from scipy.spatial import ConvexHull, cKDTree


PDI_VOLUME_METHOD = "point_density_integration"
PDI_VOXEL_SIZE_M = 0.25
OFFICIAL_VOLUME_FILTER_METHOD = "obb_plus_curvature"
OFFICIAL_VOLUME_FILTER_OBB_PERCENTILE = 80.0
OFFICIAL_VOLUME_FILTER_CURVATURE_PERCENTILE = 80.0


class MeshProcessingError(Exception):
    """Raised when Hito 0.5 mesh generation or volume estimation cannot proceed."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


@dataclass(frozen=True)
class MeshArtifacts:
    """Artifacts and metrics produced by preliminary volumetry."""

    point_cloud_path: str
    mesh_ply_path: str | None
    mesh_glb_path: str | None
    mesh_watertight: bool | None
    mesh_repair_applied: bool
    repair_cycles: list[str] = field(default_factory=list)
    volume_m3: float | None = None
    volume_method: str = PDI_VOLUME_METHOD
    confidence_score: float | None = None
    confidence_level: str | None = None
    quality_gates: list[dict[str, Any]] = field(default_factory=list)
    diagnostic: list[str] = field(default_factory=list)
    pdi_metrics: dict[str, Any] = field(default_factory=dict)
    legacy_mesh_enabled: bool = False
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


def _resolve_metric_point_cloud_scale(
    point_cloud_scale_m_per_unit: float | None,
    scale_source: str | None,
    scale_px_per_cm: float | None,
) -> tuple[float, dict[str, Any]]:
    if point_cloud_scale_m_per_unit is None:
        raise MeshProcessingError(
            "Metric 3D point cloud scale evidence is required before volumetry",
            {
                "scale_px_per_cm": scale_px_per_cm,
                "scale_source": scale_source,
                "reason": "scale_px_per_cm_is_2d_calibration_only",
            },
        )
    if point_cloud_scale_m_per_unit <= 0:
        raise MeshProcessingError(
            "Metric 3D point cloud scale must be positive",
            {
                "point_cloud_scale_m_per_unit": point_cloud_scale_m_per_unit,
                "scale_source": scale_source,
            },
        )
    if not scale_source:
        raise MeshProcessingError(
            "Metric 3D point cloud scale source is required before volumetry",
            {"point_cloud_scale_m_per_unit": point_cloud_scale_m_per_unit},
        )
    return float(point_cloud_scale_m_per_unit), {
        "point_cloud_scale_m_per_unit": float(point_cloud_scale_m_per_unit),
        "source": scale_source,
        "scale_px_per_cm_observed": scale_px_per_cm,
        "metric_units_certified": True,
    }


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
    max_component_height_m: float,
    max_component_bbox_volume_m3: float,
    max_component_axis_ratio: float,
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
    cluster_metrics: dict[int, dict[str, Any]] = {}
    candidate_labels: list[int] = []
    for ordered_index in order:
        label = int(values[ordered_index])
        count = int(counts[ordered_index])
        indices = np.where(labels == label)[0]
        component = clustering_cloud.select_by_index(indices.tolist())
        extent = np.asarray(component.get_axis_aligned_bounding_box().get_extent(), dtype=float)
        positive_extent = extent[extent > 0]
        bbox_volume = float(np.prod(positive_extent)) if positive_extent.size == 3 else 0.0
        axis_ratio = float(positive_extent.max() / positive_extent.min()) if positive_extent.size else float("inf")
        density = float(count / bbox_volume) if bbox_volume > 0 else 0.0
        plausible = (
            count >= cluster_min_points
            and (max_component_height_m <= 0 or float(extent[2]) <= max_component_height_m)
            and (max_component_bbox_volume_m3 <= 0 or bbox_volume <= max_component_bbox_volume_m3)
            and (not np.isfinite(axis_ratio) or max_component_axis_ratio <= 0 or axis_ratio <= max_component_axis_ratio)
        )
        cluster_metrics[label] = {
            "count": count,
            "extent": [round(float(value), 4) for value in extent.tolist()],
            "bbox_volume_m3": round(bbox_volume, 4),
            "density_points_per_m3": round(density, 4),
            "axis_ratio": round(axis_ratio, 4) if np.isfinite(axis_ratio) else None,
            "plausible_woodpile": plausible,
        }
        if count / main_count < min_component_ratio:
            continue
        if plausible:
            candidate_labels.append(label)

    if candidate_labels:
        candidate_labels.sort(
            key=lambda label: (
                cluster_metrics[label]["count"],
                cluster_metrics[label]["density_points_per_m3"],
            ),
            reverse=True,
        )
        selected_labels = candidate_labels[:max_components]
        selection_reason = "plausible_woodpile_components"
    else:
        selected_labels = []
        for ordered_index in order:
            label = int(values[ordered_index])
            count = int(counts[ordered_index])
            if len(selected_labels) >= max_components:
                break
            if count / main_count < min_component_ratio:
                continue
            selected_labels.append(label)
        selection_reason = "dominant_components_fallback"

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
        "max_component_height_m": max_component_height_m,
        "max_component_bbox_volume_m3": max_component_bbox_volume_m3,
        "max_component_axis_ratio": max_component_axis_ratio,
        "selection_reason": selection_reason,
        "selected_labels": selected_labels,
        "selected_point_count": int(selected_indices.size),
        "cluster_counts": {str(int(values[i])): int(counts[i]) for i in order[:8]},
        "cluster_metrics": {str(label): cluster_metrics[label] for label in selected_labels},
    }


def _local_pca_curvature(points: np.ndarray, k: int = 20) -> np.ndarray:
    if len(points) < 4:
        return np.zeros(len(points), dtype=float)
    tree = cKDTree(points)
    neighbor_count = min(k + 1, len(points))
    _, indices = tree.query(points, k=neighbor_count)
    neighbors = points[indices[:, 1:]]
    centered = neighbors - points[:, None, :]
    covariance = np.einsum("nki,nkj->nij", centered, centered) / max(1, neighbor_count - 1)
    eigenvalues = np.maximum(np.linalg.eigvalsh(covariance), 1e-12)
    return eigenvalues[:, 0] / eigenvalues.sum(axis=1)


def _filter_obb_plus_curvature(
    point_cloud: Any,
    obb_percentile: float = OFFICIAL_VOLUME_FILTER_OBB_PERCENTILE,
    curvature_percentile: float = OFFICIAL_VOLUME_FILTER_CURVATURE_PERCENTILE,
) -> tuple[Any, dict[str, Any]]:
    if not hasattr(point_cloud, "select_by_index"):
        return point_cloud, {
            "applied": False,
            "method": OFFICIAL_VOLUME_FILTER_METHOD,
            "reason": "point_cloud_select_by_index_unsupported",
            "obb_percentile": float(obb_percentile),
            "curvature_percentile": float(curvature_percentile),
        }
    points = _point_cloud_points(point_cloud)
    if not (0 < obb_percentile <= 100):
        raise MeshProcessingError(
            "Official volume filter obb_percentile must be in (0, 100]",
            {"obb_percentile": obb_percentile},
        )
    if not (0 < curvature_percentile <= 100):
        raise MeshProcessingError(
            "Official volume filter curvature_percentile must be in (0, 100]",
            {"curvature_percentile": curvature_percentile},
        )

    center = points.mean(axis=0)
    centered = points - center
    eigenvalues, eigenvectors = np.linalg.eigh(np.cov(centered.T))
    axes = eigenvectors[:, np.argsort(eigenvalues)[::-1]]
    local = centered @ axes

    margin = (100.0 - obb_percentile) / 2.0
    keep_obb = np.ones(len(points), dtype=bool)
    bounds: list[list[float]] = []
    for axis_index in range(3):
        lower, upper = np.percentile(local[:, axis_index], [margin, 100.0 - margin])
        keep_obb &= (local[:, axis_index] >= lower) & (local[:, axis_index] <= upper)
        bounds.append([float(lower), float(upper)])

    obb_indices = np.where(keep_obb)[0]
    if len(obb_indices) < 4:
        raise MeshProcessingError(
            "Official volume filter removed too much structure at OBB step",
            {
                "method": OFFICIAL_VOLUME_FILTER_METHOD,
                "input_point_count": int(len(points)),
                "after_obb_point_count": int(len(obb_indices)),
            },
        )

    obb_points = points[obb_indices]
    curvature = _local_pca_curvature(obb_points, k=20)
    curvature_threshold = float(np.percentile(curvature, curvature_percentile))
    keep_curvature = curvature <= curvature_threshold
    filtered_indices = obb_indices[keep_curvature]
    if len(filtered_indices) < 4:
        raise MeshProcessingError(
            "Official volume filter removed too much structure at curvature step",
            {
                "method": OFFICIAL_VOLUME_FILTER_METHOD,
                "input_point_count": int(len(points)),
                "after_curvature_point_count": int(len(filtered_indices)),
            },
        )

    filtered_cloud = point_cloud.select_by_index(filtered_indices.tolist())
    return filtered_cloud, {
        "applied": True,
        "method": OFFICIAL_VOLUME_FILTER_METHOD,
        "insertion_point": "after_dbscan_before_pdi",
        "obb_percentile": float(obb_percentile),
        "curvature_percentile": float(curvature_percentile),
        "obb_local_bounds": bounds,
        "curvature_threshold": curvature_threshold,
        "input_point_count": int(len(points)),
        "after_obb_point_count": int(len(obb_indices)),
        "after_curvature_point_count": int(len(filtered_indices)),
        "removed_point_count": int(len(points) - len(filtered_indices)),
        "removed_percentage": round(float((len(points) - len(filtered_indices)) / len(points) * 100.0), 6),
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


def _mesh_edge_metrics(mesh: Any) -> dict[str, Any]:
    try:
        triangles = np.asarray(mesh.triangles, dtype=int)
    except Exception:
        triangles = np.asarray([])
    if triangles.size == 0:
        return {
            "unique_edges": 0,
            "boundary_edges": 0,
            "non_manifold_edges_by_count": 0,
        }
    edges: dict[tuple[int, int], int] = {}
    for triangle in triangles:
        for start, end in ((triangle[0], triangle[1]), (triangle[1], triangle[2]), (triangle[2], triangle[0])):
            key = tuple(sorted((int(start), int(end))))
            edges[key] = edges.get(key, 0) + 1
    return {
        "unique_edges": len(edges),
        "boundary_edges": sum(1 for count in edges.values() if count == 1),
        "non_manifold_edges_by_count": sum(1 for count in edges.values() if count > 2),
    }


def _mesh_surface_area(mesh: Any) -> float | None:
    try:
        return float(mesh.get_surface_area())
    except Exception:
        return None


def _safe_mesh_volume(mesh: Any) -> float | None:
    try:
        return float(mesh.get_volume())
    except Exception:
        return None


def _point_cloud_points(point_cloud: Any) -> np.ndarray:
    points = np.asarray(point_cloud.points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3:
        raise MeshProcessingError(
            "Point cloud must contain Nx3 metric coordinates for PDI volumetry",
            {"point_shape": list(points.shape)},
        )
    points = points[np.all(np.isfinite(points), axis=1)]
    if len(points) < 4:
        raise MeshProcessingError(
            "Point cloud has insufficient finite points for PDI volumetry",
            {"point_count": int(len(points))},
        )
    return points


def _pdi_occupancy_grid(points: np.ndarray, voxel_size_m: float) -> tuple[np.ndarray, np.ndarray]:
    origin = points.min(axis=0) - 4 * voxel_size_m
    dims = np.ceil((points.max(axis=0) + 4 * voxel_size_m - origin) / voxel_size_m).astype(int) + 1
    idx = np.floor((points - origin) / voxel_size_m).astype(np.int32)
    grid = np.zeros(tuple(dims.tolist()), dtype=bool)
    grid[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    return grid, origin


def _pdi_solid_from_occupancy(occupancy: np.ndarray) -> np.ndarray:
    structure = ndimage.generate_binary_structure(3, 2)
    shell = ndimage.binary_dilation(occupancy, structure=structure, iterations=2)
    solid = ndimage.binary_fill_holes(shell)
    solid = ndimage.binary_closing(solid, structure=structure, iterations=1)
    solid = ndimage.binary_fill_holes(solid)
    labels, count = ndimage.label(solid, structure=structure)
    if count > 1:
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        solid = labels == int(np.argmax(sizes))
    return solid


def _point_cloud_bounding_box_m(point_cloud: Any) -> dict[str, float]:
    extent = point_cloud.get_axis_aligned_bounding_box().get_extent()
    return {
        "length_m": round(float(extent[0]), 4),
        "width_m": round(float(extent[1]), 4),
        "height_m": round(float(extent[2]), 4),
    }


def _estimate_pdi_volume(point_cloud: Any, voxel_size_m: float = PDI_VOXEL_SIZE_M) -> dict[str, Any]:
    points = _point_cloud_points(point_cloud)
    hull_volume = float(ConvexHull(points).volume)
    hull_density = len(points) / hull_volume if hull_volume > 0 else 0.0
    occupancy, origin = _pdi_occupancy_grid(points, voxel_size_m)
    counts = np.zeros_like(occupancy, dtype=np.int32)
    idx = np.floor((points - origin) / voxel_size_m).astype(np.int32)
    np.add.at(counts, (idx[:, 0], idx[:, 1], idx[:, 2]), 1)
    threshold = max(1, int(np.ceil(hull_density * (voxel_size_m ** 3) * 0.35)))
    dense = counts >= threshold
    solid = _pdi_solid_from_occupancy(dense)
    volume_m3 = float(np.count_nonzero(solid) * (voxel_size_m ** 3))
    return {
        "method": PDI_VOLUME_METHOD,
        "volume_m3": round(volume_m3, 4),
        "voxel_size_m": voxel_size_m,
        "density_threshold_points_per_voxel": threshold,
        "hull_density_points_per_m3": round(float(hull_density), 6),
        "hull_volume_m3": round(float(hull_volume), 6),
        "solid_voxels": int(np.count_nonzero(solid)),
        "occupied_voxels": int(np.count_nonzero(occupancy)),
        "dense_voxels": int(np.count_nonzero(dense)),
    }


def _nearest_neighbor_quality(points: np.ndarray, sample_limit: int = 12000) -> dict[str, Any]:
    sample = points
    if len(points) > sample_limit:
        sample = points[np.linspace(0, len(points) - 1, sample_limit).astype(int)]
    distances, _ = cKDTree(sample).query(sample, k=2)
    nn = distances[:, 1]
    nn = nn[np.isfinite(nn) & (nn > 0)]
    if len(nn) == 0:
        return {
            "median_nn_m": None,
            "mean_nn_m": None,
            "local_density_cv": None,
            "isolated_point_ratio": 1.0,
            "outlier_ratio": 1.0,
        }
    q1, q3 = np.quantile(nn, [0.25, 0.75])
    outlier_limit = q3 + 1.5 * (q3 - q1)
    isolated_limit = max(float(np.median(nn)) * 4.0, outlier_limit)
    return {
        "median_nn_m": round(float(np.median(nn)), 6),
        "mean_nn_m": round(float(np.mean(nn)), 6),
        "local_density_cv": round(float(np.std(nn) / np.mean(nn)), 6) if np.mean(nn) else None,
        "isolated_point_ratio": round(float(np.mean(nn > isolated_limit)), 6),
        "outlier_ratio": round(float(np.mean(nn > outlier_limit)), 6),
    }


def _coverage_quality(points: np.ndarray, bins: int = 6) -> dict[str, Any]:
    mins = points.min(axis=0)
    extent = np.maximum(points.max(axis=0) - mins, 1e-9)
    normalized = np.clip((points - mins) / extent, 0.0, 0.999999)
    idx = np.floor(normalized * bins).astype(np.int32)
    grid = np.zeros((bins, bins, bins), dtype=bool)
    grid[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    interior = grid[1:-1, 1:-1, 1:-1]
    face_ratios = {
        "x_min": float(np.mean(grid[0, :, :])),
        "x_max": float(np.mean(grid[-1, :, :])),
        "y_min": float(np.mean(grid[:, 0, :])),
        "y_max": float(np.mean(grid[:, -1, :])),
        "z_min": float(np.mean(grid[:, :, 0])),
        "z_max": float(np.mean(grid[:, :, -1])),
    }
    lateral = [face_ratios[key] for key in ("x_min", "x_max", "y_min", "y_max")]
    return {
        "spatial_coverage_ratio": round(float(np.count_nonzero(grid) / grid.size), 6),
        "interior_hole_ratio": round(float(np.mean(~interior)), 6) if interior.size else None,
        "lateral_coverage_ratio": round(float(np.mean(lateral)), 6),
        "top_coverage_ratio": round(face_ratios["z_max"], 6),
        "bottom_coverage_ratio": round(face_ratios["z_min"], 6),
    }


def _pdi_component_quality(points: np.ndarray, voxel_size_m: float = PDI_VOXEL_SIZE_M) -> dict[str, Any]:
    occupancy, _ = _pdi_occupancy_grid(points, voxel_size_m)
    labels, count = ndimage.label(occupancy, structure=ndimage.generate_binary_structure(3, 2))
    sizes = np.bincount(labels.ravel()) if count else np.asarray([0])
    if len(sizes) > 1:
        sizes[0] = 0
    dominant = int(sizes.max()) if len(sizes) else 0
    occupied = int(np.count_nonzero(occupancy))
    return {
        "voxel_components": int(count),
        "dominant_component_voxel_ratio": round(float(dominant / occupied), 6) if occupied else 0.0,
    }


def _gate_status(value: float, warning: float, fail: float, higher_is_worse: bool = True) -> str:
    if higher_is_worse:
        if value >= fail:
            return "FAIL"
        if value >= warning:
            return "WARNING"
        return "PASS"
    if value <= fail:
        return "FAIL"
    if value <= warning:
        return "WARNING"
    return "PASS"


def _quality_gate(name: str, status: str, metric: str, value: Any, explanation: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "metric": metric,
        "value": value,
        "explanation": explanation,
    }


def _pdi_quality_gates(point_cloud: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    points = _point_cloud_points(point_cloud)
    bbox = _point_cloud_quality(point_cloud)
    nn = _nearest_neighbor_quality(points)
    coverage = _coverage_quality(points)
    components = _pdi_component_quality(points)
    metrics = {**bbox, **nn, **coverage, **components}
    gates = [
        _quality_gate("segmentation.isolated_points", _gate_status(float(nn["isolated_point_ratio"]), 0.03, 0.08), "isolated_point_ratio", nn["isolated_point_ratio"], "High isolated-point ratio indicates possible background leakage or sparse segmentation."),
        _quality_gate("segmentation.outliers", _gate_status(float(nn["outlier_ratio"]), 0.10, 0.20), "outlier_ratio", nn["outlier_ratio"], "Nearest-neighbor outliers can expand PDI support and inflate volume."),
        _quality_gate("segmentation.mean_density", _gate_status(float(bbox["density_points_per_m3"]), 15.0, 8.0, higher_is_worse=False), "density_points_per_m3", bbox["density_points_per_m3"], "Low global density increases sensitivity to voxelization."),
        _quality_gate("segmentation.bbox_aspect", _gate_status(float(bbox["axis_ratio"] or 0.0), 4.5, 7.0), "axis_ratio", bbox["axis_ratio"], "Extreme bounding-box ratios can indicate missing views or background contamination."),
        _quality_gate("coverage.spatial_distribution", _gate_status(float(coverage["spatial_coverage_ratio"]), 0.08, 0.04, higher_is_worse=False), "spatial_coverage_ratio", coverage["spatial_coverage_ratio"], "Low occupied-cell coverage suggests incomplete spatial support."),
        _quality_gate("coverage.interior_holes", _gate_status(float(coverage["interior_hole_ratio"]), 0.82, 0.92), "interior_hole_ratio", coverage["interior_hole_ratio"], "High empty-interior ratio is a proxy for large holes or missing regions."),
        _quality_gate("coverage.lateral", _gate_status(float(coverage["lateral_coverage_ratio"]), 0.18, 0.10, higher_is_worse=False), "lateral_coverage_ratio", coverage["lateral_coverage_ratio"], "Low lateral coverage can cause structured underestimation."),
        _quality_gate("coverage.top", _gate_status(float(coverage["top_coverage_ratio"]), 0.15, 0.08, higher_is_worse=False), "top_coverage_ratio", coverage["top_coverage_ratio"], "Low top coverage can indicate missing upper surface observations."),
        _quality_gate("coverage.bottom", _gate_status(float(coverage["bottom_coverage_ratio"]), 0.08, 0.03, higher_is_worse=False), "bottom_coverage_ratio", coverage["bottom_coverage_ratio"], "Low bottom coverage is expected in aerial capture but reduces volumetric confidence."),
        _quality_gate("geometry.point_count", _gate_status(float(bbox["point_count"]), 10000.0, 5000.0, higher_is_worse=False), "point_count", bbox["point_count"], "Low point count reduces estimator stability."),
        _quality_gate("geometry.components", _gate_status(float(components["voxel_components"]), 150.0, 300.0), "voxel_components", components["voxel_components"], "Many disconnected occupied components indicate fragmentation or background leakage."),
        _quality_gate("geometry.spatial_consistency", _gate_status(float(components["dominant_component_voxel_ratio"]), 0.70, 0.50, higher_is_worse=False), "dominant_component_voxel_ratio", components["dominant_component_voxel_ratio"], "Low dominant-component ratio indicates fragmented spatial support."),
    ]
    return gates, metrics


def _pdi_confidence_score(quality_gates: list[dict[str, Any]]) -> tuple[float, str, list[str]]:
    score = 100.0
    diagnostic: list[str] = []
    for gate in quality_gates:
        if gate["status"] == "FAIL":
            score -= 15.0
            diagnostic.append(f"{gate['name']}: FAIL - {gate['explanation']}")
        elif gate["status"] == "WARNING":
            score -= 5.0
            diagnostic.append(f"{gate['name']}: WARNING - {gate['explanation']}")
    score = max(0.0, min(100.0, score))
    if score >= 80:
        level = "HIGH"
    elif score >= 60:
        level = "MEDIUM"
    elif score >= 40:
        level = "LOW"
    else:
        level = "CRITICAL"
    return round(score, 2), level, diagnostic or ["No quality gate produced WARNING or FAIL."]


def _mesh_topology_metrics(mesh: Any) -> dict[str, Any]:
    edge_metrics = _mesh_edge_metrics(mesh)
    component_count = None
    component_triangles: list[int] = []
    if hasattr(mesh, "cluster_connected_triangles"):
        try:
            labels, counts, _areas = mesh.cluster_connected_triangles()
            label_values = np.asarray(labels, dtype=int)
            count_values = np.asarray(counts, dtype=int)
            component_count = int(count_values.size)
            component_triangles = [int(value) for value in count_values.tolist()]
        except Exception:
            component_count = None
    try:
        non_manifold_edges = int(len(mesh.get_non_manifold_edges(allow_boundary_edges=False)))
    except Exception:
        non_manifold_edges = None
    try:
        non_manifold_vertices = int(len(mesh.get_non_manifold_vertices()))
    except Exception:
        non_manifold_vertices = None
    try:
        orientable = bool(mesh.is_orientable())
    except Exception:
        orientable = None
    volume = _safe_mesh_volume(mesh)
    surface_area = _mesh_surface_area(mesh)
    bbox = _bounding_box_m(mesh)
    bbox_volume = bbox["length_m"] * bbox["width_m"] * bbox["height_m"]
    return {
        "vertices": len(mesh.vertices),
        "triangles": len(mesh.triangles),
        "components": component_count,
        "component_triangles": component_triangles,
        "watertight": bool(mesh.is_watertight()),
        "volume_m3": None if volume is None else round(float(volume), 4),
        "surface_area_m2": None if surface_area is None else round(float(surface_area), 4),
        "surface_volume_ratio": (
            None
            if volume is None or abs(volume) <= 1e-9 or surface_area is None
            else round(float(surface_area) / abs(float(volume)), 6)
        ),
        "unique_edges": edge_metrics["unique_edges"],
        "boundary_edges": edge_metrics["boundary_edges"],
        "boundary_edge_ratio": round(edge_metrics["boundary_edges"] / max(1, edge_metrics["unique_edges"]), 6),
        "non_manifold_edges_by_count": edge_metrics["non_manifold_edges_by_count"],
        "non_manifold_edges_open3d": non_manifold_edges,
        "non_manifold_vertices": non_manifold_vertices,
        "orientable": orientable,
        "bounding_box_m": bbox,
        "bbox_volume_m3": round(float(bbox_volume), 4),
    }


def _mesh_component_table(o3d: Any, mesh: Any) -> list[dict[str, Any]]:
    if not hasattr(mesh, "cluster_connected_triangles"):
        return []
    try:
        labels, counts, _areas = mesh.cluster_connected_triangles()
    except Exception:
        return []
    label_values = np.asarray(labels, dtype=int)
    count_values = np.asarray(counts, dtype=int)
    total_triangles = max(1, len(mesh.triangles))
    components: list[dict[str, Any]] = []
    for component_label, triangle_count in enumerate(count_values.tolist()):
        component_mesh = o3d.geometry.TriangleMesh(mesh)
        remove_mask = label_values != component_label
        component_mesh.remove_triangles_by_mask(remove_mask)
        component_mesh.remove_unreferenced_vertices()
        volume = _safe_mesh_volume(component_mesh)
        components.append(
            {
                "component": int(component_label),
                "vertices": len(component_mesh.vertices),
                "triangles": int(triangle_count),
                "triangle_percentage": round(float(triangle_count) / total_triangles * 100.0, 4),
                "volume_m3": None if volume is None else round(float(volume), 4),
                "bounding_box_m": _bounding_box_m(component_mesh),
                "watertight": bool(component_mesh.is_watertight()),
            }
        )
    components.sort(key=lambda item: item["triangles"], reverse=True)
    return components


def _remove_small_mesh_components(
    o3d: Any,
    mesh: Any,
    min_component_ratio: float = 0.01,
    min_component_triangles: int = 100,
) -> tuple[Any, dict[str, Any]]:
    if not hasattr(mesh, "cluster_connected_triangles"):
        return mesh, {"applied": False, "reason": "unsupported"}
    try:
        labels, counts, _areas = mesh.cluster_connected_triangles()
    except Exception:
        return mesh, {"applied": False, "reason": "component_clustering_failed"}
    label_values = np.asarray(labels, dtype=int)
    count_values = np.asarray(counts, dtype=int)
    if count_values.size <= 1:
        return mesh, {"applied": False, "reason": "single_component"}
    dominant_count = int(count_values.max())
    keep_labels = [
        int(index)
        for index, count in enumerate(count_values.tolist())
        if int(count) >= min_component_triangles and float(count) / dominant_count >= min_component_ratio
    ]
    if not keep_labels:
        keep_labels = [int(np.argmax(count_values))]
    recovered = o3d.geometry.TriangleMesh(mesh)
    recovered.remove_triangles_by_mask(~np.isin(label_values, keep_labels))
    recovered.remove_unreferenced_vertices()
    removed_triangles = int(len(mesh.triangles) - len(recovered.triangles))
    return recovered, {
        "applied": True,
        "method": "remove_small_connected_components",
        "input_components": int(count_values.size),
        "kept_components": len(keep_labels),
        "kept_labels": keep_labels,
        "dominant_component_triangles": dominant_count,
        "removed_triangles": removed_triangles,
        "removed_triangle_percentage": round(removed_triangles / max(1, len(mesh.triangles)) * 100.0, 4),
    }


def _recover_poisson_mesh(o3d: Any, mesh: Any) -> tuple[Any, list[str], dict[str, Any]]:
    repair_cycles = _repair_mesh(mesh)
    recovery_report: dict[str, Any] = {
        "poisson_raw": _mesh_topology_metrics(mesh),
        "component_table": _mesh_component_table(o3d, mesh),
        "steps": [],
    }
    if mesh.is_watertight():
        recovery_report["accepted"] = True
        recovery_report["acceptance_reason"] = "poisson_watertight_after_basic_repair"
        return mesh, repair_cycles, recovery_report

    mesh, component_step = _remove_small_mesh_components(o3d, mesh)
    recovery_report["steps"].append(component_step)
    if component_step.get("applied"):
        repair_cycles.append("cycle_3_poisson_small_components_removed")

    for method_name in (
        "remove_degenerate_triangles",
        "remove_duplicated_vertices",
        "remove_unreferenced_vertices",
        "remove_duplicated_triangles",
        "remove_non_manifold_edges",
    ):
        if hasattr(mesh, method_name):
            before = _mesh_topology_metrics(mesh)
            getattr(mesh, method_name)()
            after = _mesh_topology_metrics(mesh)
            recovery_report["steps"].append(
                {
                    "applied": True,
                    "method": method_name,
                    "before": before,
                    "after": after,
                    "removed_vertices": before["vertices"] - after["vertices"],
                    "removed_triangles": before["triangles"] - after["triangles"],
                }
            )

    if hasattr(mesh, "orient_triangles"):
        try:
            oriented = bool(mesh.orient_triangles())
        except Exception:
            oriented = False
        recovery_report["steps"].append({"applied": oriented, "method": "orient_triangles"})
        if oriented:
            repair_cycles.append("cycle_4_poisson_triangles_oriented")
    mesh.compute_vertex_normals()
    repair_cycles.append("cycle_5_poisson_recovery_cleanup")

    final_metrics = _mesh_topology_metrics(mesh)
    recovery_report["poisson_recovered"] = final_metrics
    volume = _safe_mesh_volume(mesh)
    component_table = _mesh_component_table(o3d, mesh)
    dominant_triangle_pct = component_table[0]["triangle_percentage"] if component_table else 0.0
    boundary_ratio = final_metrics["boundary_edges"] / max(1, final_metrics["unique_edges"]) if "unique_edges" in final_metrics else 1.0
    non_manifold_edges = final_metrics["non_manifold_edges_open3d"]
    acceptable = (
        bool(mesh.is_watertight())
        and volume is not None
        and dominant_triangle_pct >= 95.0
        and final_metrics["components"] in (None, 1)
        and final_metrics["boundary_edges"] == 0
        and (non_manifold_edges is None or non_manifold_edges == 0)
    )
    recovery_report["accepted"] = acceptable
    recovery_report["acceptance_metrics"] = {
        "dominant_triangle_percentage": dominant_triangle_pct,
        "boundary_edge_ratio": round(boundary_ratio, 6),
        "volume_available": volume is not None,
        "non_manifold_edges_open3d": non_manifold_edges,
    }
    recovery_report["acceptance_reason"] = (
        "poisson_recovered_watertight_single_dominant_component"
        if acceptable
        else "poisson_recovery_failed_acceptance_criteria"
    )
    return mesh, repair_cycles, recovery_report


def _mesh_acceptance_evaluation(
    o3d: Any,
    candidate_mesh: Any,
    reference_mesh: Any | None = None,
    min_dominant_triangle_pct: float = 99.0,
    max_bbox_extent_delta_ratio: float = 0.02,
    max_surface_area_delta_ratio: float = 0.08,
) -> dict[str, Any]:
    metrics = _mesh_topology_metrics(candidate_mesh)
    component_table = _mesh_component_table(o3d, candidate_mesh)
    dominant_pct = component_table[0]["triangle_percentage"] if component_table else 0.0
    non_manifold_edges = metrics["non_manifold_edges_open3d"]
    reasons: list[str] = []

    if not metrics["watertight"]:
        reasons.append("not_watertight")
    if metrics["volume_m3"] is None:
        reasons.append("volume_unavailable")
    if dominant_pct < min_dominant_triangle_pct:
        reasons.append("dominant_component_unstable")
    if metrics["components"] not in (None, 1):
        reasons.append("multiple_components")
    if metrics["boundary_edges"] != 0:
        reasons.append("open_boundary_edges")
    if non_manifold_edges not in (None, 0):
        reasons.append("non_manifold_edges")

    reference_comparison: dict[str, Any] | None = None
    if reference_mesh is not None:
        reference_metrics = _mesh_topology_metrics(reference_mesh)
        candidate_extent = np.asarray(list(metrics["bounding_box_m"].values()), dtype=float)
        reference_extent = np.asarray(list(reference_metrics["bounding_box_m"].values()), dtype=float)
        extent_delta = np.abs(candidate_extent - reference_extent) / np.maximum(np.abs(reference_extent), 1e-9)
        candidate_area = metrics["surface_area_m2"]
        reference_area = reference_metrics["surface_area_m2"]
        area_delta = None
        if candidate_area is not None and reference_area not in (None, 0):
            area_delta = abs(candidate_area - reference_area) / abs(reference_area)
        reference_comparison = {
            "bbox_extent_delta_ratio": [round(float(value), 6) for value in extent_delta.tolist()],
            "max_bbox_extent_delta_ratio": round(float(extent_delta.max()), 6),
            "surface_area_delta_ratio": None if area_delta is None else round(float(area_delta), 6),
        }
        if float(extent_delta.max()) > max_bbox_extent_delta_ratio:
            reasons.append("bbox_changed_vs_poisson_reference")
        if area_delta is not None and area_delta > max_surface_area_delta_ratio:
            reasons.append("surface_area_changed_vs_poisson_reference")

    return {
        "accepted": not reasons,
        "reasons": reasons,
        "metrics": metrics,
        "dominant_triangle_percentage": dominant_pct,
        "reference_comparison": reference_comparison,
        "criteria": {
            "requires_watertight": True,
            "requires_volume": True,
            "min_dominant_triangle_pct": min_dominant_triangle_pct,
            "max_bbox_extent_delta_ratio": max_bbox_extent_delta_ratio,
            "max_surface_area_delta_ratio": max_surface_area_delta_ratio,
            "requires_zero_boundary_edges": True,
            "requires_no_non_manifold_edges": True,
        },
    }


def _poisson_vertex_hull(o3d: Any, mesh: Any) -> Any | None:
    if not hasattr(o3d.geometry, "PointCloud") or not hasattr(o3d.utility, "Vector3dVector"):
        return None
    vertices = np.asarray(mesh.vertices, dtype=float)
    if vertices.size == 0:
        return None
    point_cloud = o3d.geometry.PointCloud()
    point_cloud.points = o3d.utility.Vector3dVector(vertices)
    if not hasattr(point_cloud, "compute_convex_hull"):
        return None
    hull_mesh, _ = point_cloud.compute_convex_hull()
    hull_mesh.remove_degenerate_triangles()
    hull_mesh.remove_duplicated_vertices()
    hull_mesh.remove_unreferenced_vertices()
    hull_mesh.remove_duplicated_triangles()
    hull_mesh.compute_vertex_normals()
    return hull_mesh


def _fill_boundary_edge_loops(o3d: Any, mesh: Any, max_boundary_edges: int = 2000) -> tuple[Any, dict[str, Any]]:
    try:
        triangles = np.asarray(mesh.triangles, dtype=int)
    except Exception:
        return mesh, {"applied": False, "reason": "triangles_unavailable"}
    if triangles.size == 0:
        return mesh, {"applied": False, "reason": "empty_mesh"}

    edge_counts: dict[tuple[int, int], int] = {}
    for triangle in triangles:
        for start, end in ((triangle[0], triangle[1]), (triangle[1], triangle[2]), (triangle[2], triangle[0])):
            key = tuple(sorted((int(start), int(end))))
            edge_counts[key] = edge_counts.get(key, 0) + 1
    boundary_edges = [edge for edge, count in edge_counts.items() if count == 1]
    if not boundary_edges:
        return mesh, {"applied": False, "reason": "no_boundary_edges"}
    if len(boundary_edges) > max_boundary_edges:
        return mesh, {
            "applied": False,
            "reason": "too_many_boundary_edges",
            "boundary_edges": len(boundary_edges),
            "max_boundary_edges": max_boundary_edges,
        }

    adjacency: dict[int, list[int]] = {}
    unused = {edge for edge in boundary_edges}
    for start, end in boundary_edges:
        adjacency.setdefault(start, []).append(end)
        adjacency.setdefault(end, []).append(start)

    loops: list[list[int]] = []
    while unused:
        start, next_vertex = unused.pop()
        loop = [start, next_vertex]
        previous = start
        current = next_vertex
        while current != start:
            candidates = [vertex for vertex in adjacency.get(current, []) if vertex != previous]
            if not candidates:
                break
            following = candidates[0]
            edge = tuple(sorted((current, following)))
            if edge not in unused and following != start:
                break
            if edge in unused:
                unused.remove(edge)
            previous, current = current, following
            if current != start:
                loop.append(current)
            if len(loop) > len(boundary_edges) + 1:
                break
        if current == start and len(loop) >= 3:
            loops.append(loop)

    fill_triangles: list[list[int]] = []
    for loop in loops:
        anchor = loop[0]
        for index in range(1, len(loop) - 1):
            fill_triangles.append([anchor, loop[index], loop[index + 1]])
    if not fill_triangles:
        return mesh, {
            "applied": False,
            "reason": "no_closed_boundary_loops",
            "boundary_edges": len(boundary_edges),
        }

    filled_mesh = o3d.geometry.TriangleMesh(mesh)
    combined_triangles = np.vstack([triangles, np.asarray(fill_triangles, dtype=int)])
    filled_mesh.triangles = o3d.utility.Vector3iVector(combined_triangles)
    filled_mesh.remove_degenerate_triangles()
    filled_mesh.remove_duplicated_triangles()
    filled_mesh.remove_unreferenced_vertices()
    if hasattr(filled_mesh, "orient_triangles"):
        try:
            filled_mesh.orient_triangles()
        except Exception:
            pass
    filled_mesh.compute_vertex_normals()
    return filled_mesh, {
        "applied": True,
        "method": "fill_boundary_edge_loops",
        "boundary_edges": len(boundary_edges),
        "closed_loops": len(loops),
        "added_triangles": len(fill_triangles),
    }


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


def _alpha_shape_mesh(
    o3d: Any,
    point_cloud: Any,
    alpha_min_m: float,
    alpha_max_m: float,
    alpha_extent_ratio: float,
) -> tuple[Any | None, float | None]:
    if not hasattr(o3d.geometry.TriangleMesh, "create_from_point_cloud_alpha_shape"):
        return None, None

    extent = np.asarray(point_cloud.get_axis_aligned_bounding_box().get_extent(), dtype=float)
    positive_extent = extent[extent > 0]
    if positive_extent.size == 0:
        return None, None

    alpha_m = float(np.clip(positive_extent.min() * alpha_extent_ratio, alpha_min_m, alpha_max_m))
    mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_alpha_shape(point_cloud, alpha_m)
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_vertices()
    mesh.remove_unreferenced_vertices()
    mesh.remove_duplicated_triangles()
    mesh.compute_vertex_normals()
    return mesh, alpha_m


def _watertight_mesh(
    o3d: Any,
    point_cloud: Any,
    poisson_mesh: Any,
    alpha_shape_fallback: bool,
    alpha_min_m: float,
    alpha_max_m: float,
    alpha_extent_ratio: float,
) -> tuple[Any, list[str], bool, dict[str, Any]]:
    poisson_mesh, repair_cycles, recovery_report = _recover_poisson_mesh(o3d, poisson_mesh)
    if recovery_report.get("accepted"):
        return poisson_mesh, repair_cycles, False, recovery_report

    filled_mesh = poisson_mesh
    for fill_attempt in range(1, 4):
        filled_mesh, fill_step = _fill_boundary_edge_loops(o3d, filled_mesh)
        fill_step["attempt"] = fill_attempt
        recovery_report["steps"].append(fill_step)
        if not fill_step.get("applied"):
            break
        if hasattr(filled_mesh, "remove_non_manifold_edges"):
            filled_mesh.remove_non_manifold_edges()
        filled_mesh.remove_degenerate_triangles()
        filled_mesh.remove_duplicated_triangles()
        filled_mesh.remove_unreferenced_vertices()
        if hasattr(filled_mesh, "orient_triangles"):
            try:
                filled_mesh.orient_triangles()
            except Exception:
                pass
        filled_mesh.compute_vertex_normals()
        recovery_report[f"poisson_hole_filled_attempt_{fill_attempt}"] = _mesh_topology_metrics(filled_mesh)
        repair_cycles.append(f"cycle_6_poisson_boundary_loops_filled_attempt_{fill_attempt}")
        if filled_mesh.is_watertight() and _safe_mesh_volume(filled_mesh) is not None:
            recovery_report["accepted"] = True
            recovery_report["acceptance_reason"] = "poisson_boundary_loops_filled_watertight"
            return filled_mesh, repair_cycles, False, recovery_report

    poisson_hull = _poisson_vertex_hull(o3d, filled_mesh)
    if poisson_hull is not None:
        hull_acceptance = _mesh_acceptance_evaluation(o3d, poisson_hull, reference_mesh=poisson_mesh)
        recovery_report["poisson_vertex_hull"] = {
            "metrics": _mesh_topology_metrics(poisson_hull),
            "acceptance": hull_acceptance,
            "fallback_reason": recovery_report.get("acceptance_reason"),
        }
        recovery_report["steps"].append(
            {
                "applied": False,
                "method": "poisson_vertex_hull",
                "reason": "diagnostic_only_global_envelope_not_primary_surface",
                "accepted_by_final_surface_criteria": hull_acceptance["accepted"],
            }
        )

    if alpha_shape_fallback:
        alpha_mesh, alpha_m = _alpha_shape_mesh(
            o3d,
            point_cloud,
            alpha_min_m=alpha_min_m,
            alpha_max_m=alpha_max_m,
            alpha_extent_ratio=alpha_extent_ratio,
        )
        if alpha_mesh is not None:
            repair_cycles.append(f"cycle_3_alpha_shape_fallback_alpha_{alpha_m:.3f}m")
            recovery_report["alpha_shape"] = {
                "alpha_m": alpha_m,
                "metrics": _mesh_topology_metrics(alpha_mesh),
                "fallback_reason": recovery_report.get("acceptance_reason"),
            }
            if alpha_mesh.is_watertight():
                return alpha_mesh, repair_cycles, True, recovery_report

    if not hasattr(point_cloud, "compute_convex_hull"):
        recovery_report["fallback_failure"] = "point_cloud_compute_convex_hull_unavailable"
        return poisson_mesh, repair_cycles, False, recovery_report

    hull_mesh, _ = point_cloud.compute_convex_hull()
    hull_mesh.remove_degenerate_triangles()
    hull_mesh.remove_duplicated_vertices()
    hull_mesh.remove_unreferenced_vertices()
    hull_mesh.remove_duplicated_triangles()
    hull_mesh.compute_vertex_normals()
    repair_cycles.append("cycle_4_convex_hull_fallback")
    recovery_report["convex_hull"] = {
        "metrics": _mesh_topology_metrics(hull_mesh),
        "fallback_reason": recovery_report.get("acceptance_reason"),
    }
    if hull_mesh.is_watertight():
        return hull_mesh, repair_cycles, True, recovery_report

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
    repair_cycles.append("cycle_5_bounding_box_envelope_fallback")
    recovery_report["bounding_box_envelope"] = {
        "metrics": _mesh_topology_metrics(box_mesh),
        "fallback_reason": "convex_hull_not_watertight",
    }
    return box_mesh, repair_cycles, True, recovery_report


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
    scale_source: str | None = None,
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
    max_component_height_m: float = 8.0,
    max_component_bbox_volume_m3: float = 500.0,
    max_component_axis_ratio: float = 8.0,
    alpha_shape_fallback: bool = True,
    alpha_min_m: float = 1.5,
    alpha_max_m: float = 3.0,
    alpha_extent_ratio: float = 0.52,
    max_segmented_height_m: float = 12.0,
    fallback_woodpile_components: int = 2,
    normal_radius_m: float = 0.05,
    normal_max_nn: int = 48,
    recompute_normals: bool = True,
    mesh_name: str = "preliminary_mesh",
    pdi_voxel_size_m: float = PDI_VOXEL_SIZE_M,
    legacy_mesh_enabled: bool = False,
) -> MeshArtifacts:
    """Generate official PDI volumetry and optional legacy mesh artifacts."""

    o3d = _require_open3d()
    point_cloud_path = Path(point_cloud_path)
    if not point_cloud_path.exists():
        raise MeshProcessingError(
            "Point cloud artifact does not exist",
            {"point_cloud_path": str(point_cloud_path)},
        )

    point_cloud = _load_point_cloud(o3d, point_cloud_path)
    scale_factor_m, scale_quality = _resolve_metric_point_cloud_scale(
        point_cloud_scale_m_per_unit=point_cloud_scale_m_per_unit,
        scale_source=scale_source,
        scale_px_per_cm=scale_px_per_cm,
    )
    point_cloud.scale(scale_factor_m, center=(0.0, 0.0, 0.0))
    point_cloud = _clean_point_cloud(
        point_cloud,
        voxel_size_m=voxel_size_m,
        outlier_neighbors=outlier_neighbors,
        outlier_std_ratio=outlier_std_ratio,
        min_retained_ratio=min_retained_ratio,
    )
    cleaned_point_cloud = point_cloud
    point_cloud, segmentation_quality = _segment_woodpile_components(
        point_cloud,
        segmentation_voxel_size_m=segmentation_voxel_size_m,
        cluster_eps_m=cluster_eps_m,
        cluster_min_points=cluster_min_points,
        max_components=max_woodpile_components,
        min_component_ratio=min_component_ratio,
        max_component_height_m=max_component_height_m,
        max_component_bbox_volume_m3=max_component_bbox_volume_m3,
        max_component_axis_ratio=max_component_axis_ratio,
    )
    segmented_extent = np.asarray(point_cloud.get_axis_aligned_bounding_box().get_extent(), dtype=float)
    if (
        max_segmented_height_m > 0
        and segmented_extent.size == 3
        and segmented_extent[2] > max_segmented_height_m
        and fallback_woodpile_components < max_woodpile_components
    ):
        point_cloud, fallback_quality = _segment_woodpile_components(
            cleaned_point_cloud,
            segmentation_voxel_size_m=segmentation_voxel_size_m,
            cluster_eps_m=cluster_eps_m,
            cluster_min_points=cluster_min_points,
            max_components=fallback_woodpile_components,
            min_component_ratio=min_component_ratio,
            max_component_height_m=max_component_height_m,
            max_component_bbox_volume_m3=max_component_bbox_volume_m3,
            max_component_axis_ratio=max_component_axis_ratio,
        )
        fallback_quality["fallback_reason"] = "segmented_height_exceeded"
        fallback_quality["previous_segmentation"] = segmentation_quality
        fallback_quality["max_segmented_height_m"] = max_segmented_height_m
        segmentation_quality = fallback_quality

    point_cloud, official_filter_quality = _filter_obb_plus_curvature(point_cloud)
    quality = _validate_point_cloud_geometry(
        point_cloud,
        min_point_count=min_point_count,
        max_axis_ratio=max_axis_ratio,
        min_density_points_per_m3=min_density_points_per_m3,
    )
    quality["scale"] = scale_quality
    quality["segmentation"] = segmentation_quality
    quality["official_volume_filter"] = official_filter_quality
    quality_gates, pdi_quality_metrics = _pdi_quality_gates(point_cloud)
    confidence_score, confidence_level, diagnostic = _pdi_confidence_score(quality_gates)
    pdi_metrics = _estimate_pdi_volume(point_cloud, pdi_voxel_size_m)
    quality["pdi_quality"] = pdi_quality_metrics

    volume_m3 = round(float(pdi_metrics["volume_m3"]), 4)
    error_percentage = None
    if ground_truth_volume_m3 is not None:
        error_percentage = round(abs(volume_m3 - ground_truth_volume_m3) / ground_truth_volume_m3 * 100.0, 4)

    mesh = None
    mesh_ply_path = None
    mesh_glb_path = None
    mesh_watertight = None
    mesh_repair_applied = False
    repair_cycles: list[str] = []
    vertex_count = 0
    triangle_count = 0
    if legacy_mesh_enabled:
        _prepare_normals(
            o3d,
            point_cloud,
            normal_radius_m=normal_radius_m,
            normal_max_nn=normal_max_nn,
            recompute_normals=recompute_normals,
        )
        mesh = _poisson_mesh(o3d, point_cloud, poisson_depth, density_quantile)
        mesh, repair_cycles, hull_fallback_applied, mesh_recovery_quality = _watertight_mesh(
            o3d,
            point_cloud,
            mesh,
            alpha_shape_fallback=alpha_shape_fallback,
            alpha_min_m=alpha_min_m,
            alpha_max_m=alpha_max_m,
            alpha_extent_ratio=alpha_extent_ratio,
        )
        quality["legacy_mesh_recovery"] = mesh_recovery_quality
        mesh.compute_vertex_normals()
        mesh_watertight = bool(mesh.is_watertight())
        mesh_repair_applied = bool(repair_cycles) or hull_fallback_applied
        mesh_ply_path, mesh_glb_path = _export_mesh(o3d, mesh, output_dir, mesh_name)
        vertex_count = len(mesh.vertices)
        triangle_count = len(mesh.triangles)

    return MeshArtifacts(
        point_cloud_path=str(point_cloud_path),
        mesh_ply_path=None if mesh_ply_path is None else str(mesh_ply_path),
        mesh_glb_path=None if mesh_glb_path is None else str(mesh_glb_path),
        mesh_watertight=mesh_watertight,
        mesh_repair_applied=mesh_repair_applied,
        repair_cycles=repair_cycles,
        volume_m3=volume_m3,
        volume_method=PDI_VOLUME_METHOD,
        confidence_score=confidence_score,
        confidence_level=confidence_level,
        quality_gates=quality_gates,
        diagnostic=diagnostic,
        pdi_metrics=pdi_metrics,
        legacy_mesh_enabled=legacy_mesh_enabled,
        bounding_box_m=_point_cloud_bounding_box_m(point_cloud),
        ground_truth_volume_m3=ground_truth_volume_m3,
        error_percentage=error_percentage,
        vertex_count=vertex_count,
        triangle_count=triangle_count,
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
        "volume_method": artifacts.volume_method,
        "confidence_score": artifacts.confidence_score,
        "confidence_level": artifacts.confidence_level,
        "quality_gates": artifacts.quality_gates,
        "diagnostic": artifacts.diagnostic,
        "pdi_metrics": artifacts.pdi_metrics,
        "legacy_mesh_enabled": artifacts.legacy_mesh_enabled,
        "bounding_box_m": artifacts.bounding_box_m,
        "ground_truth_volume_m3": artifacts.ground_truth_volume_m3,
        "error_percentage": artifacts.error_percentage,
        "vertex_count": artifacts.vertex_count,
        "triangle_count": artifacts.triangle_count,
        "point_cloud_quality": artifacts.point_cloud_quality,
        "warning": artifacts.warning,
    }
