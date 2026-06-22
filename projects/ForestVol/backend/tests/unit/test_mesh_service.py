from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from backend.app.services.mesh_service import (
    MeshProcessingError,
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
        self.points = [object()] * point_count
        self._extent = extent

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


def _fake_open3d(
    monkeypatch: pytest.MonkeyPatch,
    watertight: bool = True,
    point_count: int = 1500,
    extent=None,
) -> FakeMesh:
    fake_mesh = FakeMesh(watertight=watertight)

    fake_io = types.SimpleNamespace(
        read_point_cloud=lambda _path: FakePointCloud(point_count=point_count, extent=extent),
        write_triangle_mesh=lambda path, _mesh: Path(path).write_text("mesh", encoding="utf-8") is None,
    )
    fake_geometry = types.SimpleNamespace(
        TriangleMesh=types.SimpleNamespace(
            create_from_point_cloud_poisson=lambda _pcd, depth: (fake_mesh, [1.0, 1.0, 1.0, 1.0])
        )
    )
    monkeypatch.setitem(
        sys.modules,
        "open3d",
        types.SimpleNamespace(io=fake_io, geometry=fake_geometry),
    )
    return fake_mesh


def test_generate_preliminary_volumetry_calculates_volume_for_watertight_mesh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_open3d(monkeypatch, watertight=True)
    point_cloud_path = tmp_path / "point_cloud.ply"
    point_cloud_path.write_text("ply", encoding="utf-8")

    result = generate_preliminary_volumetry(
        point_cloud_path,
        tmp_path / "processed",
        scale_px_per_cm=2.0,
        ground_truth_volume_m3=119.74,
    )

    assert result.mesh_watertight is True
    assert result.volume_m3 == 125.0
    assert result.error_percentage == pytest.approx(4.393, abs=0.001)
    assert result.bounding_box_m == {"length_m": 5.0, "width_m": 4.0, "height_m": 3.0}
    assert result.point_cloud_quality["point_count"] == 1500
    assert result.point_cloud_quality["axis_ratio"] == pytest.approx(1.6667, abs=0.0001)
    assert Path(result.mesh_ply_path).exists()


def test_generate_preliminary_volumetry_blocks_non_watertight_mesh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_open3d(monkeypatch, watertight=False)
    point_cloud_path = tmp_path / "point_cloud.ply"
    point_cloud_path.write_text("ply", encoding="utf-8")

    with pytest.raises(MeshProcessingError) as exc_info:
        generate_preliminary_volumetry(point_cloud_path, tmp_path / "processed", scale_px_per_cm=2.0)

    assert "not watertight" in str(exc_info.value)
    assert exc_info.value.details["mesh_watertight"] is False


def test_generate_preliminary_volumetry_requires_positive_scale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_open3d(monkeypatch)
    point_cloud_path = tmp_path / "point_cloud.ply"
    point_cloud_path.write_text("ply", encoding="utf-8")

    with pytest.raises(MeshProcessingError) as exc_info:
        generate_preliminary_volumetry(point_cloud_path, tmp_path / "processed", scale_px_per_cm=0.0)

    assert "scale_px_per_cm" in exc_info.value.details


def test_generate_preliminary_volumetry_blocks_sparse_point_cloud(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_open3d(monkeypatch, point_count=20)
    point_cloud_path = tmp_path / "point_cloud.ply"
    point_cloud_path.write_text("ply", encoding="utf-8")

    with pytest.raises(MeshProcessingError) as exc_info:
        generate_preliminary_volumetry(point_cloud_path, tmp_path / "processed", scale_px_per_cm=2.0)

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
        generate_preliminary_volumetry(point_cloud_path, tmp_path / "processed", scale_px_per_cm=2.0)

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
        density_quantile=0.0,
    )

    assert fake_mesh.removed_vertex_mask is None
