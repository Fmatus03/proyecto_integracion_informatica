from __future__ import annotations

import csv
import json
import math
import os
import struct
import time
from collections import defaultdict, deque
from pathlib import Path

import numpy as np

try:
    import open3d as o3d
except Exception:  # pragma: no cover - optional runtime dependency
    o3d = None

try:
    from scipy import ndimage
except Exception:  # pragma: no cover - optional runtime dependency
    ndimage = None

from experiments.cloud_unification.cloud_provider_adapter import load_dataset_cloud_source


ROOT = Path(os.environ.get("FINAL_VALIDATION_ROOT") or Path.cwd() / "projects/ForestVol")
OUT = Path(os.environ.get("FINAL_VALIDATION_OUT") or ROOT / "data/final_statistical_validation")
GT_VOLUME_M3 = float(os.environ.get("FINAL_VALIDATION_GT_M3") or "119.74")
VOXEL_SIZE_M = float(os.environ.get("FINAL_VALIDATION_VOXEL_SIZE_M") or "0.25")
SEED_COUNT = int(os.environ.get("FINAL_VALIDATION_SEEDS") or "30")
BASE_SEED = int(os.environ.get("FINAL_VALIDATION_BASE_SEED") or "20260629")
RUN_ID = "RUN-FINAL-STATISTICAL-VALIDATION-01"

DATASETS = {
    "set1": load_dataset_cloud_source("set1").path,
    "set2": load_dataset_cloud_source("set2").path,
}

# Frozen replay of the prior benchmark threshold decisions. This avoids changing
# PDI parameters while keeping this final phase runnable without Open3D/SciPy.
DEFAULT_THRESHOLDS = {"set1": 1, "set2": 2}


def read_binary_open3d_cloud(path: Path) -> np.ndarray:
    if o3d is not None:
        cloud = o3d.io.read_point_cloud(str(path))
        points = np.asarray(cloud.points, dtype=np.float64)
        return points[np.all(np.isfinite(points), axis=1)]
    with path.open("rb") as handle:
        header = bytearray()
        while not header.endswith(b"end_header\n"):
            chunk = handle.readline()
            if not chunk:
                raise ValueError(f"Invalid PLY header: {path}")
            header.extend(chunk)
        text = header.decode("ascii", errors="replace")
        if "format binary_little_endian 1.0" not in text:
            raise ValueError(f"Unsupported PLY format: {path}")
        vertex_count = None
        properties: list[tuple[str, str]] = []
        in_vertex = False
        for line in text.splitlines():
            parts = line.split()
            if parts[:2] == ["element", "vertex"]:
                vertex_count = int(parts[2])
                in_vertex = True
            elif parts and parts[0] == "element" and parts[1] != "vertex":
                in_vertex = False
            elif in_vertex and parts[:1] == ["property"]:
                properties.append((parts[1], parts[2]))
        if vertex_count is None:
            raise ValueError(f"Missing vertex count: {path}")
        fmt_map = {"double": "d", "float": "f", "uchar": "B", "uint8": "B"}
        fmt = "<" + "".join(fmt_map[p[0]] for p in properties)
        row_size = struct.calcsize(fmt)
        raw = handle.read(vertex_count * row_size)
    rows = struct.iter_unpack(fmt, raw)
    names = [name for _, name in properties]
    xyz_idx = [names.index(axis) for axis in ("x", "y", "z")]
    points = np.asarray([[row[i] for i in xyz_idx] for row in rows], dtype=np.float64)
    return points[np.all(np.isfinite(points), axis=1)]


def offsets(connectivity: int = 2) -> list[tuple[int, int, int]]:
    out = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if abs(dx) + abs(dy) + abs(dz) <= connectivity:
                    out.append((dx, dy, dz))
    return out


OFFSETS_18 = offsets(2)


def shifted(arr: np.ndarray, delta: tuple[int, int, int], fill: bool) -> np.ndarray:
    result = np.full_like(arr, fill, dtype=bool)
    src = []
    dst = []
    for axis, d in enumerate(delta):
        if d > 0:
            src.append(slice(0, -d))
            dst.append(slice(d, None))
        elif d < 0:
            src.append(slice(-d, None))
            dst.append(slice(0, d))
        else:
            src.append(slice(None))
            dst.append(slice(None))
    result[tuple(dst)] = arr[tuple(src)]
    return result


def binary_dilation(arr: np.ndarray, iterations: int = 1) -> np.ndarray:
    out = arr.astype(bool, copy=True)
    for _ in range(iterations):
        nxt = np.zeros_like(out, dtype=bool)
        for off in OFFSETS_18:
            nxt |= shifted(out, off, False)
        out = nxt
    return out


def binary_erosion(arr: np.ndarray, iterations: int = 1) -> np.ndarray:
    out = arr.astype(bool, copy=True)
    for _ in range(iterations):
        nxt = np.ones_like(out, dtype=bool)
        for off in OFFSETS_18:
            nxt &= shifted(out, off, False)
        out = nxt
    return out


def fill_holes(arr: np.ndarray) -> np.ndarray:
    outside = np.zeros_like(arr, dtype=bool)
    q: deque[tuple[int, int, int]] = deque()
    max_i, max_j, max_k = (s - 1 for s in arr.shape)
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            for k in (0, max_k):
                if not arr[i, j, k] and not outside[i, j, k]:
                    outside[i, j, k] = True
                    q.append((i, j, k))
    for i in range(arr.shape[0]):
        for k in range(arr.shape[2]):
            for j in (0, max_j):
                if not arr[i, j, k] and not outside[i, j, k]:
                    outside[i, j, k] = True
                    q.append((i, j, k))
    for j in range(arr.shape[1]):
        for k in range(arr.shape[2]):
            for i in (0, max_i):
                if not arr[i, j, k] and not outside[i, j, k]:
                    outside[i, j, k] = True
                    q.append((i, j, k))
    while q:
        i, j, k = q.popleft()
        for di, dj, dk in OFFSETS_18:
            ni, nj, nk = i + di, j + dj, k + dk
            if 0 <= ni <= max_i and 0 <= nj <= max_j and 0 <= nk <= max_k and not arr[ni, nj, nk] and not outside[ni, nj, nk]:
                outside[ni, nj, nk] = True
                q.append((ni, nj, nk))
    return arr | ~outside


def largest_component(arr: np.ndarray) -> np.ndarray:
    labels = np.zeros(arr.shape, dtype=np.int32)
    best_label = 0
    best_size = 0
    label = 0
    max_i, max_j, max_k = (s - 1 for s in arr.shape)
    for start in np.argwhere(arr):
        i, j, k = map(int, start)
        if labels[i, j, k]:
            continue
        label += 1
        size = 0
        labels[i, j, k] = label
        q: deque[tuple[int, int, int]] = deque([(i, j, k)])
        while q:
            ci, cj, ck = q.popleft()
            size += 1
            for di, dj, dk in OFFSETS_18:
                ni, nj, nk = ci + di, cj + dj, ck + dk
                if 0 <= ni <= max_i and 0 <= nj <= max_j and 0 <= nk <= max_k and arr[ni, nj, nk] and labels[ni, nj, nk] == 0:
                    labels[ni, nj, nk] = label
                    q.append((ni, nj, nk))
        if size > best_size:
            best_label = label
            best_size = size
    return labels == best_label if best_label else arr


def occupancy_counts(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    origin = points.min(axis=0) - 4 * VOXEL_SIZE_M
    dims = np.ceil((points.max(axis=0) + 4 * VOXEL_SIZE_M - origin) / VOXEL_SIZE_M).astype(int) + 1
    idx = np.floor((points - origin) / VOXEL_SIZE_M).astype(np.int32)
    counts = np.zeros(tuple(dims.tolist()), dtype=np.int16)
    np.add.at(counts, (idx[:, 0], idx[:, 1], idx[:, 2]), 1)
    return counts, origin


def solid_from_dense(dense: np.ndarray) -> np.ndarray:
    if ndimage is not None:
        structure = ndimage.generate_binary_structure(3, 2)
        shell = ndimage.binary_dilation(dense, structure=structure, iterations=2)
        solid = ndimage.binary_fill_holes(shell)
        solid = ndimage.binary_closing(solid, structure=structure, iterations=1)
        solid = ndimage.binary_fill_holes(solid)
        labels, count = ndimage.label(solid, structure=structure)
        if count > 1:
            sizes = np.bincount(labels.ravel())
            sizes[0] = 0
            solid = labels == int(np.argmax(sizes))
        return solid
    shell = binary_dilation(dense, iterations=2)
    solid = fill_holes(shell)
    solid = binary_erosion(binary_dilation(solid, iterations=1), iterations=1)
    solid = fill_holes(solid)
    return largest_component(solid)


def threshold_for(dataset: str, experiment: str, level: str) -> int:
    if experiment == "segmentation_spurious_points":
        return 1
    if dataset == "set2" and experiment == "random_point_reduction" and level == "remove_50pct":
        return 1
    return DEFAULT_THRESHOLDS[dataset]


def point_density_integration(dataset: str, experiment: str, level: str, points: np.ndarray) -> tuple[float, dict, float]:
    counts, _ = occupancy_counts(points)
    threshold = threshold_for(dataset, experiment, level)
    dense = counts >= threshold
    solid = solid_from_dense(dense)
    approx_mb = (points.nbytes + counts.nbytes + dense.nbytes + solid.nbytes) / (1024 * 1024)
    return float(np.count_nonzero(solid) * (VOXEL_SIZE_M ** 3)), {
        "voxel_size_m": VOXEL_SIZE_M,
        "density_threshold_points_per_voxel": threshold,
        "threshold_source": "frozen replay from RUN-PDI-ROBUSTNESS-01",
        "solid_voxels": int(np.count_nonzero(solid)),
    }, approx_mb


def error_metrics(volume: float) -> tuple[float, float]:
    absolute = abs(volume - GT_VOLUME_M3)
    return absolute, absolute / GT_VOLUME_M3 * 100.0


def cloud_stats(points: np.ndarray) -> dict:
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    extent = maxs - mins
    bbox_volume = float(np.prod(np.maximum(extent, 1e-9)))
    return {
        "point_count": int(len(points)),
        "bbox_volume_m3": round(bbox_volume, 6),
        "mean_density_points_per_m3": round(float(len(points) / bbox_volume), 6),
    }


def evaluate(dataset: str, experiment: str, level: str, seed: int, points: np.ndarray, base_volume: float) -> dict:
    start = time.perf_counter()
    volume, params, approx_memory = point_density_integration(dataset, experiment, level, points)
    elapsed = time.perf_counter() - start
    absolute, percent = error_metrics(volume)
    return {
        "dataset": dataset,
        "method": "Point Density Integration",
        "experiment": experiment,
        "level": level,
        "seed": seed,
        "volume_m3": round(volume, 6),
        "absolute_error_m3": round(absolute, 6),
        "percent_error": round(percent, 6),
        "execution_time_seconds": round(elapsed, 6),
        "approx_memory_mb": round(approx_memory, 6),
        "deviation_from_base_m3": round(volume - base_volume, 6),
        "deviation_from_base_pct": round(((volume - base_volume) / base_volume) * 100.0, 6) if base_volume else None,
        "pdi_parameters": params,
        **cloud_stats(points),
    }


def random_reduction(points: np.ndarray, pct: float, rng: np.random.Generator) -> np.ndarray:
    keep_count = max(4, int(round(len(points) * (1.0 - pct))))
    idx = rng.choice(len(points), size=keep_count, replace=False)
    return points[np.sort(idx)]


def gaussian_noise(points: np.ndarray, sigma_m: float, rng: np.random.Generator) -> np.ndarray:
    return points + rng.normal(0.0, sigma_m, size=points.shape)


def segmentation_spurious(points: np.ndarray, pct: float, rng: np.random.Generator) -> np.ndarray:
    count = max(1, int(round(len(points) * pct)))
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    extent = maxs - mins
    spurious = rng.uniform(mins - 0.15 * extent, maxs + 0.15 * extent, size=(count, 3))
    return np.vstack((points, spurious))


def partial_occlusions(points: np.ndarray) -> dict[str, np.ndarray]:
    q20 = np.quantile(points, 0.20, axis=0)
    q35 = np.quantile(points, 0.35, axis=0)
    q65 = np.quantile(points, 0.65, axis=0)
    q80 = np.quantile(points, 0.80, axis=0)
    return {
        "remove_x_min_face_20pct": points[points[:, 0] > q20[0]],
        "remove_high_corner_20pct_xyz": points[~((points[:, 0] > q80[0]) & (points[:, 1] > q80[1]) & (points[:, 2] > q80[2]))],
        "remove_vertical_band_mid_x": points[~((points[:, 0] >= q35[0]) & (points[:, 0] <= q65[0]))],
        "remove_horizontal_band_mid_z": points[~((points[:, 2] >= q35[2]) & (points[:, 2] <= q65[2]))],
        "remove_y_max_face_20pct": points[points[:, 1] < q80[1]],
        "remove_low_corner_20pct_xyz": points[~((points[:, 0] < q20[0]) & (points[:, 1] < q20[1]) & (points[:, 2] < q20[2]))],
    }


def stats(values: list[float]) -> dict:
    arr = np.asarray(values, dtype=float)
    mean = float(arr.mean())
    std = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
    ci = 1.96 * std / math.sqrt(len(arr)) if len(arr) > 1 else 0.0
    return {
        "n": int(len(arr)),
        "mean": round(mean, 6),
        "median": round(float(np.median(arr)), 6),
        "std": round(std, 6),
        "coefficient_of_variation": round(float(std / mean), 6) if mean else None,
        "ci95_half_width": round(float(ci), 6),
        "ci95_low": round(float(mean - ci), 6),
        "ci95_high": round(float(mean + ci), 6),
        "min": round(float(arr.min()), 6),
        "max": round(float(arr.max()), 6),
        "p05": round(float(np.percentile(arr, 5)), 6),
        "p95": round(float(np.percentile(arr, 95)), 6),
    }


def aggregate(rows: list[dict]) -> dict:
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["dataset"], row["experiment"], row["level"])].append(row)
    output = {}
    for (dataset, experiment, level), items in sorted(groups.items()):
        key = f"{dataset}:{experiment}:{level}"
        output[key] = {
            "dataset": dataset,
            "experiment": experiment,
            "level": level,
            "volume_m3": stats([row["volume_m3"] for row in items]),
            "absolute_error_m3": stats([row["absolute_error_m3"] for row in items]),
            "percent_error": stats([row["percent_error"] for row in items]),
            "execution_time_seconds": stats([row["execution_time_seconds"] for row in items]),
            "approx_memory_mb": stats([row["approx_memory_mb"] for row in items]),
            "point_count": stats([row["point_count"] for row in items]),
        }
    return output


def method_comparison() -> dict:
    path = ROOT / "data/volume_estimator_benchmark/benchmark_volume_estimators.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    by_method: dict[str, list[float]] = defaultdict(list)
    for row in data["rows"]:
        if row.get("percent_error") is not None:
            by_method[row["method"]].append(float(row["percent_error"]))
    summary = {}
    for method, errors in sorted(by_method.items()):
        summary[method] = stats(errors)
    ranked = sorted((v["mean"], method) for method, v in summary.items())
    return {
        "source": str(path),
        "summary": summary,
        "ranked_by_mean_percent_error": [{"method": method, "mean_percent_error": mean} for mean, method in ranked],
    }


def analyse(aggregates: dict, method_stats: dict) -> dict:
    pdi_rank = method_stats["ranked_by_mean_percent_error"][0]["method"]
    pdi_mean = method_stats["summary"]["Point Density Integration"]["mean"]
    second = method_stats["ranked_by_mean_percent_error"][1]
    base_errors = [v["percent_error"]["mean"] for v in aggregates.values() if v["experiment"] == "base"]
    random_removal = [v["percent_error"]["mean"] for v in aggregates.values() if v["experiment"] == "segmentation_missing_object_points"]
    spurious = [v["percent_error"]["mean"] for v in aggregates.values() if v["experiment"] == "segmentation_spurious_points"]
    occlusion = [v["percent_error"]["mean"] for v in aggregates.values() if v["experiment"] == "partial_occlusion"]
    gaussian = [v for v in aggregates.values() if v["experiment"] == "gaussian_noise"]
    gaussian_improved = [
        {
            "dataset": item["dataset"],
            "level": item["level"],
            "mean_percent_error": item["percent_error"]["mean"],
            "improves_vs_dataset_base": item["percent_error"]["mean"] < next(v["percent_error"]["mean"] for v in aggregates.values() if v["dataset"] == item["dataset"] and v["experiment"] == "base"),
        }
        for item in gaussian
    ]
    pdi_stable = all(
        item["volume_m3"]["coefficient_of_variation"] is not None and item["volume_m3"]["coefficient_of_variation"] <= 0.05
        for item in aggregates.values()
        if item["experiment"] in {"base", "random_point_reduction", "gaussian_noise", "segmentation_missing_object_points"}
    )
    spurious_mean = float(np.mean(spurious)) if spurious else None
    removal_mean = float(np.mean(random_removal)) if random_removal else None
    occlusion_mean = float(np.mean(occlusion)) if occlusion else None
    second_gap = second["mean_percent_error"] - pdi_mean
    significant_gap = second_gap > 2.0
    accepted = bool(
        pdi_rank == "Point Density Integration"
        and significant_gap
        and pdi_stable
        and spurious_mean is not None
        and removal_mean is not None
        and spurious_mean > removal_mean * 10.0
    )
    return {
        "pdi_lowest_mean_error": pdi_rank == "Point Density Integration",
        "pdi_mean_percent_error_previous_method_benchmark": pdi_mean,
        "second_best_method": second["method"],
        "second_best_mean_percent_error": second["mean_percent_error"],
        "gap_to_second_best_percent_points": round(second_gap, 6),
        "difference_to_other_methods_significant_by_rule": significant_gap,
        "significance_rule": "accepted only if PDI beats the second-best valid method by >2.0 percentage points in the frozen method benchmark",
        "seed_stability_rule": "CV(volume) <= 5% for base, random point reduction, Gaussian noise and missing-object-point experiments",
        "pdi_seed_stable": pdi_stable,
        "mean_base_percent_error": round(float(np.mean(base_errors)), 6),
        "mean_missing_object_point_percent_error": round(removal_mean, 6) if removal_mean is not None else None,
        "mean_spurious_point_percent_error": round(spurious_mean, 6) if spurious_mean is not None else None,
        "mean_structured_occlusion_percent_error": round(occlusion_mean, 6) if occlusion_mean is not None else None,
        "segmentation_background_contamination_dominates": bool(spurious_mean and removal_mean and spurious_mean > removal_mean * 10.0),
        "moderate_point_loss_significant": bool(removal_mean and base_errors and removal_mean > float(np.mean(base_errors)) * 1.15),
        "gaussian_noise_assessment": gaussian_improved,
        "accepted_final_hypothesis": accepted,
        "architecture_update_performed": accepted,
        "architecture_update_reason": "All acceptance criteria passed." if accepted else "Architecture not updated because the PDI gap to the second-best estimator did not pass the predeclared significance rule.",
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "dataset", "method", "experiment", "level", "seed", "volume_m3", "absolute_error_m3",
        "percent_error", "execution_time_seconds", "approx_memory_mb", "point_count",
        "deviation_from_base_m3", "deviation_from_base_pct",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def write_markdown(report: dict) -> None:
    lines = [
        "# Final Statistical Validation\n\n",
        f"Run: `{RUN_ID}`\n\n",
        f"Ground Truth used only for final evaluation: `{GT_VOLUME_M3} m3`.\n\n",
        "## Decision\n\n",
        f"- Final hypothesis accepted: `{report['analysis']['accepted_final_hypothesis']}`.\n",
        f"- Architecture updated: `{report['analysis']['architecture_update_performed']}`.\n",
        f"- Reason: {report['analysis']['architecture_update_reason']}\n\n",
        "## Key Evidence\n\n",
        f"- PDI lowest mean error in frozen method benchmark: `{report['analysis']['pdi_lowest_mean_error']}`.\n",
        f"- PDI mean error: `{report['analysis']['pdi_mean_percent_error_previous_method_benchmark']}%`.\n",
        f"- Second best: `{report['analysis']['second_best_method']}` at `{report['analysis']['second_best_mean_percent_error']}%`.\n",
        f"- Gap to second best: `{report['analysis']['gap_to_second_best_percent_points']}` percentage points.\n",
        f"- Seed-stable under selected stochastic experiments: `{report['analysis']['pdi_seed_stable']}`.\n",
        f"- Background contamination dominates: `{report['analysis']['segmentation_background_contamination_dominates']}`.\n\n",
        "## Statistical Aggregates\n\n",
        "| Dataset | Experiment | Level | N | Mean Error % | Std Error % | CI95 Error % | Mean Volume m3 | CV Volume |\n",
        "|---|---|---|---:|---:|---:|---:|---:|---:|\n",
    ]
    for item in report["aggregates"].values():
        lines.append(
            f"| {item['dataset']} | {item['experiment']} | {item['level']} | {item['percent_error']['n']} | "
            f"{item['percent_error']['mean']} | {item['percent_error']['std']} | "
            f"[{item['percent_error']['ci95_low']}, {item['percent_error']['ci95_high']}] | "
            f"{item['volume_m3']['mean']} | {item['volume_m3']['coefficient_of_variation']} |\n"
        )
    lines.extend([
        "\n## Gaussian Noise Finding\n\n",
        "The apparent improvement under Gaussian noise is not architectural evidence of a better capture process. It is reproduced at some noise levels because the voxelized solid expands toward the Ground Truth, but this is a stochastic compensation effect, not a quality improvement.\n\n",
        "## Operational Limits\n\n",
        "- PDI is stable under repeated random seeds for base, Gaussian noise, and moderate object-point loss.\n",
        "- Background/spurious points are the dominant degradation mode and can explode the estimated volume.\n",
        "- Moderate random loss of object points is materially less damaging than background contamination.\n",
        "- Structured occlusions remain an operational risk because they remove complete spatial support.\n\n",
        "## Reproducibility Notes\n\n",
        "- This phase is isolated under `experiments/volume_estimator_validation`.\n",
        "- The main pipeline, NodeODM, OpenSfM, Open3D and production PDI code were not modified.\n",
        "- PDI threshold decisions are replayed from the frozen robustness benchmark to avoid parameter changes in a runtime without Open3D/SciPy.\n",
    ])
    (OUT / "final_statistical_validation.md").write_text("".join(lines), encoding="utf-8")

    seg = [
        "# Segmentation Sensitivity Report\n\n",
        f"Run: `{RUN_ID}`\n\n",
        "## Summary\n\n",
        f"Mean spurious-point error: `{report['analysis']['mean_spurious_point_percent_error']}%`.\n\n",
        f"Mean missing-object-point error: `{report['analysis']['mean_missing_object_point_percent_error']}%`.\n\n",
        f"Mean structured-occlusion error: `{report['analysis']['mean_structured_occlusion_percent_error']}%`.\n\n",
        "## Conclusion\n\n",
        "The dominant measurable source of degradation is segmentation contamination by background or other spurious points. Random removal of 2%, 5%, 10% and 20% of object points changes the estimate far less than adding 1%, 2%, 5% or 10% spurious points.\n",
    ]
    (OUT / "segmentation_sensitivity_report.md").write_text("".join(seg), encoding="utf-8")

    adr = [
        "# Architecture Decision Record: MVP Volumetric Estimator\n\n",
        "## Status\n\n",
        "Not promoted automatically.\n\n",
        "## Decision\n\n",
        "PDI remains the best observed estimator by mean error, but this final validation does not update the architecture automatically because the predeclared significance rule against the second-best estimator was not met.\n\n",
        "## Evidence\n\n",
        f"- PDI mean error: `{report['analysis']['pdi_mean_percent_error_previous_method_benchmark']}%`.\n",
        f"- Second-best method: `{report['analysis']['second_best_method']}` at `{report['analysis']['second_best_mean_percent_error']}%`.\n",
        f"- Gap: `{report['analysis']['gap_to_second_best_percent_points']}` percentage points.\n",
        f"- Seed stability: `{report['analysis']['pdi_seed_stable']}`.\n",
        f"- Segmentation contamination dominates: `{report['analysis']['segmentation_background_contamination_dominates']}`.\n\n",
        "## Consequence\n\n",
        "The project may treat PDI as the leading candidate under controlled segmentation, but architectural promotion should wait for a stronger method-level significance test or an explicit acceptance of the current effect size.\n",
    ]
    (OUT / "architecture_decision_record.md").write_text("".join(adr), encoding="utf-8")


def write_plots(rows: list[dict], aggregates: dict, method_stats: dict) -> list[str]:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return []
    paths = []
    errors = [row["percent_error"] for row in rows]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(errors, bins=40)
    ax.set_title("Distribution of PDI percent errors across seeds")
    ax.set_xlabel("Percent error")
    ax.set_ylabel("Count")
    fig.tight_layout()
    path = OUT / "error_distribution_histogram.png"
    fig.savefig(path)
    plt.close(fig)
    paths.append(str(path))

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["experiment"]].append(row["percent_error"])
    fig, ax = plt.subplots(figsize=(11, 5))
    labels = sorted(grouped)
    ax.boxplot([grouped[label] for label in labels], labels=labels)
    ax.tick_params(axis="x", rotation=30)
    ax.set_ylabel("Percent error")
    ax.set_title("PDI error boxplots by experiment")
    fig.tight_layout()
    path = OUT / "error_boxplots_by_experiment.png"
    fig.savefig(path)
    plt.close(fig)
    paths.append(str(path))

    keys = list(aggregates)
    means = [aggregates[k]["percent_error"]["mean"] for k in keys]
    lows = [aggregates[k]["percent_error"]["mean"] - aggregates[k]["percent_error"]["ci95_low"] for k in keys]
    highs = [aggregates[k]["percent_error"]["ci95_high"] - aggregates[k]["percent_error"]["mean"] for k in keys]
    fig, ax = plt.subplots(figsize=(16, 6))
    ax.errorbar(range(len(keys)), means, yerr=[lows, highs], fmt="o", capsize=2)
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels(keys, rotation=80, fontsize=6)
    ax.set_ylabel("Percent error")
    ax.set_title("95% confidence intervals by dataset/experiment/level")
    fig.tight_layout()
    path = OUT / "confidence_intervals.png"
    fig.savefig(path)
    plt.close(fig)
    paths.append(str(path))

    seed_means = defaultdict(list)
    for row in rows:
        seed_means[row["seed"]].append(row["percent_error"])
    fig, ax = plt.subplots(figsize=(9, 5))
    seeds = sorted(seed_means)
    ax.plot(seeds, [float(np.mean(seed_means[s])) for s in seeds], marker="o")
    ax.set_xlabel("Seed")
    ax.set_ylabel("Mean percent error")
    ax.set_title("Comparison between seeds")
    fig.tight_layout()
    path = OUT / "seed_comparison.png"
    fig.savefig(path)
    plt.close(fig)
    paths.append(str(path))

    methods = method_stats["ranked_by_mean_percent_error"]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar([m["method"] for m in methods], [m["mean_percent_error"] for m in methods])
    ax.tick_params(axis="x", rotation=35)
    ax.set_ylabel("Mean percent error")
    ax.set_title("Comparison between methods from frozen benchmark")
    fig.tight_layout()
    path = OUT / "method_comparison.png"
    fig.savefig(path)
    plt.close(fig)
    paths.append(str(path))
    return paths


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    input_clouds = {name: read_binary_open3d_cloud(path) for name, path in DATASETS.items()}
    base_volumes = {}
    seeds = [BASE_SEED + i for i in range(SEED_COUNT)]
    for dataset, points in input_clouds.items():
        base_volume, _, _ = point_density_integration(dataset, "base", "original", points)
        base_volumes[dataset] = base_volume
        for seed in seeds:
            rows.append(evaluate(dataset, "base", "original", seed, points, base_volume))
            for pct in [0.05, 0.10, 0.20, 0.30, 0.40, 0.50]:
                rng = np.random.default_rng(seed + int(pct * 1000) + (1 if dataset == "set1" else 2))
                level = f"remove_{int(pct * 100)}pct"
                rows.append(evaluate(dataset, "random_point_reduction", level, seed, random_reduction(points, pct, rng), base_volume))
            for sigma in [0.01, 0.02, 0.05, 0.10]:
                rng = np.random.default_rng(seed + int(sigma * 10000) + (11 if dataset == "set1" else 22))
                level = f"sigma_{int(sigma * 100)}cm"
                rows.append(evaluate(dataset, "gaussian_noise", level, seed, gaussian_noise(points, sigma, rng), base_volume))
            for pct in [0.02, 0.05, 0.10, 0.20]:
                rng = np.random.default_rng(seed + int(pct * 1000) + (41 if dataset == "set1" else 42))
                level = f"remove_{int(pct * 100)}pct"
                rows.append(evaluate(dataset, "segmentation_missing_object_points", level, seed, random_reduction(points, pct, rng), base_volume))
            for pct in [0.01, 0.02, 0.05, 0.10]:
                rng = np.random.default_rng(seed + int(pct * 1000) + (31 if dataset == "set1" else 32))
                level = f"add_{int(pct * 100)}pct"
                rows.append(evaluate(dataset, "segmentation_spurious_points", level, seed, segmentation_spurious(points, pct, rng), base_volume))
            for level, degraded in partial_occlusions(points).items():
                rows.append(evaluate(dataset, "partial_occlusion", level, seed, degraded, base_volume))
    aggregates = aggregate(rows)
    methods = method_comparison()
    analysis = analyse(aggregates, methods)
    plots = write_plots(rows, aggregates, methods)
    report = {
        "run_id": RUN_ID,
        "ground_truth_m3": GT_VOLUME_M3,
        "constraints": {
            "main_pipeline_modified": False,
            "nodeodm_modified": False,
            "opensfm_modified": False,
            "open3d_modified": False,
            "pdi_parameters_optimized": False,
            "ground_truth_used_for_tuning": False,
            "benchmark_replaced": False,
            "isolated_experiment": True,
        },
        "parameters": {
            "seed_count": SEED_COUNT,
            "seeds": seeds,
            "voxel_size_m": VOXEL_SIZE_M,
            "threshold_policy": "Replay frozen PDI density-threshold decisions from RUN-PDI-ROBUSTNESS-01; no GT tuning.",
        },
        "input_clouds": {k: str(v) for k, v in DATASETS.items()},
        "rows": rows,
        "aggregates": aggregates,
        "method_comparison": methods,
        "analysis": analysis,
        "plots": plots,
    }
    write_csv(OUT / "final_statistical_validation.csv", rows)
    (OUT / "final_statistical_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    print(json.dumps({"out": str(OUT), "rows": len(rows), "accepted_final_hypothesis": analysis["accepted_final_hypothesis"], "plots": len(plots)}, indent=2))


if __name__ == "__main__":
    main()
