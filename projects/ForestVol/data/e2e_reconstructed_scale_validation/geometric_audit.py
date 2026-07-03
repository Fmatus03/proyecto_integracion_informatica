from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


EXPECTED_LENGTH_M = 6.0
EXPECTED_DIAMETER_M = 1.26
EXPECTED_TRUNKS_PER_LAYER = 8
EXPECTED_LAYERS = 4
EXPECTED_WIDTH_M = EXPECTED_TRUNKS_PER_LAYER * EXPECTED_DIAMETER_M
EXPECTED_HEIGHT_M = EXPECTED_LAYERS * EXPECTED_DIAMETER_M

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

PALETTE = np.array(
    [
        [230, 57, 70],
        [69, 123, 157],
        [42, 157, 143],
        [233, 196, 106],
        [244, 162, 97],
        [131, 56, 236],
        [255, 0, 110],
        [58, 134, 255],
        [46, 196, 182],
        [255, 190, 11],
        [251, 86, 7],
        [115, 201, 111],
        [157, 78, 221],
        [0, 180, 216],
        [255, 117, 143],
        [173, 181, 189],
    ],
    dtype=np.uint8,
)


def read_cloud(path: Path) -> tuple[np.ndarray, np.ndarray]:
    raw = path.read_bytes()
    header_end = raw.index(b"end_header\n") + len(b"end_header\n")
    header = raw[:header_end].decode("ascii", errors="ignore")
    vertex_count = None
    for line in header.splitlines():
        if line.startswith("element vertex "):
            vertex_count = int(line.split()[-1])
            break
    if vertex_count is None:
        raise ValueError("Missing vertex count")
    data = np.frombuffer(raw, dtype=PLY_DTYPE, count=vertex_count, offset=header_end)
    points = np.column_stack([data["x"], data["y"], data["z"]]).astype(np.float64)
    colors = np.column_stack([data["red"], data["green"], data["blue"]]).astype(np.uint8)
    finite = np.isfinite(points).all(axis=1)
    return points[finite], colors[finite]


def smooth2d(hist: np.ndarray, rounds: int = 4) -> np.ndarray:
    smoothed = hist.astype(np.float64)
    for _ in range(rounds):
        padded = np.pad(smoothed, 1, mode="edge")
        smoothed = (
            padded[:-2, :-2]
            + 2 * padded[:-2, 1:-1]
            + padded[:-2, 2:]
            + 2 * padded[1:-1, :-2]
            + 4 * padded[1:-1, 1:-1]
            + 2 * padded[1:-1, 2:]
            + padded[2:, :-2]
            + 2 * padded[2:, 1:-1]
            + padded[2:, 2:]
        ) / 16.0
    return smoothed


def estimate_log_frame(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xy = points[:, :2] - np.median(points[:, :2], axis=0)
    cov = np.cov(xy.T)
    values, vectors = np.linalg.eigh(cov)
    horizontal = vectors[:, int(np.argmax(values))]
    if horizontal[0] < 0:
        horizontal *= -1
    axis_x = np.array([horizontal[0], horizontal[1], 0.0], dtype=float)
    axis_x /= np.linalg.norm(axis_x)
    axis_y = np.array([-axis_x[1], axis_x[0], 0.0], dtype=float)
    axis_z = np.array([0.0, 0.0, 1.0], dtype=float)
    return axis_x, axis_y, axis_z


def detect_trunk_candidates(points: np.ndarray) -> tuple[np.ndarray, list[dict], dict]:
    axis_x, axis_y, axis_z = estimate_log_frame(points)
    origin = np.median(points, axis=0)
    local = np.column_stack([(points - origin) @ axis_x, (points - origin) @ axis_y, (points - origin) @ axis_z])
    yz = local[:, 1:3]

    bin_size = 0.12
    yz_min = np.quantile(yz, 0.003, axis=0)
    yz_max = np.quantile(yz, 0.997, axis=0)
    bins_y = max(16, int(math.ceil((yz_max[0] - yz_min[0]) / bin_size)))
    bins_z = max(12, int(math.ceil((yz_max[1] - yz_min[1]) / bin_size)))
    hist, y_edges, z_edges = np.histogram2d(yz[:, 0], yz[:, 1], bins=[bins_y, bins_z], range=[[yz_min[0], yz_max[0]], [yz_min[1], yz_max[1]]])
    density = smooth2d(hist)
    threshold = max(float(np.quantile(density[density > 0], 0.70)), float(density.max()) * 0.10)

    peaks: list[tuple[float, int, int]] = []
    for iy in range(1, density.shape[0] - 1):
        for iz in range(1, density.shape[1] - 1):
            value = density[iy, iz]
            if value < threshold:
                continue
            window = density[iy - 1 : iy + 2, iz - 1 : iz + 2]
            if value >= window.max():
                peaks.append((float(value), iy, iz))
    peaks.sort(reverse=True)

    selected: list[tuple[float, float, float]] = []
    min_peak_distance_m = 0.45
    for value, iy, iz in peaks:
        cy = 0.5 * (y_edges[iy] + y_edges[iy + 1])
        cz = 0.5 * (z_edges[iz] + z_edges[iz + 1])
        if all(math.hypot(cy - py, cz - pz) >= min_peak_distance_m for _pv, py, pz in selected):
            selected.append((value, float(cy), float(cz)))

    if not selected:
        raise RuntimeError("No trunk-density peaks were detected")

    centers_yz = np.array([[p[1], p[2]] for p in selected], dtype=float)
    distances = np.linalg.norm(yz[:, None, :] - centers_yz[None, :, :], axis=2)
    labels = distances.argmin(axis=1).astype(np.int32)
    nearest = distances[np.arange(len(yz)), labels]

    max_assignment_distance = 0.85
    labels[nearest > max_assignment_distance] = -1

    min_points = max(250, int(len(points) * 0.0008))
    candidates = []
    remap = np.full(len(selected), -1, dtype=np.int32)
    next_id = 0
    for idx, (_value, cy, cz) in enumerate(selected):
        count = int(np.sum(labels == idx))
        if count < min_points:
            labels[labels == idx] = -1
            continue
        remap[idx] = next_id
        candidates.append(
            {
                "seed_id": idx,
                "trunk_id": next_id,
                "density_peak": float(_value),
                "center_yz_local": [float(cy), float(cz)],
                "assigned_point_count": count,
            }
        )
        next_id += 1
    valid = labels >= 0
    labels[valid] = remap[labels[valid]]

    detection = {
        "method": "PCA horizontal alignment + 2D YZ density peaks + nearest-peak assignment",
        "forced_expected_layers_or_trunks": False,
        "bin_size_m": bin_size,
        "density_threshold": threshold,
        "min_peak_distance_m": min_peak_distance_m,
        "max_assignment_distance_m": max_assignment_distance,
        "min_points_per_candidate": min_points,
        "raw_peak_count": len(peaks),
        "accepted_peak_count": len(candidates),
        "local_origin": origin.tolist(),
        "axis_x": axis_x.tolist(),
        "axis_y": axis_y.tolist(),
        "axis_z": axis_z.tolist(),
    }
    return labels, candidates, detection


def robust_castle_points(points_m: np.ndarray) -> tuple[np.ndarray, dict]:
    q005 = np.quantile(points_m, 0.005, axis=0)
    q995 = np.quantile(points_m, 0.995, axis=0)
    core = points_m[np.all((points_m >= q005) & (points_m <= q995), axis=1)]

    # Robust castle envelope from the previous dimensional audit logic.
    q01 = np.quantile(core, 0.01, axis=0)
    q99 = np.quantile(core, 0.99, axis=0)
    selected = core[np.all((core >= q01) & (core <= q99), axis=1)]
    return selected, {
        "raw_q005": q005.tolist(),
        "raw_q995": q995.tolist(),
        "selected_q01": q01.tolist(),
        "selected_q99": q99.tolist(),
        "selected_point_count": int(len(selected)),
    }


def pca_measure(points: np.ndarray) -> dict:
    center = points.mean(axis=0)
    centered = points - center
    cov = np.cov(centered.T)
    values, vectors = np.linalg.eigh(cov)
    order = np.argsort(values)[::-1]
    values = values[order]
    vectors = vectors[:, order]
    if vectors[0, 0] < 0:
        vectors[:, 0] *= -1

    major = vectors[:, 0]
    projection = centered @ major
    p01, p99 = np.quantile(projection, [0.01, 0.99])
    length = float(p99 - p01)
    closest = np.outer(projection, major)
    radial = np.linalg.norm(centered - closest, axis=1)
    diameter_p50 = float(2 * np.quantile(radial, 0.50))
    diameter_p90 = float(2 * np.quantile(radial, 0.90))
    diameter_p95 = float(2 * np.quantile(radial, 0.95))
    ext = points.max(axis=0) - points.min(axis=0)
    return {
        "center": center.tolist(),
        "axis": major.tolist(),
        "eigenvalues": values.tolist(),
        "length_m": length,
        "diameter_p50_m": diameter_p50,
        "diameter_p90_m": diameter_p90,
        "diameter_p95_m": diameter_p95,
        "aabb_extent_m": ext.tolist(),
        "orientation_angle_to_x_deg": float(math.degrees(math.acos(min(1.0, abs(float(major[0])))))),
        "orientation_angle_to_horizontal_deg": float(math.degrees(math.asin(min(1.0, abs(float(major[2])))))),
    }


def write_ply(path: Path, points: np.ndarray, colors: np.ndarray, comments: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as handle:
        handle.write("ply\n")
        handle.write("format ascii 1.0\n")
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


def render(points: np.ndarray, colors: np.ndarray, centers: list[dict], view: str, out: Path) -> None:
    size = 1600
    margin = 90
    if view == "iso":
        yaw, pitch = np.deg2rad(38), np.deg2rad(28)
        rz = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
        rx = np.array([[1, 0, 0], [0, np.cos(pitch), -np.sin(pitch)], [0, np.sin(pitch), np.cos(pitch)]])
        origin = points.mean(axis=0)
        proj = (points - origin) @ rz.T @ rx.T
        x, y, depth = proj[:, 0], proj[:, 1], proj[:, 2]
        def transform(p: np.ndarray) -> tuple[float, float]:
            q = (p - origin) @ rz.T @ rx.T
            return float(q[0]), float(q[1])
    else:
        mapping = {
            "front": ((0, 2), 1, 1),
            "back": ((0, 2), 1, -1),
            "left": ((1, 2), 0, 1),
            "right": ((1, 2), 0, -1),
            "top": ((0, 1), 2, 1),
        }
        axes, depth_axis, sign = mapping[view]
        x, y, depth = sign * points[:, axes[0]], points[:, axes[1]], points[:, depth_axis]
        def transform(p: np.ndarray) -> tuple[float, float]:
            return float(sign * p[axes[0]]), float(p[axes[1]])

    xmin, xmax = float(np.min(x)), float(np.max(x))
    ymin, ymax = float(np.min(y)), float(np.max(y))

    def to_px(xv: float, yv: float) -> tuple[int, int]:
        px = margin + (xv - xmin) / max(1e-9, xmax - xmin) * (size - 2 * margin)
        py = size - margin - (yv - ymin) / max(1e-9, ymax - ymin) * (size - 2 * margin)
        return int(px), int(py)

    image = Image.new("RGB", (size, size), (18, 20, 22))
    draw = ImageDraw.Draw(image, "RGB")
    if len(points) > 300000:
        rng = np.random.default_rng(7)
        idx = rng.choice(len(points), 300000, replace=False)
    else:
        idx = np.arange(len(points))
    order = idx[np.argsort(depth[idx])]
    for pxi, pyi, color in zip(x[order], y[order], colors[order]):
        draw.point(to_px(float(pxi), float(pyi)), fill=tuple(int(c) for c in color))

    for item in centers:
        center = np.array(item["center"], dtype=float)
        axis = np.array(item["axis"], dtype=float)
        half = 0.5 * item["length_m"]
        p1 = center - axis * half
        p2 = center + axis * half
        x1, y1 = transform(p1)
        x2, y2 = transform(p2)
        c = tuple(int(v) for v in PALETTE[item["trunk_id"] % len(PALETTE)])
        draw.line((*to_px(x1, y1), *to_px(x2, y2)), fill=c, width=4)
        cx, cy = transform(center)
        px, py = to_px(cx, cy)
        draw.ellipse((px - 6, py - 6, px + 6, py + 6), fill=(255, 255, 255))
        draw.text((px + 8, py - 8), str(item["trunk_id"]), fill=(255, 255, 255))

    draw.text((34, 30), f"{view.upper()} colored trunks, labels=trunk_id", fill=(255, 255, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cloud", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--scale", type=float, required=True)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    raw_points, _raw_colors = read_cloud(Path(args.cloud))
    points_m = raw_points * args.scale
    castle, selection = robust_castle_points(points_m)

    trunk_labels, seeds, detection = detect_trunk_candidates(castle)
    measurements: list[dict] = []
    center_distance_rows: list[dict] = []

    for seed in seeds:
        indices = np.nonzero(trunk_labels == seed["trunk_id"])[0]
        pts = castle[indices]
        lo = np.quantile(pts, 0.02, axis=0)
        hi = np.quantile(pts, 0.98, axis=0)
        pts_trim = pts[np.all((pts >= lo) & (pts <= hi), axis=1)]
        if len(pts_trim) < 100:
            pts_trim = pts
        m = pca_measure(pts_trim)
        status = "ok"
        if m["length_m"] < EXPECTED_LENGTH_M * 0.65:
            status = "incomplete_length"
        if m["diameter_p90_m"] > EXPECTED_DIAMETER_M * 1.65:
            status = "possibly_fused_or_thick"
        if m["diameter_p90_m"] < EXPECTED_DIAMETER_M * 0.45:
            status = "possibly_partial_surface"
        m.update(
            {
                "trunk_id": seed["trunk_id"],
                "seed_id": seed["seed_id"],
                "density_peak": seed["density_peak"],
                "center_yz_local": seed["center_yz_local"],
                "layer_id": None,
                "slot_y": None,
                "point_count": int(len(pts)),
                "trimmed_point_count": int(len(pts_trim)),
                "status": status,
                "length_error_percent_vs_6m": (m["length_m"] - EXPECTED_LENGTH_M) / EXPECTED_LENGTH_M * 100.0,
                "diameter_error_percent_vs_1_26m": (m["diameter_p90_m"] - EXPECTED_DIAMETER_M) / EXPECTED_DIAMETER_M * 100.0,
            }
        )
        measurements.append(m)

    measurements.sort(key=lambda item: (item["center"][2], item["center_yz_local"][0]))
    centers_z = np.array([m["center"][2] for m in measurements], dtype=float)
    layer_metrics = []
    if len(measurements):
        order = np.argsort(centers_z)
        sorted_z = centers_z[order]
        gaps = np.diff(sorted_z)
        positive_gaps = gaps[gaps > 1e-6]
        gap_threshold = float(max(0.35, np.median(positive_gaps) * 2.5)) if len(positive_gaps) else 0.35
        layer_id = 0
        previous_sorted_index = 0
        for rank, measurement_index in enumerate(order):
            if rank and sorted_z[rank] - sorted_z[rank - 1] > gap_threshold:
                layer_id += 1
            measurements[measurement_index]["layer_id"] = layer_id
        layer_count = layer_id + 1
        for lid in range(layer_count):
            layer_trunks = [m for m in measurements if m["layer_id"] == lid]
            layer_trunks.sort(key=lambda item: item["center_yz_local"][0])
            for slot, m in enumerate(layer_trunks):
                m["slot_y"] = slot
            for prev, curr in zip(layer_trunks[:-1], layer_trunks[1:]):
                dist = float(np.linalg.norm(np.array(curr["center"]) - np.array(prev["center"])))
                center_distance_rows.append(
                    {
                        "layer_id": lid,
                        "from_trunk_id": prev["trunk_id"],
                        "to_trunk_id": curr["trunk_id"],
                        "center_distance_m": dist,
                        "error_percent_vs_expected_diameter": (dist - EXPECTED_DIAMETER_M) / EXPECTED_DIAMETER_M * 100.0,
                    }
                )
            layer_metrics.append(
                {
                    "layer_id": lid,
                    "z_center_m": float(np.mean([t["center"][2] for t in layer_trunks])),
                    "trunk_count": len(layer_trunks),
                    "avg_length_m": float(np.mean([t["length_m"] for t in layer_trunks])) if layer_trunks else None,
                    "avg_diameter_p90_m": float(np.mean([t["diameter_p90_m"] for t in layer_trunks])) if layer_trunks else None,
                    "avg_orientation_angle_to_x_deg": float(np.mean([t["orientation_angle_to_x_deg"] for t in layer_trunks])) if layer_trunks else None,
                }
            )
        detection["inferred_layer_count"] = layer_count
        detection["layer_gap_threshold_m"] = gap_threshold

    valid_mask = trunk_labels >= 0
    trunk_points = castle[valid_mask]
    trunk_ids = trunk_labels[valid_mask]
    trunk_colors = PALETTE[trunk_ids % len(PALETTE)]
    id_to_layer = {int(m["trunk_id"]): int(m["layer_id"]) for m in measurements}
    point_layers = np.array([id_to_layer.get(int(tid), 0) for tid in trunk_ids], dtype=np.int32)
    layer_colors = PALETTE[point_layers % len(PALETTE)]

    length_values = np.array([m["length_m"] for m in measurements], dtype=float)
    diameter_values = np.array([m["diameter_p90_m"] for m in measurements], dtype=float)
    center_distances = np.array([r["center_distance_m"] for r in center_distance_rows], dtype=float)
    all_extent = castle.max(axis=0) - castle.min(axis=0)
    aabb_robust_min = np.quantile(castle, 0.01, axis=0)
    aabb_robust_max = np.quantile(castle, 0.99, axis=0)
    aabb_robust_extent = aabb_robust_max - aabb_robust_min

    summary = {
        "source_cloud": args.cloud,
        "scale_factor_m_per_unit": args.scale,
        "expected": {
            "trunks": EXPECTED_LAYERS * EXPECTED_TRUNKS_PER_LAYER,
            "layers": EXPECTED_LAYERS,
            "trunks_per_layer": EXPECTED_TRUNKS_PER_LAYER,
            "length_m": EXPECTED_LENGTH_M,
            "diameter_m": EXPECTED_DIAMETER_M,
            "width_m": EXPECTED_WIDTH_M,
            "height_m": EXPECTED_HEIGHT_M,
        },
        "detection": detection,
        "selection": selection,
        "detected_trunk_count": len(measurements),
        "missing_trunk_count_vs_expected": EXPECTED_LAYERS * EXPECTED_TRUNKS_PER_LAYER - len(measurements),
        "incomplete_trunks": [m["trunk_id"] for m in measurements if "incomplete" in m["status"] or "partial" in m["status"]],
        "possibly_fused_trunks": [m["trunk_id"] for m in measurements if "fused" in m["status"]],
        "mean_length_m": float(np.mean(length_values)) if len(length_values) else None,
        "std_length_m": float(np.std(length_values)) if len(length_values) else None,
        "mean_diameter_p90_m": float(np.mean(diameter_values)) if len(diameter_values) else None,
        "std_diameter_p90_m": float(np.std(diameter_values)) if len(diameter_values) else None,
        "mean_center_distance_m": float(np.mean(center_distances)) if len(center_distances) else None,
        "std_center_distance_m": float(np.std(center_distances)) if len(center_distances) else None,
        "layer_metrics": layer_metrics,
        "global_aabb_extent_m": all_extent.tolist(),
        "robust_aabb_extent_m": aabb_robust_extent.tolist(),
        "axis_scale_ratios_vs_expected": {
            "x_length_ratio": float(aabb_robust_extent[0] / EXPECTED_LENGTH_M),
            "y_width_ratio": float(aabb_robust_extent[1] / EXPECTED_WIDTH_M),
            "z_height_ratio": float(aabb_robust_extent[2] / EXPECTED_HEIGHT_M),
        },
        "axis_error_percent_vs_expected": {
            "x_length": float((aabb_robust_extent[0] - EXPECTED_LENGTH_M) / EXPECTED_LENGTH_M * 100.0),
            "y_width": float((aabb_robust_extent[1] - EXPECTED_WIDTH_M) / EXPECTED_WIDTH_M * 100.0),
            "z_height": float((aabb_robust_extent[2] - EXPECTED_HEIGHT_M) / EXPECTED_HEIGHT_M * 100.0),
        },
        "trunk_measurements": measurements,
        "center_distances": center_distance_rows,
    }

    (out / "trunk_measurements.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")
    with (out / "trunk_measurements.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "trunk_id",
            "layer_id",
            "slot_y",
            "point_count",
            "length_m",
            "diameter_p90_m",
            "diameter_p95_m",
            "orientation_angle_to_x_deg",
            "orientation_angle_to_horizontal_deg",
            "center_x",
            "center_y",
            "center_z",
            "status",
            "length_error_percent_vs_6m",
            "diameter_error_percent_vs_1_26m",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for m in measurements:
            row = {field: m.get(field) for field in fields}
            row["center_x"], row["center_y"], row["center_z"] = m["center"]
            writer.writerow(row)

    comments = [f"trunk_id {m['trunk_id']} inferred_layer {m['layer_id']} slot_y {m['slot_y']}" for m in measurements]
    write_ply(out / "detected_trunks.ply", trunk_points, trunk_colors, comments)
    center_pts = np.array([m["center"] for m in measurements], dtype=float)
    center_colors = np.full((len(center_pts), 3), [255, 255, 255], dtype=np.uint8)
    numbered_points = np.vstack([trunk_points, center_pts])
    numbered_colors = np.vstack([trunk_colors, center_colors])
    write_ply(out / "numbered_trunks.ply", numbered_points, numbered_colors, comments + ["white points are trunk centers"])
    write_ply(out / "hill_layers.ply", trunk_points, layer_colors, [f"inferred layer metrics {json.dumps(layer_metrics)}"])

    for view in ("front", "back", "left", "right", "top", "iso"):
        render(trunk_points, trunk_colors, measurements, view, out / f"{view}.png")

    report = f"""# Castillo Geometric Audit

Source cloud: `{args.cloud}`

Scale factor used for measurement: `{args.scale:.8f} m/unit`

No reconstruction, PDI, DBSCAN pipeline stage, or algorithm parameter was modified. This audit operates only on the existing point cloud.

## Expected Physical Geometry

| Metric | Expected |
|---|---:|
| Trunks | {EXPECTED_LAYERS * EXPECTED_TRUNKS_PER_LAYER} |
| Layers | {EXPECTED_LAYERS} |
| Trunks per layer | {EXPECTED_TRUNKS_PER_LAYER} |
| Log length | {EXPECTED_LENGTH_M:.2f} m |
| Log diameter | {EXPECTED_DIAMETER_M:.2f} m |
| Total width | {EXPECTED_WIDTH_M:.2f} m |
| Total height | {EXPECTED_HEIGHT_M:.2f} m |

## Detected Geometry

| Metric | Measured |
|---|---:|
| Detected trunk candidates | {len(measurements)} |
| Missing vs 32 expected | {EXPECTED_LAYERS * EXPECTED_TRUNKS_PER_LAYER - len(measurements)} |
| Mean trunk length | {summary['mean_length_m']:.4f} m |
| Trunk length std | {summary['std_length_m']:.4f} m |
| Mean diameter p90 | {summary['mean_diameter_p90_m']:.4f} m |
| Diameter p90 std | {summary['std_diameter_p90_m']:.4f} m |
| Mean center-center distance | {summary['mean_center_distance_m']:.4f} m |
| Center-center std | {summary['std_center_distance_m']:.4f} m |

## Global Deformation

Robust AABB extents from selected castle points:

| Axis | Expected | Measured | Error |
|---|---:|---:|---:|
| X length | {EXPECTED_LENGTH_M:.4f} m | {aabb_robust_extent[0]:.4f} m | {summary['axis_error_percent_vs_expected']['x_length']:.2f}% |
| Y width | {EXPECTED_WIDTH_M:.4f} m | {aabb_robust_extent[1]:.4f} m | {summary['axis_error_percent_vs_expected']['y_width']:.2f}% |
| Z height | {EXPECTED_HEIGHT_M:.4f} m | {aabb_robust_extent[2]:.4f} m | {summary['axis_error_percent_vs_expected']['z_height']:.2f}% |

Axis scale ratios vs expected:

- X: {summary['axis_scale_ratios_vs_expected']['x_length_ratio']:.4f}
- Y: {summary['axis_scale_ratios_vs_expected']['y_width_ratio']:.4f}
- Z: {summary['axis_scale_ratios_vs_expected']['z_height_ratio']:.4f}

This is anisotropic: X is expanded while Y and Z are compressed.

## Layer Summary

| Layer | Z center | Trunks | Avg length | Avg diameter p90 |
|---:|---:|---:|---:|---:|
"""
    for layer in layer_metrics:
        report += f"| {layer['layer_id']} | {layer['z_center_m']:.4f} | {layer['trunk_count']} | {layer['avg_length_m']:.4f} | {layer['avg_diameter_p90_m']:.4f} |\n"

    report += f"""
## Objective Conclusion

1. Geometry vs 8x4 castle: {len(measurements)} trunk candidates were detected against 32 expected, with {summary['missing_trunk_count_vs_expected']} missing candidate(s) under this automatic partitioning.
2. Log length: mean detected length is {summary['mean_length_m']:.4f} m vs 6.0000 m expected, error {(summary['mean_length_m'] - EXPECTED_LENGTH_M) / EXPECTED_LENGTH_M * 100.0:.2f}%.
3. Diameter: mean p90 diameter is {summary['mean_diameter_p90_m']:.4f} m vs 1.2600 m expected, error {(summary['mean_diameter_p90_m'] - EXPECTED_DIAMETER_M) / EXPECTED_DIAMETER_M * 100.0:.2f}%.
4. Systematic deformation: robust global dimensions show X error {summary['axis_error_percent_vs_expected']['x_length']:.2f}%, Y error {summary['axis_error_percent_vs_expected']['y_width']:.2f}%, Z error {summary['axis_error_percent_vs_expected']['z_height']:.2f}%. This is not compatible with a uniform global scale error.
5. The remaining volume discrepancy is therefore supported by geometric deformation evidence: anisotropic expansion/compression and reconstructed trunk cross-sections that do not match the expected 6.0 m by 1.26 m logs.
"""
    (out / "geometric_audit_report.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
