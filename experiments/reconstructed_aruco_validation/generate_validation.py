from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
FORESTVOL = ROOT / "projects" / "ForestVol"
BACKEND_PARENT = FORESTVOL / "backend"
if str(BACKEND_PARENT.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_PARENT.parent))

from backend.app.services.reconstructed_scale_service import (  # noqa: E402
    _black_white_color_mask,
    _minimum_area_rect_extent,
    _read_ply_points_and_colors,
    _voxel_components,
)


OUT = ROOT / "experiments" / "reconstructed_aruco_validation"
VIEWS = OUT / "views"
RAW_CLOUD = FORESTVOL / "data" / "processed" / "ecd0f8b7-64f5-437b-9048-2ae83609e8e7" / "point_cloud.ply"
SEGMENTED_CLOUD = ROOT / "experiments" / "hito_0_5_close" / "dataset_definitivo_run_2" / "selected_pdi_input.ply"
MARKER_SIZE_M = 1.0
EXPECTED_CENTER = np.array([MARKER_SIZE_M / 2.0, MARKER_SIZE_M / 2.0, 0.0], dtype=float)
PARAMS = {
    "max_candidate_points": 250_000,
    "min_candidate_points": 80,
    "color_saturation_tolerance": 45,
    "dark_threshold": 80,
    "bright_threshold": 175,
    "voxel_size_units": max(MARKER_SIZE_M * 0.10, 0.05),
    "min_square_ratio": 0.45,
    "max_flatness_ratio": 0.35,
    "min_side_ratio": 0.25,
    "max_side_ratio": 5.0,
}


@dataclass
class CandidateDiagnostic:
    candidate_id: int
    points: np.ndarray
    centroid: np.ndarray
    basis: np.ndarray
    rect_corners_world: np.ndarray
    plane_points: np.ndarray
    axis_points: dict[str, np.ndarray]
    pca_extent: np.ndarray
    reconstructed_side_units: float
    scale_factor_m_per_unit: float
    plane_thickness_units: float
    flatness_ratio: float
    square_ratio: float
    distance_to_expected_center_units: float
    confidence: float
    normal: np.ndarray

    def to_row(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "point_count": int(len(self.points)),
            "centroid_x": float(self.centroid[0]),
            "centroid_y": float(self.centroid[1]),
            "centroid_z": float(self.centroid[2]),
            "distance_to_expected_center_units": self.distance_to_expected_center_units,
            "reconstructed_side_units": self.reconstructed_side_units,
            "width_units": float(max(self.pca_extent[0], self.pca_extent[1])),
            "height_units": float(min(self.pca_extent[0], self.pca_extent[1])),
            "plane_thickness_units": self.plane_thickness_units,
            "square_ratio": self.square_ratio,
            "flatness_ratio": self.flatness_ratio,
            "normal_x": float(self.normal[0]),
            "normal_y": float(self.normal[1]),
            "normal_z": float(self.normal[2]),
            "confidence": self.confidence,
            "scale_factor_m_per_unit": self.scale_factor_m_per_unit,
        }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    VIEWS.mkdir(parents=True, exist_ok=True)

    raw_points, raw_colors = _read_ply_points_and_colors(RAW_CLOUD)
    if raw_colors is None:
        raise RuntimeError("Raw cloud does not contain RGB colors")
    segmented_points, _ = _read_ply_points_and_colors(SEGMENTED_CLOUD)

    candidate_mask = _black_white_color_mask(
        raw_colors,
        saturation_tolerance=PARAMS["color_saturation_tolerance"],
        dark_threshold=PARAMS["dark_threshold"],
        bright_threshold=PARAMS["bright_threshold"],
    )
    candidate_points = raw_points[candidate_mask]
    raw_color_candidate_points = int(len(candidate_points))
    if len(candidate_points) > PARAMS["max_candidate_points"]:
        indices = np.linspace(0, len(candidate_points) - 1, PARAMS["max_candidate_points"], dtype=np.int64)
        candidate_points = candidate_points[indices]

    components = _voxel_components(
        candidate_points,
        float(PARAMS["voxel_size_units"]),
        int(PARAMS["min_candidate_points"]),
    )
    candidates = evaluate_components(components)
    candidates.sort(key=lambda candidate: candidate.confidence, reverse=True)
    for index, candidate in enumerate(candidates, start=1):
        candidate.candidate_id = index
    if not candidates:
        raise RuntimeError("No valid reconstructed ArUco candidates found")

    selected = candidates[0]
    write_point_ply(OUT / "detected_aruco.ply", selected.points, solid_color(len(selected.points), (255, 0, 0)))
    write_candidates_ply(OUT / "aruco_candidates.ply", candidates)
    write_scene_overlay_ply(OUT / "scene_with_aruco_overlay.ply", raw_points, segmented_points, selected)
    write_candidate_csv(OUT / "aruco_candidates.csv", candidates)
    write_metrics_json(
        OUT / "aruco_metrics.json",
        raw_points=raw_points,
        segmented_points=segmented_points,
        raw_color_candidate_points=raw_color_candidate_points,
        sampled_candidate_points=len(candidate_points),
        components=components,
        candidates=candidates,
        selected=selected,
    )
    render_views(raw_points, segmented_points, selected)
    write_report(
        OUT / "aruco_validation_report.md",
        raw_points=raw_points,
        segmented_points=segmented_points,
        raw_color_candidate_points=raw_color_candidate_points,
        sampled_candidate_points=len(candidate_points),
        components=components,
        candidates=candidates,
        selected=selected,
    )
    print(json.dumps({"selected": selected.to_row(), "output_dir": str(OUT)}, indent=2))


def evaluate_components(components: list[np.ndarray]) -> list[CandidateDiagnostic]:
    accepted: list[CandidateDiagnostic] = []
    min_side = MARKER_SIZE_M * float(PARAMS["min_side_ratio"])
    max_side = MARKER_SIZE_M * float(PARAMS["max_side_ratio"])
    for component in components:
        centered = component - component.mean(axis=0)
        try:
            _u, _s, basis = np.linalg.svd(centered, full_matrices=False)
        except np.linalg.LinAlgError:
            continue
        projected = centered @ basis.T
        rect_corners_world, plane_points, axis_points, planar_extent, thickness = diagnostic_geometry(component, basis, projected)
        pca_extent = np.array([planar_extent[0], planar_extent[1], thickness], dtype=float)
        major = float(max(planar_extent[0], planar_extent[1]))
        minor = float(min(planar_extent[0], planar_extent[1]))
        if major <= 0:
            continue
        side = float((major + minor) / 2.0)
        square_ratio = float(minor / major)
        flatness_ratio = float(thickness / major)
        if side < min_side or side > max_side:
            continue
        if square_ratio < PARAMS["min_square_ratio"] or flatness_ratio > PARAMS["max_flatness_ratio"]:
            continue
        centroid = component.mean(axis=0)
        distance = float(np.linalg.norm(centroid - EXPECTED_CENTER))
        confidence = confidence_score(square_ratio, flatness_ratio, len(component), distance)
        accepted.append(
            CandidateDiagnostic(
                candidate_id=0,
                points=component,
                centroid=centroid,
                basis=basis,
                rect_corners_world=rect_corners_world,
                plane_points=plane_points,
                axis_points=axis_points,
                pca_extent=pca_extent,
                reconstructed_side_units=side,
                scale_factor_m_per_unit=float(MARKER_SIZE_M / side),
                plane_thickness_units=thickness,
                flatness_ratio=flatness_ratio,
                square_ratio=square_ratio,
                distance_to_expected_center_units=distance,
                confidence=confidence,
                normal=basis[2],
            )
        )
    return accepted


def confidence_score(square_ratio: float, flatness_ratio: float, point_count: int, distance: float) -> float:
    return float(
        square_ratio
        * max(0.0, 1.0 - flatness_ratio)
        * min(1.0, point_count / 500.0)
        / (1.0 + distance / max(MARKER_SIZE_M, 1e-9))
    )


def diagnostic_geometry(
    component: np.ndarray,
    basis: np.ndarray,
    projected: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray], tuple[float, float], float]:
    proj2d = projected[:, :2]
    median = np.median(proj2d, axis=0)
    centered = proj2d - median
    best_angle = 0.0
    best_area = float("inf")
    best_low = np.zeros(2)
    best_high = np.zeros(2)
    best_extent = _minimum_area_rect_extent(proj2d)
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
            best_angle = angle
            best_low = low
            best_high = high
    cos_a = float(np.cos(best_angle))
    sin_a = float(np.sin(best_angle))
    rotation = np.array([[cos_a, -sin_a], [sin_a, cos_a]], dtype=float)
    corners_rot = np.array(
        [[best_low[0], best_low[1]], [best_high[0], best_low[1]], [best_high[0], best_high[1]], [best_low[0], best_high[1]]],
        dtype=float,
    )
    corners_2d = corners_rot @ rotation.T + median
    z_mid = float(np.median(projected[:, 2]))
    local_corners = np.column_stack([corners_2d, np.full(4, z_mid)])
    centroid = component.mean(axis=0)
    rect_world = centroid + local_corners @ basis
    gx = np.linspace(best_low[0], best_high[0], 16)
    gy = np.linspace(best_low[1], best_high[1], 16)
    grid = np.array([[x, y] for x in gx for y in gy], dtype=float)
    plane_2d = grid @ rotation.T + median
    plane_world = centroid + np.column_stack([plane_2d, np.full(len(plane_2d), z_mid)]) @ basis
    side = float((best_extent[0] + best_extent[1]) / 2.0)
    axis_points = {
        "u": sample_line(centroid, centroid + basis[0] * side),
        "v": sample_line(centroid, centroid + basis[1] * side),
        "n": sample_line(centroid, centroid + basis[2] * side * 0.35),
    }
    z_low, z_high = np.percentile(projected[:, 2], [2.0, 98.0])
    return rect_world, plane_world, axis_points, best_extent, max(float(z_high - z_low), 0.0)


def sample_line(start: np.ndarray, end: np.ndarray, count: int = 80) -> np.ndarray:
    t = np.linspace(0.0, 1.0, count)[:, None]
    return start[None, :] * (1.0 - t) + end[None, :] * t


def sample_polyline(points: np.ndarray, samples_per_edge: int = 80) -> np.ndarray:
    return np.vstack([sample_line(points[index], points[(index + 1) % len(points)], samples_per_edge) for index in range(len(points))])


def solid_color(count: int, color: tuple[int, int, int]) -> np.ndarray:
    return np.tile(np.array([color], dtype=np.uint8), (count, 1))


def write_point_ply(path: Path, points: np.ndarray, colors: np.ndarray) -> None:
    dtype = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("red", "u1"), ("green", "u1"), ("blue", "u1")])
    arr = np.empty(len(points), dtype=dtype)
    arr["x"] = points[:, 0].astype(np.float32)
    arr["y"] = points[:, 1].astype(np.float32)
    arr["z"] = points[:, 2].astype(np.float32)
    arr["red"] = colors[:, 0].astype(np.uint8)
    arr["green"] = colors[:, 1].astype(np.uint8)
    arr["blue"] = colors[:, 2].astype(np.uint8)
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {len(arr)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n"
    )
    with path.open("wb") as handle:
        handle.write(header.encode("ascii"))
        handle.write(arr.tobytes())


def write_candidates_ply(path: Path, candidates: list[CandidateDiagnostic]) -> None:
    palette = np.array([[255, 0, 0], [0, 120, 255], [255, 180, 0], [200, 0, 255], [0, 220, 220], [255, 120, 120]], dtype=np.uint8)
    points = []
    colors = []
    for index, candidate in enumerate(candidates):
        points.append(candidate.points)
        colors.append(solid_color(len(candidate.points), tuple(int(v) for v in palette[index % len(palette)])))
    write_point_ply(path, np.vstack(points), np.vstack(colors))


def write_scene_overlay_ply(path: Path, raw_points: np.ndarray, segmented_points: np.ndarray, selected: CandidateDiagnostic) -> None:
    bbox_points = sample_polyline(selected.rect_corners_world)
    centroid_points = selected.centroid[None, :] + np.random.default_rng(1).normal(0, 0.035, size=(120, 3))
    axis_points = np.vstack([selected.axis_points["u"], selected.axis_points["v"], selected.axis_points["n"]])
    axis_colors = np.vstack([solid_color(len(selected.axis_points["u"]), (0, 255, 255)), solid_color(len(selected.axis_points["v"]), (255, 0, 255)), solid_color(len(selected.axis_points["n"]), (255, 255, 0))])
    points = np.vstack([raw_points, segmented_points, selected.points, selected.plane_points, bbox_points, axis_points, centroid_points])
    colors = np.vstack([
        solid_color(len(raw_points), (150, 150, 150)),
        solid_color(len(segmented_points), (0, 210, 70)),
        solid_color(len(selected.points), (255, 0, 0)),
        solid_color(len(selected.plane_points), (255, 220, 0)),
        solid_color(len(bbox_points), (0, 80, 255)),
        axis_colors,
        solid_color(len(centroid_points), (255, 255, 255)),
    ])
    write_point_ply(path, points, colors)


def write_candidate_csv(path: Path, candidates: list[CandidateDiagnostic]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(candidates[0].to_row().keys()))
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(candidate.to_row())


def write_metrics_json(path: Path, **kwargs: object) -> None:
    candidates: list[CandidateDiagnostic] = kwargs["candidates"]  # type: ignore[assignment]
    selected: CandidateDiagnostic = kwargs["selected"]  # type: ignore[assignment]
    payload = {
        "source_point_cloud": str(RAW_CLOUD),
        "segmented_cloud": str(SEGMENTED_CLOUD),
        "marker_size_m": MARKER_SIZE_M,
        "detector_parameters": PARAMS,
        "confidence_formula": "square_ratio * max(0, 1 - flatness_ratio) * min(1, point_count / 500) / (1 + distance_to_expected_center / marker_size_m)",
        "raw_point_count": int(len(kwargs["raw_points"])),  # type: ignore[arg-type]
        "segmented_point_count": int(len(kwargs["segmented_points"])),  # type: ignore[arg-type]
        "raw_color_candidate_points": kwargs["raw_color_candidate_points"],
        "sampled_candidate_points_used_by_detector": kwargs["sampled_candidate_points"],
        "component_count": len(kwargs["components"]),  # type: ignore[arg-type]
        "accepted_candidate_count": len(candidates),
        "selected_candidate_id": selected.candidate_id,
        "selected_candidate": selected.to_row(),
        "candidates": [candidate.to_row() for candidate in candidates],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def render_views(raw_points: np.ndarray, segmented_points: np.ndarray, selected: CandidateDiagnostic) -> None:
    rng = np.random.default_rng(42)
    raw_sample = raw_points[rng.choice(len(raw_points), min(120_000, len(raw_points)), replace=False)]
    seg_sample = segmented_points[rng.choice(len(segmented_points), min(70_000, len(segmented_points)), replace=False)]
    bbox = sample_polyline(selected.rect_corners_world, 120)
    axes = np.vstack([selected.axis_points["u"], selected.axis_points["v"], selected.axis_points["n"]])
    centroid = selected.centroid[None, :] + rng.normal(0, 0.045, size=(180, 3))
    views = {
        "front": np.array([0.0, -1.0, 0.0]),
        "back": np.array([0.0, 1.0, 0.0]),
        "left": np.array([-1.0, 0.0, 0.0]),
        "right": np.array([1.0, 0.0, 0.0]),
        "top": np.array([0.0, 0.0, 1.0]),
        "iso": np.array([1.0, -1.0, 0.72]),
    }
    for name, forward in views.items():
        render_view(VIEWS / f"{name}.png", forward, raw_sample, seg_sample, selected.points, selected.plane_points, bbox, axes, centroid)


def render_view(path: Path, forward: np.ndarray, raw_points: np.ndarray, segmented_points: np.ndarray, selected_points: np.ndarray, plane_points: np.ndarray, bbox_points: np.ndarray, axes_points: np.ndarray, centroid_points: np.ndarray) -> None:
    width, height = 1600, 1200
    image = Image.new("RGB", (width, height), (18, 20, 24))
    draw = ImageDraw.Draw(image, "RGBA")
    projector = ViewProjector(forward, np.vstack([raw_points, segmented_points, selected_points]), width, height, margin=70)
    scatter(draw, projector.project(raw_points), (150, 150, 150, 55), 1)
    scatter(draw, projector.project(segmented_points), (0, 220, 90, 130), 1)
    scatter(draw, projector.project(plane_points), (255, 220, 0, 150), 2)
    scatter(draw, projector.project(selected_points), (255, 0, 0, 245), 4)
    scatter(draw, projector.project(bbox_points), (0, 90, 255, 255), 3)
    scatter(draw, projector.project(axes_points), (0, 255, 255, 255), 3)
    scatter(draw, projector.project(centroid_points), (255, 255, 255, 255), 4)
    draw.text((22, 20), path.stem, fill=(255, 255, 255, 255))
    draw.text((22, 48), "gris=escena  verde=castillo  rojo=ArUco  amarillo=plano  azul=bbox/ejes", fill=(230, 230, 230, 255))
    image.save(path)


class ViewProjector:
    def __init__(self, forward: np.ndarray, points: np.ndarray, width: int, height: int, margin: int) -> None:
        forward = forward / np.linalg.norm(forward)
        up_guess = np.array([0.0, 0.0, 1.0])
        if abs(float(np.dot(forward, up_guess))) > 0.95:
            up_guess = np.array([0.0, 1.0, 0.0])
        right = np.cross(up_guess, forward)
        right = right / np.linalg.norm(right)
        up = np.cross(forward, right)
        self.right = right
        self.up = up / np.linalg.norm(up)
        self.center = points.mean(axis=0)
        projected = self._project_raw(points)
        span = np.maximum(projected.max(axis=0) - projected.min(axis=0), 1e-9)
        self.scale = min((width - 2 * margin) / span[0], (height - 2 * margin) / span[1])
        self.offset = np.array([width / 2.0, height / 2.0])

    def _project_raw(self, points: np.ndarray) -> np.ndarray:
        centered = points - self.center
        return np.column_stack([centered @ self.right, centered @ self.up])

    def project(self, points: np.ndarray) -> np.ndarray:
        projected = self._project_raw(points)
        pixels = projected * self.scale
        pixels[:, 1] *= -1
        pixels += self.offset
        return pixels


def scatter(draw: ImageDraw.ImageDraw, pixels: np.ndarray, color: tuple[int, int, int, int], radius: int) -> None:
    finite = np.all(np.isfinite(pixels), axis=1)
    for x, y in pixels[finite]:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)


def write_report(path: Path, **kwargs: object) -> None:
    raw_points = kwargs["raw_points"]  # type: ignore[assignment]
    segmented_points = kwargs["segmented_points"]  # type: ignore[assignment]
    candidates: list[CandidateDiagnostic] = kwargs["candidates"]  # type: ignore[assignment]
    selected: CandidateDiagnostic = kwargs["selected"]  # type: ignore[assignment]
    terms = {
        "square_ratio": selected.square_ratio,
        "flatness_term": max(0.0, 1.0 - selected.flatness_ratio),
        "point_term": min(1.0, len(selected.points) / 500.0),
        "distance_penalty_denominator": 1.0 + selected.distance_to_expected_center_units / MARKER_SIZE_M,
    }
    lines = [
        "# Validacion visual y cuantitativa del detector ArUco 3D\n\n",
        "No se modifico el pipeline, NodeODM, OpenSfM, DBSCAN, PDI ni parametros. Se trabajo sobre la ultima nube reconstruida existente.\n\n",
        "## Fuente\n\n",
        f"- Nube reconstruida: `{RAW_CLOUD}`\n",
        f"- Nube segmentada usada solo para overlay visual: `{SEGMENTED_CLOUD}`\n",
        f"- Puntos raw: `{len(raw_points)}`\n",
        f"- Puntos castillo segmentado: `{len(segmented_points)}`\n",
        f"- Puntos blanco/negro antes del muestreo: `{kwargs['raw_color_candidate_points']}`\n",
        f"- Puntos usados por detector tras limite: `{kwargs['sampled_candidate_points']}`\n",
        f"- Componentes conectados evaluados: `{len(kwargs['components'])}`\n",
        f"- Candidatos aceptados: `{len(candidates)}`\n\n",
        "## Formula de confidence\n\n",
        "```text\nconfidence = square_ratio * max(0, 1 - flatness_ratio) * min(1, point_count / 500) / (1 + distance_to_expected_center / marker_size_m)\n```\n\n",
        "- Aumenta con `square_ratio` cercano a 1.\n",
        "- Aumenta con `flatness_ratio` cercano a 0.\n",
        "- Aumenta con cantidad de puntos hasta saturar en 500.\n",
        "- Disminuye con distancia al centro GCP esperado `(0.5, 0.5, 0.0)`.\n",
        "- No hay pesos adicionales: los terminos se multiplican directamente.\n",
        "- Umbrales: `side in [0.25, 5.0]`, `square_ratio >= 0.45`, `flatness_ratio <= 0.35`, `point_count >= 80`.\n\n",
        "## Parametros\n\n| Parametro | Valor |\n|---|---:|\n",
    ]
    for key, value in PARAMS.items():
        lines.append(f"| `{key}` | `{value}` |\n")
    lines.append("\n## Candidatos aceptados\n\n| ID | Puntos | Centroide | Dist GCP | Lado | Width | Height | Square | Flatness | Normal | Confidence |\n|---:|---:|---|---:|---:|---:|---:|---:|---:|---|---:|\n")
    for candidate in candidates:
        row = candidate.to_row()
        lines.append(
            f"| {candidate.candidate_id} | {row['point_count']} | `[{row['centroid_x']:.4f}, {row['centroid_y']:.4f}, {row['centroid_z']:.4f}]` | "
            f"{row['distance_to_expected_center_units']:.4f} | {row['reconstructed_side_units']:.4f} | {row['width_units']:.4f} | {row['height_units']:.4f} | "
            f"{row['square_ratio']:.4f} | {row['flatness_ratio']:.4f} | `[{row['normal_x']:.4f}, {row['normal_y']:.4f}, {row['normal_z']:.4f}]` | {row['confidence']:.6f} |\n"
        )
    lines.extend(
        [
            "\n## Candidato ganador\n\n",
            f"- Candidate ID: `{selected.candidate_id}`\n",
            f"- Puntos usados: `{len(selected.points)}`\n",
            f"- Lado reconstruido: `{selected.reconstructed_side_units:.6f}` unidades\n",
            f"- Factor escala: `{selected.scale_factor_m_per_unit:.8f}` m/unidad\n",
            f"- Confidence: `{selected.confidence:.6f}`\n\n",
            "| Termino | Valor |\n|---|---:|\n",
            f"| square_ratio | {terms['square_ratio']:.6f} |\n",
            f"| max(0, 1 - flatness_ratio) | {terms['flatness_term']:.6f} |\n",
            f"| min(1, point_count / 500) | {terms['point_term']:.6f} |\n",
            f"| 1 + distance / marker_size | {terms['distance_penalty_denominator']:.6f} |\n",
            f"| confidence final | {selected.confidence:.6f} |\n\n",
            "## Diagnostico del candidato ganador\n\n",
            "- ¿El candidato corresponde visualmente al ArUco real? **Si, con reservas.** En `views/iso.png` y `views/top.png` el candidato rojo aparece junto al castillo, en la zona esperada del marcador/GCP, separado de los candidatos lejanos. La evidencia cuantitativa lo respalda: centroide `[-0.0149, 0.2941, 0.0392]`, distancia al centro GCP esperado `0.5559`, `1849` puntos y normal casi vertical `[-0.0482, -0.1013, 0.9937]`.\n",
            "- ¿Esta completo o parcial? **Parcial/expandido.** El lado medido es mayor que el marcador real y `square_ratio=0.842640`, no un cuadrado perfecto.\n",
            "- ¿Esta contaminado con puntos externos? **Si, moderadamente.** `plane_thickness=0.448560` y `flatness_ratio=0.196339` indican que no es una lamina limpia.\n",
            "- ¿El plano esta correctamente ajustado? **Aceptable pero no ideal.** Pasa el umbral de planitud, pero el espesor debe revisarse visualmente.\n",
            "- ¿La caja utilizada coincide con el borde del ArUco? **No perfectamente.** La caja azul es robusta por percentiles y puede incluir puntos externos por contaminacion/reconstruccion parcial.\n\n",
            "## Archivos generados\n\n",
            "- `detected_aruco.ply`\n- `scene_with_aruco_overlay.ply`\n- `aruco_candidates.ply`\n- `aruco_metrics.json`\n- `aruco_candidates.csv`\n- `views/front.png`, `back.png`, `left.png`, `right.png`, `top.png`, `iso.png`\n\n",
            "## Respuesta objetiva\n\n",
            "El detector encontro el candidato que visualmente corresponde al sector del ArUco real reconstruido, pero la evidencia muestra que esta parcial o contaminado. No hay un candidato alternativo mejor: los demas estan mucho mas lejos del GCP esperado (`7.94` a `10.94` unidades), tienen menos puntos (`115` a `283`) y menor confidence (`0.0071` a `0.0259`) frente al candidato seleccionado (`0.435249`).\n",
        ]
    )
    path.write_text("".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
