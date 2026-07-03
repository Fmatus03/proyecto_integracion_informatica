from __future__ import annotations

import argparse
import csv
import json
import math
from collections import deque
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


def connected_voxel_component(points: np.ndarray, voxel_size: float = 0.18) -> tuple[np.ndarray, dict]:
    q_low = np.quantile(points, 0.005, axis=0)
    q_high = np.quantile(points, 0.995, axis=0)
    core_mask = np.all((points >= q_low) & (points <= q_high), axis=1)
    core = points[core_mask]
    origin = core.min(axis=0)
    vox = np.floor((core - origin) / voxel_size).astype(np.int32)
    uniq, inverse, counts = np.unique(vox, axis=0, return_inverse=True, return_counts=True)
    dense_mask = counts >= 4
    dense_ids = np.nonzero(dense_mask)[0]
    dense_set = {tuple(v) for v in uniq[dense_ids]}

    visited: set[tuple[int, int, int]] = set()
    components: list[list[tuple[int, int, int]]] = []
    neighbors = [
        (dx, dy, dz)
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        for dz in (-1, 0, 1)
        if not (dx == 0 and dy == 0 and dz == 0)
    ]
    for voxel in dense_set:
        if voxel in visited:
            continue
        queue: deque[tuple[int, int, int]] = deque([voxel])
        visited.add(voxel)
        component: list[tuple[int, int, int]] = []
        while queue:
            current = queue.popleft()
            component.append(current)
            for delta in neighbors:
                nxt = (current[0] + delta[0], current[1] + delta[1], current[2] + delta[2])
                if nxt in dense_set and nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)
        components.append(component)

    comp_rows = []
    for comp in components:
        comp_arr = np.array(comp, dtype=np.int32)
        comp_ids = {tuple(v) for v in comp}
        voxel_indices = np.array([i for i, v in enumerate(uniq) if tuple(v) in comp_ids], dtype=np.int32)
        point_count = int(counts[voxel_indices].sum())
        mins = origin + comp_arr.min(axis=0) * voxel_size
        maxs = origin + (comp_arr.max(axis=0) + 1) * voxel_size
        extent = maxs - mins
        comp_rows.append(
            {
                "voxel_count": len(comp),
                "point_count": point_count,
                "min": mins.tolist(),
                "max": maxs.tolist(),
                "extent": extent.tolist(),
            }
        )
    comp_rows.sort(key=lambda row: row["point_count"], reverse=True)
    selected = comp_rows[0]
    selected_voxels = {
        tuple(v)
        for v in uniq[
            np.array(
                [
                    i
                    for i, v in enumerate(uniq)
                    if all(selected["min"][axis] <= origin[axis] + v[axis] * voxel_size <= selected["max"][axis] for axis in range(3))
                    and tuple(v) in dense_set
                ],
                dtype=np.int32,
            )
        ]
    }
    selected_core_mask = np.array([tuple(v) in selected_voxels for v in vox], dtype=bool)
    selected_points_core = core[selected_core_mask]

    # Pull nearby original points around the selected dense component.
    mins = np.array(selected["min"]) - voxel_size
    maxs = np.array(selected["max"]) + voxel_size
    selected_mask = np.all((points >= mins) & (points <= maxs), axis=1)
    selected_points = points[selected_mask]
    return selected_points, {
        "voxel_size_m": voxel_size,
        "core_quantiles": {"low": q_low.tolist(), "high": q_high.tolist()},
        "component_count": len(comp_rows),
        "components_top5": comp_rows[:5],
        "selected_dense_core_points": int(len(selected_points_core)),
        "selected_points": int(len(selected_points)),
    }


def robust_bounds(points: np.ndarray, low: float = 0.01, high: float = 0.99) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mn = np.quantile(points, low, axis=0)
    mx = np.quantile(points, high, axis=0)
    mask = np.all((points >= mn) & (points <= mx), axis=1)
    trimmed = points[mask]
    return trimmed.min(axis=0), trimmed.max(axis=0), trimmed


def obb_xy(points: np.ndarray) -> dict:
    xy = points[:, :2]
    center = xy.mean(axis=0)
    cov = np.cov((xy - center).T)
    vals, vecs = np.linalg.eigh(cov)
    order = np.argsort(vals)[::-1]
    axes = vecs[:, order]
    if np.linalg.det(axes) < 0:
        axes[:, 1] *= -1
    proj = (xy - center) @ axes
    mn = proj.min(axis=0)
    mx = proj.max(axis=0)
    extent_xy = mx - mn
    zmin = float(points[:, 2].min())
    zmax = float(points[:, 2].max())
    return {
        "center_xy": center.tolist(),
        "axes_xy": axes.tolist(),
        "min_local_xy": mn.tolist(),
        "max_local_xy": mx.tolist(),
        "extent_m": [float(extent_xy[0]), float(extent_xy[1]), zmax - zmin],
        "z_min": zmin,
        "z_max": zmax,
    }


def vertical_profile(points: np.ndarray, bin_size: float = 0.25) -> dict:
    z = points[:, 2]
    zmin, zmax = float(z.min()), float(z.max())
    bins = np.arange(math.floor(zmin / bin_size) * bin_size, zmax + bin_size, bin_size)
    counts, edges = np.histogram(z, bins=bins)
    top_max = zmax
    top_start = top_max - 0.75
    below_start = top_start - 0.75
    top_count = int(np.count_nonzero(z >= top_start))
    below_count = int(np.count_nonzero((z >= below_start) & (z < top_start)))
    high95 = float(np.quantile(z, 0.95))
    high99 = float(np.quantile(z, 0.99))
    return {
        "z_min": zmin,
        "z_max": zmax,
        "z_extent": zmax - zmin,
        "z_p95": high95,
        "z_p99": high99,
        "bin_size_m": bin_size,
        "bins": [
            {"z0": float(edges[i]), "z1": float(edges[i + 1]), "count": int(counts[i])}
            for i in range(len(counts))
        ],
        "top_0_75m_point_count": top_count,
        "previous_0_75m_point_count": below_count,
        "top_to_previous_ratio": float(top_count / below_count) if below_count else None,
    }


def draw_view(points: np.ndarray, aabb_min: np.ndarray, aabb_max: np.ndarray, obb: dict, view: str, out: Path) -> None:
    size = 1600
    margin = 90
    if view == "iso":
        yaw, pitch = np.deg2rad(38), np.deg2rad(28)
        rz = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
        rx = np.array([[1, 0, 0], [0, np.cos(pitch), -np.sin(pitch)], [0, np.sin(pitch), np.cos(pitch)]])
        centered = points - points.mean(axis=0)
        proj3 = centered @ rz.T @ rx.T
        x, y, depth = proj3[:, 0], proj3[:, 1], proj3[:, 2]
        transform_points = lambda p: (p - points.mean(axis=0)) @ rz.T @ rx.T
    else:
        mapping = {
            "front": ((0, 2), 1),
            "back": ((0, 2), 1),
            "left": ((1, 2), 0),
            "right": ((1, 2), 0),
            "top": ((0, 1), 2),
        }
        axes, depth_axis = mapping[view]
        sign = -1 if view in {"back", "right"} else 1
        x, y, depth = sign * points[:, axes[0]], points[:, axes[1]], points[:, depth_axis]
        transform_points = None

    xmin, xmax = float(x.min()), float(x.max())
    ymin, ymax = float(y.min()), float(y.max())
    def norm_xy(xv: np.ndarray, yv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        px = margin + (xv - xmin) / max(1e-9, xmax - xmin) * (size - 2 * margin)
        py = size - margin - (yv - ymin) / max(1e-9, ymax - ymin) * (size - 2 * margin)
        return px, py

    px, py = norm_xy(x, y)
    order = np.argsort(depth)
    image = Image.new("RGB", (size, size), (18, 20, 22))
    draw = ImageDraw.Draw(image, "RGB")
    for xi, yi in zip(px[order][::2], py[order][::2]):
        draw.point((int(xi), int(yi)), fill=(185, 190, 185))

    corners = np.array(
        [
            [aabb_min[0], aabb_min[1], aabb_min[2]],
            [aabb_max[0], aabb_min[1], aabb_min[2]],
            [aabb_max[0], aabb_max[1], aabb_min[2]],
            [aabb_min[0], aabb_max[1], aabb_min[2]],
            [aabb_min[0], aabb_min[1], aabb_max[2]],
            [aabb_max[0], aabb_min[1], aabb_max[2]],
            [aabb_max[0], aabb_max[1], aabb_max[2]],
            [aabb_min[0], aabb_max[1], aabb_max[2]],
        ]
    )
    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
    if view == "iso":
        pc = transform_points(corners)
        bx, by = norm_xy(pc[:, 0], pc[:, 1])
    else:
        axes = {"front": (0, 2), "back": (0, 2), "left": (1, 2), "right": (1, 2), "top": (0, 1)}[view]
        sign = -1 if view in {"back", "right"} else 1
        bx, by = norm_xy(sign * corners[:, axes[0]], corners[:, axes[1]])
    for a, b in edges:
        draw.line((float(bx[a]), float(by[a]), float(bx[b]), float(by[b])), fill=(255, 60, 60), width=4)
    extent = aabb_max - aabb_min
    draw.text((36, 32), f"{view.upper()}  L={extent[0]:.2f}m  W={extent[1]:.2f}m  H={extent[2]:.2f}m", fill=(255, 255, 255))
    draw.text((36, 62), "AABB red; dimensions from robust selected castle component", fill=(235, 235, 235))
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cloud", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--scale", type=float, required=True)
    args = parser.parse_args()

    out = Path(args.out)
    points_raw, colors = read_cloud(Path(args.cloud))
    points_m = points_raw * args.scale
    selected, segmentation = connected_voxel_component(points_m)
    aabb_min, aabb_max, trimmed = robust_bounds(selected)
    aabb_extent = aabb_max - aabb_min
    obb = obb_xy(trimmed)
    profile = vertical_profile(trimmed)

    # Conservative height excluding sparse upper extension: p99 top instead of absolute max.
    height_excluding_sparse_top = profile["z_p99"] - profile["z_min"]
    top_extension_m = profile["z_max"] - profile["z_p99"]
    has_sparse_extension = bool(
        top_extension_m > 0.30
        and profile["top_to_previous_ratio"] is not None
        and profile["top_to_previous_ratio"] < 0.35
    )

    dims = {
        "session_id": args.session,
        "source_point_cloud": args.cloud,
        "scale_factor_m_per_unit": args.scale,
        "raw_point_count": int(len(points_raw)),
        "selected_castle_point_count": int(len(selected)),
        "trimmed_castle_point_count": int(len(trimmed)),
        "reported_dimensions_source": "AABB of dense main castle component, trimmed at 1%-99% per axis",
        "aabb": {
            "min": aabb_min.tolist(),
            "max": aabb_max.tolist(),
            "extent_m": aabb_extent.tolist(),
            "length_x_m": float(aabb_extent[0]),
            "width_y_m": float(aabb_extent[1]),
            "height_z_m": float(aabb_extent[2]),
        },
        "obb": obb,
        "vertical_profile": profile,
        "height_including_upper_extension_m": float(aabb_extent[2]),
        "height_excluding_sparse_upper_extension_m": float(height_excluding_sparse_top),
        "top_extension_above_p99_m": float(top_extension_m),
        "upper_extension_classification": (
            "sparse_partial_upper_extension_or_noise" if has_sparse_extension else "no_sparse_upper_extension_detected"
        ),
        "segmentation": segmentation,
        "interpretation": {
            "use_aabb_for_reported_dimensions": True,
            "reason": "The metric X/Y/Z axes are the requested reporting axes; OBB is included to show orientation effects but would mix requested axes.",
        },
    }

    write_json = lambda name, payload: (out / name).write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    out.mkdir(parents=True, exist_ok=True)
    write_json("dimensions.json", dims)
    write_json(
        "bbox_measurements.json",
        {
            "aabb": dims["aabb"],
            "obb": dims["obb"],
            "vertical_profile_summary": {
                key: profile[key]
                for key in ("z_min", "z_max", "z_extent", "z_p95", "z_p99", "top_0_75m_point_count", "previous_0_75m_point_count", "top_to_previous_ratio")
            },
        },
    )

    with (out / "measured_dimensions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["measurement", "value_m", "method"])
        writer.writeheader()
        writer.writerow({"measurement": "length_x", "value_m": f"{aabb_extent[0]:.6f}", "method": "AABB trimmed dense component"})
        writer.writerow({"measurement": "width_y", "value_m": f"{aabb_extent[1]:.6f}", "method": "AABB trimmed dense component"})
        writer.writerow({"measurement": "height_z_including_extension", "value_m": f"{aabb_extent[2]:.6f}", "method": "AABB trimmed dense component"})
        writer.writerow({"measurement": "height_z_excluding_sparse_extension", "value_m": f"{height_excluding_sparse_top:.6f}", "method": "z p99 minus z min"})
        writer.writerow({"measurement": "obb_length_major", "value_m": f"{obb['extent_m'][0]:.6f}", "method": "PCA OBB XY + Z extent"})
        writer.writerow({"measurement": "obb_width_minor", "value_m": f"{obb['extent_m'][1]:.6f}", "method": "PCA OBB XY + Z extent"})
        writer.writerow({"measurement": "obb_height_z", "value_m": f"{obb['extent_m'][2]:.6f}", "method": "PCA OBB XY + Z extent"})

    for view in ("front", "back", "left", "right", "top", "iso"):
        draw_view(trimmed, aabb_min, aabb_max, obb, view, out / "views" / f"{view}.png")

    report = f"""# Castillo Dimension Validation

Session: `{args.session}`

Source cloud: `{args.cloud}`

Scale factor applied for measurement: `{args.scale:.8f} m/unit`

## Reported Dimensions

Dimensions are reported from the AABB of the automatically selected dense main castle component, trimmed at 1%-99% per axis.

| Measurement | Value |
|---|---:|
| Length X | {aabb_extent[0]:.4f} m |
| Width Y | {aabb_extent[1]:.4f} m |
| Height Z including upper extension | {aabb_extent[2]:.4f} m |
| Height Z excluding sparse upper extension | {height_excluding_sparse_top:.4f} m |

## Bounding Boxes

| Box | X/major | Y/minor | Z |
|---|---:|---:|---:|
| AABB | {aabb_extent[0]:.4f} m | {aabb_extent[1]:.4f} m | {aabb_extent[2]:.4f} m |
| OBB | {obb['extent_m'][0]:.4f} m | {obb['extent_m'][1]:.4f} m | {obb['extent_m'][2]:.4f} m |

AABB is used for final reporting because the requested dimensions are explicitly X, Y and Z extents. OBB is included as an orientation check.

## Vertical Evidence

| Metric | Value |
|---|---:|
| Z min | {profile['z_min']:.4f} m |
| Z max | {profile['z_max']:.4f} m |
| Z p95 | {profile['z_p95']:.4f} m |
| Z p99 | {profile['z_p99']:.4f} m |
| Top 0.75m points | {profile['top_0_75m_point_count']} |
| Previous 0.75m points | {profile['previous_0_75m_point_count']} |
| Top/previous ratio | {profile['top_to_previous_ratio']:.6f} |

Upper extension classification: `{dims['upper_extension_classification']}`.

## Conclusion

1. Final dimensions: X={aabb_extent[0]:.4f} m, Y={aabb_extent[1]:.4f} m, Z={aabb_extent[2]:.4f} m including upper extension.
2. This report does not have an external measured ground-truth dimension table; it can only compare internal AABB/OBB consistency.
3. Fifth level / upper extension: `{dims['upper_extension_classification']}` based on top-vs-previous vertical point distribution.
4. Since the model dimensions remain large while the ArUco scale was applied, the remaining volume error is more consistent with geometry/segmentation/PDI support than with a missing global scale application. Exact ground-truth dimensions are required to conclude whether the ArUco factor itself is numerically correct.
"""
    (out / "dimension_report.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
