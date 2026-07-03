from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services.reconstructed_scale_service import (
    ReconstructedScaleError,
    estimate_reconstructed_aruco_scale,
)


def _write_ascii_ply(path: Path, rows: list[tuple[float, float, float, int, int, int]]) -> None:
    lines = [
        "ply",
        "format ascii 1.0",
        f"element vertex {len(rows)}",
        "property float x",
        "property float y",
        "property float z",
        "property uchar red",
        "property uchar green",
        "property uchar blue",
        "end_header",
    ]
    lines.extend(f"{x} {y} {z} {r} {g} {b}" for x, y, z, r, g, b in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _synthetic_marker_rows(side_units: float = 2.0) -> list[tuple[float, float, float, int, int, int]]:
    rows: list[tuple[float, float, float, int, int, int]] = []
    steps = 24
    for ix in range(steps):
        for iy in range(steps):
            x = side_units * ix / (steps - 1)
            y = side_units * iy / (steps - 1)
            z = 0.01 if (ix + iy) % 5 == 0 else 0.0
            color = 20 if ((ix // 6) + (iy // 6)) % 2 == 0 else 235
            rows.append((x, y, z, color, color, color))
    for index in range(120):
        x = 8.0 + (index % 12) * 0.2
        y = -5.0 + (index // 12) * 0.2
        rows.append((x, y, 1.0, 120, 70, 30))
    return rows


def test_estimate_reconstructed_aruco_scale_measures_synthetic_square(tmp_path: Path) -> None:
    cloud_path = tmp_path / "point_cloud.ply"
    _write_ascii_ply(cloud_path, _synthetic_marker_rows(side_units=2.0))

    result = estimate_reconstructed_aruco_scale(
        cloud_path,
        marker_size_m=1.0,
        min_candidate_points=60,
    )

    assert result.selected_candidate is not None
    assert result.selected_candidate.point_count >= 500
    assert result.selected_candidate.square_ratio > 0.9
    assert result.selected_candidate.flatness_ratio < 0.02
    assert result.scale_factor_m_per_unit == pytest.approx(0.5, abs=0.03)
    payload = result.to_payload()
    assert payload["method"] == "reconstructed_aruco_3d"
    assert payload["scale_factor_m_per_unit"] == pytest.approx(0.5, abs=0.03)


def test_estimate_reconstructed_aruco_scale_requires_colors(tmp_path: Path) -> None:
    cloud_path = tmp_path / "point_cloud.ply"
    cloud_path.write_text(
        "\n".join(
            [
                "ply",
                "format ascii 1.0",
                "element vertex 100",
                "property float x",
                "property float y",
                "property float z",
                "end_header",
                *[f"{index % 10} {index // 10} 0" for index in range(100)],
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ReconstructedScaleError) as exc_info:
        estimate_reconstructed_aruco_scale(cloud_path, marker_size_m=1.0, min_candidate_points=60)

    assert "colors are required" in str(exc_info.value)
