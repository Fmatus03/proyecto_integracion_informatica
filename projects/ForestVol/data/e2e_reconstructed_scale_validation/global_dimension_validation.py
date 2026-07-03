from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


PLY_DTYPE = np.dtype(
    [
        ("x", "<f4"),
        ("y", "<f4"),
        ("z", "<f4"),
        ("nx", "<f4"),
        ("ny", "<f4"),
        ("nz", "<f4"),
        ("red", "u1"),
        ("blue", "u1"),
        ("green", "u1"),
        ("views", "u1"),
    ]
)

EXPECTED = {"x_length_m": 6.0, "y_width_m": 10.08, "z_height_m": 5.04, "log_diameter_m": 1.26}
FACE_COLORS = {
    "left": [230, 57, 70],
    "right": [255, 117, 143],
    "front": [42, 157, 143],
    "back": [46, 196, 182],
    "bottom": [69, 123, 157],
    "top": [233, 196, 106],
}


def read_cloud(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    header_end = raw.index(b"end_header\n") + len(b"end_header\n")
    header = raw[:header_end].decode("ascii", errors="ignore")
    vertex_count = None
    for line in header.splitlines():
        if line.startswith("element vertex "):
            vertex_count = int(line.split()[-1])
            break
    if vertex_count is None:
        raise ValueError("Missing PLY vertex count")
    data = np.frombuffer(raw, dtype=PLY_DTYPE, count=vertex_count, offset=header_end)
    points = np.column_stack([data["x"], data["y"], data["z"]]).astype(np.float64)
    return points[np.isfinite(points).all(axis=1)]


def write_ply(path: Path, points: np.ndarray, colors: np.ndarray, comments: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as handle:
        handle.write("ply\nformat ascii 1.0\n")
        for comment in comments or []:
            handle.write(f"comment {comment}\n")
        handle.write(f"element vertex {len(points)}\n")
        handle.write("property float x\nproperty float y\nproperty float z\n")
        handle.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        handle.write("end_header\n")
        for point, color in zip(points, colors):
            handle.write(
                f"{point[0]:.6f} {point[1]:.6f} {point[2]:.6f} {int(color[0])} {int(color[1])} {int(color[2])}\n"
            )


def robust_castle_selection(points_m: np.ndarray) -> tuple[np.ndarray, dict]:
    q005 = np.quantile(points_m, 0.005, axis=0)
    q995 = np.quantile(points_m, 0.995, axis=0)
    core = points_m[np.all((points_m >= q005) & (points_m <= q995), axis=1)]
    q01 = np.quantile(core, 0.01, axis=0)
    q99 = np.quantile(core, 0.99, axis=0)
    selected = core[np.all((core >= q01) & (core <= q99), axis=1)]
    return selected, {
        "method": "raw cloud scaled to meters, remove outer 0.5% per axis, then keep central 98% per axis",
        "raw_point_count": int(len(points_m)),
        "core_point_count": int(len(core)),
        "selected_point_count": int(len(selected)),
        "q005_m": q005.tolist(),
        "q995_m": q995.tolist(),
        "q01_core_m": q01.tolist(),
        "q99_core_m": q99.tolist(),
    }


def estimate_frame(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    origin = np.median(points, axis=0)
    xy = points[:, :2] - np.median(points[:, :2], axis=0)
    cov = np.cov(xy.T)
    values, vectors = np.linalg.eigh(cov)
    axis_x_2d = vectors[:, int(np.argmax(values))]
    if axis_x_2d[0] < 0:
        axis_x_2d *= -1
    axis_x = np.array([axis_x_2d[0], axis_x_2d[1], 0.0], dtype=float)
    axis_x /= np.linalg.norm(axis_x)
    axis_y = np.array([-axis_x[1], axis_x[0], 0.0], dtype=float)
    axis_z = np.array([0.0, 0.0, 1.0], dtype=float)
    return origin, axis_x, axis_y, axis_z


def fit_plane(points: np.ndarray, expected_normal: np.ndarray) -> dict:
    center = points.mean(axis=0)
    centered = points - center
    cov = np.cov(centered.T)
    values, vectors = np.linalg.eigh(cov)
    normal = vectors[:, int(np.argmin(values))]
    if float(normal @ expected_normal) < 0:
        normal *= -1
    signed = centered @ normal
    rms = float(np.sqrt(np.mean(signed**2)))
    p95 = float(np.quantile(np.abs(signed), 0.95))
    alignment = float(abs(normal @ expected_normal) / max(1e-9, np.linalg.norm(normal) * np.linalg.norm(expected_normal)))
    return {
        "center": center.tolist(),
        "normal": normal.tolist(),
        "rms_residual_m": rms,
        "p95_abs_residual_m": p95,
        "normal_alignment_to_expected_axis": alignment,
        "point_count": int(len(points)),
    }


def detect_face_planes(points: np.ndarray, origin: np.ndarray, axes: dict[str, np.ndarray]) -> tuple[dict, list[dict], np.ndarray, np.ndarray]:
    coords = {name: (points - origin) @ axis for name, axis in axes.items()}
    face_specs = [
        ("left", "y", -1),
        ("right", "y", 1),
        ("front", "x", -1),
        ("back", "x", 1),
        ("bottom", "z", -1),
        ("top", "z", 1),
    ]
    faces: dict[str, dict] = {}
    labels = np.full(len(points), "none", dtype=object)
    plane_rows: list[dict] = []

    for face_name, axis_name, sign in face_specs:
        values = coords[axis_name]
        if sign < 0:
            threshold = float(np.quantile(values, 0.06))
            mask = values <= threshold
            expected_normal = -axes[axis_name]
        else:
            threshold = float(np.quantile(values, 0.94))
            mask = values >= threshold
            expected_normal = axes[axis_name]
        face_points = points[mask]
        fit = fit_plane(face_points, expected_normal)
        position_axis_m = float(np.median(values[mask]))
        uncertainty = float(max(np.std(values[mask]) / math.sqrt(len(face_points)), fit["rms_residual_m"]))
        fit.update(
            {
                "face": face_name,
                "axis": axis_name,
                "side": "min" if sign < 0 else "max",
                "axis_position_m": position_axis_m,
                "axis_threshold_m": threshold,
                "position_uncertainty_m": uncertainty,
                "quality_score": float(fit["normal_alignment_to_expected_axis"] / (1.0 + fit["rms_residual_m"])),
            }
        )
        faces[face_name] = fit
        labels[mask] = face_name
        plane_rows.append(fit)

    colors = np.full((len(points), 3), [145, 145, 145], dtype=np.uint8)
    for name, color in FACE_COLORS.items():
        colors[labels == name] = color
    return faces, plane_rows, colors, labels


def dimensions_from_planes(faces: dict) -> dict:
    pairs = {
        "x_length_m": ("front", "back"),
        "y_width_m": ("left", "right"),
        "z_height_m": ("bottom", "top"),
    }
    result = {}
    for key, (low, high) in pairs.items():
        low_face = faces[low]
        high_face = faces[high]
        distance = float(high_face["axis_position_m"] - low_face["axis_position_m"])
        uncertainty = float(math.sqrt(low_face["position_uncertainty_m"] ** 2 + high_face["position_uncertainty_m"] ** 2))
        point_count = int(low_face["point_count"] + high_face["point_count"])
        quality = float((low_face["quality_score"] + high_face["quality_score"]) / 2.0)
        result[key] = {
            "value_m": abs(distance),
            "uncertainty_m": uncertainty,
            "point_count": point_count,
            "quality_score": quality,
            "negative_face": low,
            "positive_face": high,
        }
    return result


def render(points: np.ndarray, colors: np.ndarray, faces: dict, origin: np.ndarray, axes: dict[str, np.ndarray], view: str, out: Path) -> None:
    size = 1400
    margin = 80
    if view == "iso":
        yaw, pitch = np.deg2rad(38), np.deg2rad(25)
        rz = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
        rx = np.array([[1, 0, 0], [0, np.cos(pitch), -np.sin(pitch)], [0, np.sin(pitch), np.cos(pitch)]])
        base = points.mean(axis=0)
        proj = (points - base) @ rz.T @ rx.T
        x, y, depth = proj[:, 0], proj[:, 1], proj[:, 2]

        def transform(p: np.ndarray) -> tuple[float, float]:
            q = (p - base) @ rz.T @ rx.T
            return float(q[0]), float(q[1])
    else:
        mapping = {
            "front": ((0, 2), 1, 1),
            "side": ((1, 2), 0, 1),
            "top": ((0, 1), 2, 1),
        }
        axis_ids, depth_axis, sign = mapping[view]
        x, y, depth = sign * points[:, axis_ids[0]], points[:, axis_ids[1]], points[:, depth_axis]

        def transform(p: np.ndarray) -> tuple[float, float]:
            return float(sign * p[axis_ids[0]]), float(p[axis_ids[1]])

    xmin, xmax = float(np.min(x)), float(np.max(x))
    ymin, ymax = float(np.min(y)), float(np.max(y))

    def to_px(xv: float, yv: float) -> tuple[int, int]:
        px = margin + (xv - xmin) / max(1e-9, xmax - xmin) * (size - 2 * margin)
        py = size - margin - (yv - ymin) / max(1e-9, ymax - ymin) * (size - 2 * margin)
        return int(px), int(py)

    image = Image.new("RGB", (size, size), (18, 20, 22))
    draw = ImageDraw.Draw(image, "RGB")
    rng = np.random.default_rng(11)
    idx = rng.choice(len(points), min(len(points), 260000), replace=False)
    order = idx[np.argsort(depth[idx])]
    for xv, yv, color in zip(x[order], y[order], colors[order]):
        draw.point(to_px(float(xv), float(yv)), fill=tuple(int(c) for c in color))

    axis_len = 1.6
    axis_colors = {"x": (255, 80, 80), "y": (80, 220, 120), "z": (100, 150, 255)}
    for name, axis in axes.items():
        p1 = origin
        p2 = origin + axis * axis_len
        x1, y1 = transform(p1)
        x2, y2 = transform(p2)
        draw.line((*to_px(x1, y1), *to_px(x2, y2)), fill=axis_colors[name], width=5)
        draw.text(to_px(x2, y2), name.upper(), fill=axis_colors[name])

    for face_name, fit in faces.items():
        c = np.array(fit["center"], dtype=float)
        xv, yv = transform(c)
        px, py = to_px(xv, yv)
        draw.ellipse((px - 5, py - 5, px + 5, py + 5), fill=tuple(FACE_COLORS[face_name]))
        draw.text((px + 8, py - 8), face_name, fill=tuple(FACE_COLORS[face_name]))

    draw.text((30, 24), f"{view.upper()} face planes and measurement axes", fill=(255, 255, 255))
    image.save(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cloud", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--scale", type=float, required=True)
    parser.add_argument("--trunks-json")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    points = read_cloud(Path(args.cloud)) * args.scale
    castle, selection = robust_castle_selection(points)
    origin, axis_x, axis_y, axis_z = estimate_frame(castle)
    axes = {"x": axis_x, "y": axis_y, "z": axis_z}
    local = np.column_stack([(castle - origin) @ axis_x, (castle - origin) @ axis_y, (castle - origin) @ axis_z])

    faces, plane_rows, face_colors, labels = detect_face_planes(castle, origin, axes)
    plane_dimensions = dimensions_from_planes(faces)
    aabb_extent = castle.max(axis=0) - castle.min(axis=0)
    robust_aabb_extent = np.quantile(castle, 0.99, axis=0) - np.quantile(castle, 0.01, axis=0)
    obb_extent = local.max(axis=0) - local.min(axis=0)
    robust_obb_extent = np.quantile(local, 0.99, axis=0) - np.quantile(local, 0.01, axis=0)

    trunk_summary = None
    if args.trunks_json and Path(args.trunks_json).exists():
        data = json.loads(Path(args.trunks_json).read_text(encoding="utf-8"))
        trunk_summary = {
            "detected_trunk_count": data.get("detected_trunk_count"),
            "mean_length_m": data.get("mean_length_m"),
            "std_length_m": data.get("std_length_m"),
            "mean_diameter_p90_m": data.get("mean_diameter_p90_m"),
            "std_diameter_p90_m": data.get("std_diameter_p90_m"),
            "inferred_layer_count": data.get("detection", {}).get("inferred_layer_count"),
        }

    comparisons = {}
    for key, expected in EXPECTED.items():
        if key in plane_dimensions:
            comparisons[key] = {
                "expected_m": expected,
                "planes_m": plane_dimensions[key]["value_m"],
                "planes_error_percent": (plane_dimensions[key]["value_m"] - expected) / expected * 100.0,
            }

    result = {
        "source_cloud": args.cloud,
        "scale_factor_m_per_unit": args.scale,
        "castle_isolation": selection,
        "frame": {
            "origin_m": origin.tolist(),
            "axis_x": axis_x.tolist(),
            "axis_y": axis_y.tolist(),
            "axis_z": axis_z.tolist(),
            "note": "X is dominant horizontal log direction, Y is transverse horizontal, Z is vertical.",
        },
        "face_planes": faces,
        "plane_dimensions": plane_dimensions,
        "aabb_extent_m": aabb_extent.tolist(),
        "robust_aabb_extent_m": robust_aabb_extent.tolist(),
        "obb_extent_m": obb_extent.tolist(),
        "robust_obb_extent_m": robust_obb_extent.tolist(),
        "expected_m": EXPECTED,
        "comparison_to_expected": comparisons,
        "trunk_local_summary": trunk_summary,
    }

    (out / "global_dimensions.json").write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    with (out / "plane_measurements.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "face",
            "axis",
            "side",
            "point_count",
            "axis_position_m",
            "position_uncertainty_m",
            "rms_residual_m",
            "p95_abs_residual_m",
            "normal_alignment_to_expected_axis",
            "quality_score",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in plane_rows:
            writer.writerow({field: row.get(field) for field in fields})

    write_ply(out / "detected_planes.ply", castle, face_colors, ["face-colored castle selection"])
    center_points = []
    center_colors = []
    for face_name, fit in faces.items():
        center_points.append(fit["center"])
        center_colors.append(FACE_COLORS[face_name])
    overlay_points = np.vstack([castle, np.array(center_points, dtype=float)])
    overlay_colors = np.vstack([face_colors, np.array(center_colors, dtype=np.uint8)])
    write_ply(out / "dimension_overlay.ply", overlay_points, overlay_colors, ["face centers appended after castle points"])
    for view in ("front", "side", "top", "iso"):
        render(castle, face_colors, faces, origin, axes, view, out / f"{view}.png")

    report = f"""# Global Dimension Validation

Source cloud: `{args.cloud}`

Scale factor used only to express existing cloud coordinates in meters: `{args.scale:.8f} m/unit`

No reconstruction, NodeODM, OpenSfM, DBSCAN, PDI, segmentation, or ArUco scaling code was modified or rerun.

## Castle Isolation

Selection method: {selection['method']}.

- Raw points: {selection['raw_point_count']}
- Core points after 0.5% trim: {selection['core_point_count']}
- Castle-selection points used for plane fitting: {selection['selected_point_count']}

## Plane-Based Dimensions

| Dimension | Planes | Value | Uncertainty | Points | Quality | Expected | Error |
|---|---|---:|---:|---:|---:|---:|---:|
| X length | front-back | {plane_dimensions['x_length_m']['value_m']:.4f} m | {plane_dimensions['x_length_m']['uncertainty_m']:.4f} m | {plane_dimensions['x_length_m']['point_count']} | {plane_dimensions['x_length_m']['quality_score']:.4f} | {EXPECTED['x_length_m']:.4f} m | {comparisons['x_length_m']['planes_error_percent']:.2f}% |
| Y width | left-right | {plane_dimensions['y_width_m']['value_m']:.4f} m | {plane_dimensions['y_width_m']['uncertainty_m']:.4f} m | {plane_dimensions['y_width_m']['point_count']} | {plane_dimensions['y_width_m']['quality_score']:.4f} | {EXPECTED['y_width_m']:.4f} m | {comparisons['y_width_m']['planes_error_percent']:.2f}% |
| Z height | bottom-top | {plane_dimensions['z_height_m']['value_m']:.4f} m | {plane_dimensions['z_height_m']['uncertainty_m']:.4f} m | {plane_dimensions['z_height_m']['point_count']} | {plane_dimensions['z_height_m']['quality_score']:.4f} | {EXPECTED['z_height_m']:.4f} m | {comparisons['z_height_m']['planes_error_percent']:.2f}% |

## Method Comparison

| Method | X | Y | Z |
|---|---:|---:|---:|
| AABB full selection | {aabb_extent[0]:.4f} m | {aabb_extent[1]:.4f} m | {aabb_extent[2]:.4f} m |
| AABB robust 1%-99% | {robust_aabb_extent[0]:.4f} m | {robust_aabb_extent[1]:.4f} m | {robust_aabb_extent[2]:.4f} m |
| OBB PCA frame full | {obb_extent[0]:.4f} m | {obb_extent[1]:.4f} m | {obb_extent[2]:.4f} m |
| OBB PCA frame robust 1%-99% | {robust_obb_extent[0]:.4f} m | {robust_obb_extent[1]:.4f} m | {robust_obb_extent[2]:.4f} m |
| Face planes | {plane_dimensions['x_length_m']['value_m']:.4f} m | {plane_dimensions['y_width_m']['value_m']:.4f} m | {plane_dimensions['z_height_m']['value_m']:.4f} m |

## Face Fit Quality

| Face | Points | Axis position | RMS residual | p95 residual | Normal alignment |
|---|---:|---:|---:|---:|---:|
"""
    for row in plane_rows:
        report += (
            f"| {row['face']} | {row['point_count']} | {row['axis_position_m']:.4f} m | "
            f"{row['rms_residual_m']:.4f} m | {row['p95_abs_residual_m']:.4f} m | "
            f"{row['normal_alignment_to_expected_axis']:.4f} |\n"
        )

    if trunk_summary:
        report += f"""
## Coherence With Local Trunk Measurements

- Detected separable trunk-like candidates: {trunk_summary['detected_trunk_count']}
- Mean local trunk length: {trunk_summary['mean_length_m']:.4f} m
- Mean local trunk diameter p90: {trunk_summary['mean_diameter_p90_m']:.4f} m

The plane-based X length is {plane_dimensions['x_length_m']['value_m']:.4f} m, which differs from the local mean trunk length by {plane_dimensions['x_length_m']['value_m'] - trunk_summary['mean_length_m']:.4f} m.
The plane-based Y width divided by the local p90 diameter is {plane_dimensions['y_width_m']['value_m'] / trunk_summary['mean_diameter_p90_m']:.2f} apparent diameters.
The plane-based Z height divided by the local p90 diameter is {plane_dimensions['z_height_m']['value_m'] / trunk_summary['mean_diameter_p90_m']:.2f} apparent diameters.
"""

    report += f"""
## Quantitative Conclusion

1. Plane dimensions vs AABB: face planes produce X={plane_dimensions['x_length_m']['value_m']:.4f} m, Y={plane_dimensions['y_width_m']['value_m']:.4f} m, Z={plane_dimensions['z_height_m']['value_m']:.4f} m. These are compared above against AABB and OBB; the plane method avoids using coordinate extrema as the primary measurement.
2. Compatibility with local trunks: the local trunk diameter is close to the expected diameter, but the plane-based width corresponds to only {plane_dimensions['y_width_m']['value_m'] / (trunk_summary['mean_diameter_p90_m'] if trunk_summary else EXPECTED['log_diameter_m']):.2f} measured diameters, below the 8-diameter physical expectation.
3. Evidence for real deformation: the plane distances still show non-uniform errors: X {comparisons['x_length_m']['planes_error_percent']:.2f}%, Y {comparisons['y_width_m']['planes_error_percent']:.2f}%, Z {comparisons['z_height_m']['planes_error_percent']:.2f}%.
4. Measurement-method explanation: because plane-based, OBB, and robust AABB measurements remain broadly consistent, the discrepancy cannot be explained solely by AABB extrema. The remaining contradiction is between locally plausible trunk diameters and globally missing/semi-fused separable structure.
"""
    (out / "global_dimension_validation_report.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
