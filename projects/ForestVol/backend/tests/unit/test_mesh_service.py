from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from backend.app.services.mesh_service import (
    PDI_VOLUME_METHOD,
    MeshProcessingError,
    _segment_woodpile_components,
    generate_preliminary_volumetry,
)


class FakeBoundingBox:
    def __init__(self, extent=None) -> None:
        self._extent = extent or [5.0, 4.0, 3.0]

    def get_extent(self):
        return self._extent


class FakePointCloud:
    def __init__(self, point_count: int = 1500, extent=None) -> None:
        self.scaled_by: float | None = None
        self._extent = extent or [5.0, 4.0, 3.0]
        rng = __import__("numpy").random.default_rng(123)
        self.points = (rng.random((point_count, 3)) * self._extent).tolist()

    def is_empty(self) -> bool:
        return False

    def has_normals(self) -> bool:
        return False

    def estimate_normals(self) -> None:
        return None

    def orient_normals_consistent_tangent_plane(self, _neighbors: int) -> None:
        return None

    def scale(self, factor: float, center: tuple[float, float, float]) -> None:
        assert center == (0.0, 0.0, 0.0)
        self.scaled_by = factor

    def get_axis_aligned_bounding_box(self) -> FakeBoundingBox:
        return FakeBoundingBox(self._extent)


class FakeMesh:
    def __init__(self, watertight: bool = True) -> None:
        self.vertices = [object(), object(), object(), object()]
        self.triangles = [object(), object(), object(), object()]
        self._watertight = watertight
        self.removed_vertex_mask = None

    def remove_vertices_by_mask(self, mask) -> None:
        self.removed_vertex_mask = mask
        return None

    def is_watertight(self) -> bool:
        return self._watertight

    def remove_degenerate_triangles(self) -> None:
        return None

    def remove_duplicated_vertices(self) -> None:
        return None

    def remove_unreferenced_vertices(self) -> None:
        return None

    def remove_duplicated_triangles(self) -> None:
        return None

    def compute_vertex_normals(self) -> None:
        return None

    def scale(self, factor: float, center: tuple[float, float, float]) -> None:
        assert center == (0.0, 0.0, 0.0)
        self.volume_scale = factor ** 3

    def get_volume(self) -> float:
        return 125.0 * getattr(self, "volume_scale", 1.0)

    def get_axis_aligned_bounding_box(self) -> FakeBoundingBox:
        return FakeBoundingBox()


class FakeClusterPointCloud:
    def __init__(self, labels: list[int], extents_by_label: dict[int, list[float]], selected_labels: list[int] | None = None) -> None:
        self._labels = labels
        self._extents_by_label = extents_by_label
        self._selected_labels = selected_labels
        self.points = [object()] * len(labels)

    def voxel_down_sample(self, _voxel_size: float):
        return self

    def cluster_dbscan(self, eps: float, min_points: int, print_progress: bool):
        return self._labels

    def select_by_index(self, indices: list[int]):
        labels = sorted({self._labels[index] for index in indices})
        return FakeClusterPointCloud(
            [self._labels[index] for index in indices],
            self._extents_by_label,
            selected_labels=labels,
        )

    def get_axis_aligned_bounding_box(self) -> FakeBoundingBox:
        labels = self._selected_labels or sorted(set(self._labels))
        extents = [self._extents_by_label[label] for label in labels]
        combined = [max(axis_values) for axis_values in zip(*extents)]
        return FakeBoundingBox(combined)


def _fake_open3d(
    monkeypatch: pytest.MonkeyPatch,
    watertight: bool = True,
    alpha_watertight: bool | None = None,
    point_count: int = 1500,
    extent=None,
) -> FakeMesh:
    fake_mesh = FakeMesh(watertight=watertight)
    alpha_mesh = FakeMesh(watertight=alpha_watertight is True)

    fake_io = types.SimpleNamespace(
        read_point_cloud=lambda _path: FakePointCloud(point_count=point_count, extent=extent),
        write_triangle_mesh=lambda path, _mesh: Path(path).write_text("mesh", encoding="utf-8") is None,
    )
    triangle_mesh = types.SimpleNamespace(
        create_from_point_cloud_poisson=lambda _pcd, depth: (fake_mesh, [1.0, 1.0, 1.0, 1.0])
    )
    if alpha_watertight is not None:
        triangle_mesh.create_from_point_cloud_alpha_shape = lambda _pcd, _alpha: alpha_mesh
    fake_geometry = types.SimpleNamespace(TriangleMesh=triangle_mesh)
    monkeypatch.setitem(
        sys.modules,
        "open3d",
        types.SimpleNamespace(io=fake_io, geometry=fake_geometry),
    )
    return fake_mesh


def test_segment_woodpile_components_prefers_plausible_cluster_over_largest_background() -> None:
    labels = [0] * 100 + [1] * 60 + [2] * 12
    point_cloud = FakeClusterPointCloud(
        labels,
        {
            0: [16.0, 22.0, 13.0],
            1: [8.8, 4.3, 4.3],
            2: [1.0, 1.0, 1.0],
        },
    )

    segmented, quality = _segment_woodpile_components(
        point_cloud,
        segmentation_voxel_size_m=0.06,
        cluster_eps_m=0.35,
        cluster_min_points=10,
        max_components=1,
        min_component_ratio=0.10,
        max_component_height_m=8.0,
        max_component_bbox_volume_m3=500.0,
        max_component_axis_ratio=8.0,
    )

    assert quality["selection_reason"] == "plausible_woodpile_components"
    assert quality["selected_labels"] == [1]
    assert len(segmented.points) == 60
    assert quality["cluster_metrics"]["1"]["plausible_woodpile"] is True


def test_generate_preliminary_volumetry_calculates_volume_for_watertight_mesh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_open3d(monkeypatch, watertight=True)
    monkeypatch.setattr(
        "backend.app.services.mesh_service._estimate_pdi_volume",
        lambda _cloud, _voxel_size: {
            "method": PDI_VOLUME_METHOD,
            "volume_m3": 97.375,
            "voxel_size_m": 0.25,
            "density_threshold_points_per_voxel": 1,
            "hull_density_points_per_m3": 126.0,
            "hull_volume_m3": 156.0,
            "solid_voxels": 6232,
            "occupied_voxels": 1429,
            "dense_voxels": 1429,
        },
    )
    point_cloud_path = tmp_path / "point_cloud.ply"
    point_cloud_path.write_text("ply", encoding="utf-8")

    result = generate_preliminary_volumetry(
        point_cloud_path,
        tmp_path / "processed",
        scale_px_per_cm=2.0,
        point_cloud_scale_m_per_unit=1.0,
        scale_source="test_metric_point_cloud",
        ground_truth_volume_m3=119.74,
    )

    assert result.volume_method == PDI_VOLUME_METHOD
    assert result.mesh_watertight is None
    assert result.mesh_ply_path is None
    assert result.volume_m3 == 97.375
    assert result.error_percentage == pytest.approx(18.678, abs=0.001)
    assert result.bounding_box_m == {"length_m": 5.0, "width_m": 4.0, "height_m": 3.0}
    assert result.confidence_score is not None
    assert result.quality_gates
    assert result.point_cloud_quality["point_count"] == 1500
    assert result.point_cloud_quality["axis_ratio"] == pytest.approx(1.6667, abs=0.0001)
    assert result.point_cloud_quality["scale"] == {
        "point_cloud_scale_m_per_unit": 1.0,
        "source": "test_metric_point_cloud",
        "scale_px_per_cm_observed": 2.0,
        "metric_units_certified": True,
    }
    assert result.pdi_metrics["solid_voxels"] == 6232


def test_generate_preliminary_volumetry_does_not_use_mesh_for_official_volume_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_open3d(monkeypatch, watertight=False)
    point_cloud_path = tmp_path / "point_cloud.ply"
    point_cloud_path.write_text("ply", encoding="utf-8")

    result = generate_preliminary_volumetry(
        point_cloud_path,
        tmp_path / "processed",
        scale_px_per_cm=2.0,
        point_cloud_scale_m_per_unit=1.0,
        scale_source="test_metric_point_cloud",
    )

    assert result.volume_method == PDI_VOLUME_METHOD
    assert result.mesh_watertight is None
    assert result.mesh_repair_applied is False


def test_generate_preliminary_volumetry_uses_alpha_shape_before_hull(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_open3d(monkeypatch, watertight=False, alpha_watertight=True)
    point_cloud_path = tmp_path / "point_cloud.ply"
    point_cloud_path.write_text("ply", encoding="utf-8")

    result = generate_preliminary_volumetry(
        point_cloud_path,
        tmp_path / "processed",
            scale_px_per_cm=2.0,
            point_cloud_scale_m_per_unit=1.0,
            scale_source="test_metric_point_cloud",
            ground_truth_volume_m3=119.74,
            legacy_mesh_enabled=True,
        )

    assert result.mesh_watertight is True
    assert result.mesh_repair_applied is True
    assert any("alpha_shape_fallback" in cycle for cycle in result.repair_cycles)


def test_generate_preliminary_volumetry_rejects_2d_scale_without_metric_point_cloud_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_open3d(monkeypatch)
    point_cloud_path = tmp_path / "point_cloud.ply"
    point_cloud_path.write_text("ply", encoding="utf-8")

    with pytest.raises(MeshProcessingError) as exc_info:
        generate_preliminary_volumetry(point_cloud_path, tmp_path / "processed", scale_px_per_cm=2.0)

    assert "Metric 3D point cloud scale evidence" in str(exc_info.value)
    assert "scale_px_per_cm" in exc_info.value.details
    assert exc_info.value.details["reason"] == "scale_px_per_cm_is_2d_calibration_only"


def test_generate_preliminary_volumetry_requires_positive_metric_point_cloud_scale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_open3d(monkeypatch)
    point_cloud_path = tmp_path / "point_cloud.ply"
    point_cloud_path.write_text("ply", encoding="utf-8")

    with pytest.raises(MeshProcessingError) as exc_info:
        generate_preliminary_volumetry(
            point_cloud_path,
            tmp_path / "processed",
            scale_px_per_cm=2.0,
            point_cloud_scale_m_per_unit=0.0,
            scale_source="test_metric_point_cloud",
        )

    assert "point cloud scale must be positive" in str(exc_info.value)
    assert exc_info.value.details["point_cloud_scale_m_per_unit"] == 0.0


def test_generate_preliminary_volumetry_blocks_sparse_point_cloud(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_open3d(monkeypatch, point_count=20)
    point_cloud_path = tmp_path / "point_cloud.ply"
    point_cloud_path.write_text("ply", encoding="utf-8")

    with pytest.raises(MeshProcessingError) as exc_info:
        generate_preliminary_volumetry(
            point_cloud_path,
            tmp_path / "processed",
            scale_px_per_cm=2.0,
            point_cloud_scale_m_per_unit=1.0,
            scale_source="test_metric_point_cloud",
        )

    assert "insufficient density" in str(exc_info.value)
    assert exc_info.value.details["point_count"] == 20


def test_generate_preliminary_volumetry_blocks_degenerate_point_cloud(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_open3d(monkeypatch, extent=[5.0, 0.0, 3.0])
    point_cloud_path = tmp_path / "point_cloud.ply"
    point_cloud_path.write_text("ply", encoding="utf-8")

    with pytest.raises(MeshProcessingError) as exc_info:
        generate_preliminary_volumetry(
            point_cloud_path,
            tmp_path / "processed",
            scale_px_per_cm=2.0,
            point_cloud_scale_m_per_unit=1.0,
            scale_source="test_metric_point_cloud",
        )

    assert "degenerate" in str(exc_info.value)
    assert exc_info.value.details["bounding_box_extent"] == [5.0, 0.0, 3.0]


def test_generate_preliminary_volumetry_blocks_deformed_point_cloud(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_open3d(monkeypatch, extent=[100.0, 1.0, 1.0])
    point_cloud_path = tmp_path / "point_cloud.ply"
    point_cloud_path.write_text("ply", encoding="utf-8")

    with pytest.raises(MeshProcessingError) as exc_info:
        generate_preliminary_volumetry(
            point_cloud_path,
            tmp_path / "processed",
            scale_px_per_cm=2.0,
            point_cloud_scale_m_per_unit=1.0,
            scale_source="test_metric_point_cloud",
            max_axis_ratio=18.0,
        )

    assert "too deformed" in str(exc_info.value)
    assert exc_info.value.details["axis_ratio"] == pytest.approx(100.0)


def test_generate_preliminary_volumetry_uses_configurable_density_quantile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mesh = _fake_open3d(monkeypatch)
    point_cloud_path = tmp_path / "point_cloud.ply"
    point_cloud_path.write_text("ply", encoding="utf-8")

    generate_preliminary_volumetry(
        point_cloud_path,
        tmp_path / "processed",
        scale_px_per_cm=2.0,
        point_cloud_scale_m_per_unit=1.0,
            scale_source="test_metric_point_cloud",
            density_quantile=0.0,
            legacy_mesh_enabled=True,
        )

    assert fake_mesh.removed_vertex_mask is None
