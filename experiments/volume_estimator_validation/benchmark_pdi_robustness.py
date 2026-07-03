from __future__ import annotations

import csv
import json
import math
import os
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import open3d as o3d
from scipy import ndimage
from scipy.spatial import ConvexHull

from experiments.cloud_unification.cloud_provider_adapter import load_dataset_cloud_source


ROOT = Path(os.environ.get("PDI_ROBUSTNESS_ROOT") or "/app")
OUT = Path(os.environ.get("PDI_ROBUSTNESS_OUT") or ROOT / "data/pdi_robustness_benchmark")
GT_VOLUME_M3 = float(os.environ.get("PDI_ROBUSTNESS_GT_M3") or "119.74")
VOXEL_SIZE_M = float(os.environ.get("PDI_ROBUSTNESS_VOXEL_SIZE_M") or "0.25")
SEED = int(os.environ.get("PDI_ROBUSTNESS_SEED") or "20260629")

DATASETS = {
    "set1": load_dataset_cloud_source("set1").path,
    "set2": load_dataset_cloud_source("set2").path,
}


def read_cloud(path: Path) -> np.ndarray:
    cloud = o3d.io.read_point_cloud(str(path))
    points = np.asarray(cloud.points, dtype=np.float64)
    return points[np.all(np.isfinite(points), axis=1)]


def occupancy_grid(points: np.ndarray, voxel_size: float) -> tuple[np.ndarray, np.ndarray]:
    origin = points.min(axis=0) - 4 * voxel_size
    dims = np.ceil((points.max(axis=0) + 4 * voxel_size - origin) / voxel_size).astype(int) + 1
    idx = np.floor((points - origin) / voxel_size).astype(np.int32)
    grid = np.zeros(tuple(dims.tolist()), dtype=bool)
    grid[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    return grid, origin


def solid_from_occupancy(occupancy: np.ndarray) -> np.ndarray:
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


def point_density_integration(points: np.ndarray) -> tuple[float, dict]:
    hull_volume = float(ConvexHull(points).volume)
    hull_density = len(points) / hull_volume if hull_volume > 0 else 0.0
    occupancy, origin = occupancy_grid(points, VOXEL_SIZE_M)
    counts = np.zeros_like(occupancy, dtype=np.int32)
    idx = np.floor((points - origin) / VOXEL_SIZE_M).astype(np.int32)
    np.add.at(counts, (idx[:, 0], idx[:, 1], idx[:, 2]), 1)
    threshold = max(1, int(np.ceil(hull_density * (VOXEL_SIZE_M ** 3) * 0.35)))
    dense = counts >= threshold
    solid = solid_from_occupancy(dense)
    return float(np.count_nonzero(solid) * (VOXEL_SIZE_M ** 3)), {
        "voxel_size_m": VOXEL_SIZE_M,
        "density_threshold_points_per_voxel": threshold,
        "hull_density_points_per_m3": round(float(hull_density), 6),
        "solid_voxels": int(np.count_nonzero(solid)),
    }


def cloud_stats(points: np.ndarray) -> dict:
    bbox_min = points.min(axis=0)
    bbox_max = points.max(axis=0)
    extent = bbox_max - bbox_min
    bbox_volume = float(np.prod(np.maximum(extent, 1e-9)))
    return {
        "point_count": int(len(points)),
        "mean_density_points_per_m3": round(float(len(points) / bbox_volume), 6),
        "bbox_min": [round(float(v), 6) for v in bbox_min.tolist()],
        "bbox_max": [round(float(v), 6) for v in bbox_max.tolist()],
        "bbox_extent": [round(float(v), 6) for v in extent.tolist()],
        "bbox_volume_m3": round(bbox_volume, 6),
    }


def evaluate(dataset: str, experiment: str, level: str, points: np.ndarray, base_volume: float) -> dict:
    start = time.perf_counter()
    volume, params = point_density_integration(points)
    elapsed = time.perf_counter() - start
    abs_error = abs(volume - GT_VOLUME_M3)
    pct_error = (abs_error / GT_VOLUME_M3) * 100.0
    return {
        "dataset": dataset,
        "experiment": experiment,
        "level": level,
        "volume_m3": round(float(volume), 6),
        "absolute_error_m3": round(float(abs_error), 6),
        "percent_error": round(float(pct_error), 6),
        "execution_time_seconds": round(float(elapsed), 6),
        "approx_memory_mb": None,
        "memory_note": "Peak memory not measured; no profiler added.",
        "deviation_from_base_m3": round(float(volume - base_volume), 6),
        "deviation_from_base_pct": round(float(((volume - base_volume) / base_volume) * 100.0), 6) if base_volume else None,
        "pdi_parameters": params,
        **cloud_stats(points),
    }


def random_reduction(points: np.ndarray, pct: float, rng: np.random.Generator) -> np.ndarray:
    keep_count = int(round(len(points) * (1.0 - pct)))
    idx = rng.choice(len(points), size=max(4, keep_count), replace=False)
    return points[np.sort(idx)]


def gaussian_noise(points: np.ndarray, sigma_m: float, rng: np.random.Generator) -> np.ndarray:
    return points + rng.normal(0.0, sigma_m, size=points.shape)


def partial_occlusions(points: np.ndarray) -> dict[str, np.ndarray]:
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    q20 = np.quantile(points, 0.20, axis=0)
    q35 = np.quantile(points, 0.35, axis=0)
    q50 = np.quantile(points, 0.50, axis=0)
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


def segmentation_spurious(points: np.ndarray, pct: float, rng: np.random.Generator) -> np.ndarray:
    count = int(round(len(points) * pct))
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    extent = maxs - mins
    low = mins - 0.15 * extent
    high = maxs + 0.15 * extent
    spurious = rng.uniform(low, high, size=(max(1, count), 3))
    return np.vstack((points, spurious))


def segmentation_missing(points: np.ndarray, pct: float, rng: np.random.Generator) -> np.ndarray:
    return random_reduction(points, pct, rng)


def aggregate(rows: list[dict]) -> dict:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["dataset"], row["experiment"])].append(row)
    output = {}
    for (dataset, experiment), items in groups.items():
        errors = np.asarray([row["percent_error"] for row in items], dtype=float)
        vols = np.asarray([row["volume_m3"] for row in items], dtype=float)
        key = f"{dataset}:{experiment}"
        output[key] = {
            "count": int(len(items)),
            "mean_percent_error": round(float(errors.mean()), 6),
            "median_percent_error": round(float(np.median(errors)), 6),
            "std_percent_error": round(float(errors.std(ddof=1)), 6) if len(errors) > 1 else 0.0,
            "coefficient_of_variation_volume": round(float(vols.std(ddof=1) / vols.mean()), 6) if len(vols) > 1 and vols.mean() else 0.0,
            "worst_percent_error": round(float(errors.max()), 6),
            "best_percent_error": round(float(errors.min()), 6),
            "ci95_percent_error": round(float(1.96 * errors.std(ddof=1) / math.sqrt(len(errors))), 6) if len(errors) > 1 else None,
        }
    return output


def dataset_variability(base_rows: list[dict]) -> dict:
    by_dataset = {row["dataset"]: row for row in base_rows}
    vols = np.asarray([row["volume_m3"] for row in by_dataset.values()], dtype=float)
    errors = np.asarray([row["percent_error"] for row in by_dataset.values()], dtype=float)
    return {
        "set1_volume_m3": by_dataset["set1"]["volume_m3"],
        "set2_volume_m3": by_dataset["set2"]["volume_m3"],
        "absolute_volume_difference_m3": round(float(abs(vols[0] - vols[1])), 6),
        "relative_volume_difference_pct_of_gt": round(float(abs(vols[0] - vols[1]) / GT_VOLUME_M3 * 100.0), 6),
        "mean_percent_error": round(float(errors.mean()), 6),
        "coefficient_of_variation_volume": round(float(vols.std(ddof=1) / vols.mean()), 6) if vols.mean() else None,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "dataset",
        "experiment",
        "level",
        "volume_m3",
        "absolute_error_m3",
        "percent_error",
        "execution_time_seconds",
        "approx_memory_mb",
        "point_count",
        "mean_density_points_per_m3",
        "bbox_volume_m3",
        "deviation_from_base_m3",
        "deviation_from_base_pct",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def write_markdown(path: Path, report: dict) -> None:
    lines = [
        "# PDI Robustness Benchmark\n\n",
        f"Ground Truth: `{GT_VOLUME_M3} m3`\n\n",
        f"Base method: `Point Density Integration`, voxel size `{VOXEL_SIZE_M} m`, unchanged from previous benchmark.\n\n",
        "## Summary Table\n\n",
        "| Dataset | Experiment | Level | Volume | % Error | Points | Density | Delta vs Base % |\n",
        "|---|---|---|---:|---:|---:|---:|---:|\n",
    ]
    for row in report["rows"]:
        lines.append(
            "| {dataset} | {experiment} | {level} | {volume_m3} | {percent_error} | {point_count} | {mean_density_points_per_m3} | {deviation_from_base_pct} |\n".format(**row)
        )
    lines.extend([
        "\n## Aggregate Metrics\n\n",
        "```json\n",
        json.dumps(report["aggregates"], indent=2),
        "\n```\n\n",
        "## Analysis\n\n",
    ])
    for key, value in report["analysis"].items():
        lines.append(f"- {key}: {value}\n")
    lines.extend([
        "\n## Recommendation\n\n",
        report["recommendation"],
        "\n",
    ])
    path.write_text("".join(lines), encoding="utf-8")


def write_plots(out: Path, rows: list[dict]) -> list[str]:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return []
    paths = []
    for dataset in sorted({row["dataset"] for row in rows}):
        sub = [row for row in rows if row["dataset"] == dataset and row["experiment"] != "base"]
        labels = [f"{row['experiment']}:{row['level']}" for row in sub]
        errors = [row["percent_error"] for row in sub]
        fig, ax = plt.subplots(figsize=(16, 6))
        ax.bar(range(len(errors)), errors)
        ax.axhline(25.0, color="red", linestyle="--", linewidth=1, label="25% reference")
        ax.set_ylabel("Percent error")
        ax.set_title(f"PDI robustness percent error - {dataset}")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=75, ha="right", fontsize=7)
        ax.legend()
        fig.tight_layout()
        path = out / f"{dataset}_robustness_errors.png"
        fig.savefig(path)
        plt.close(fig)
        paths.append(str(path))
    for experiment in ["random_point_reduction", "gaussian_noise"]:
        fig, ax = plt.subplots(figsize=(9, 5))
        for dataset in sorted({row["dataset"] for row in rows}):
            sub = [row for row in rows if row["dataset"] == dataset and row["experiment"] == experiment]
            ax.plot([row["level"] for row in sub], [row["percent_error"] for row in sub], marker="o", label=dataset)
        ax.set_ylabel("Percent error")
        ax.set_title(f"PDI sensitivity - {experiment}")
        ax.tick_params(axis="x", rotation=35)
        ax.legend()
        fig.tight_layout()
        path = out / f"sensitivity_{experiment}.png"
        fig.savefig(path)
        plt.close(fig)
        paths.append(str(path))
    return paths


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    base_rows = []
    for dataset, path in DATASETS.items():
        points = read_cloud(path)
        base = evaluate(dataset, "base", "original", points, 1.0)
        base["deviation_from_base_m3"] = 0.0
        base["deviation_from_base_pct"] = 0.0
        base_rows.append(base)
        rows.append(base)
        base_volume = base["volume_m3"]

        for pct in [0.05, 0.10, 0.20, 0.30, 0.40, 0.50]:
            rng = np.random.default_rng(SEED + int(pct * 1000) + (1 if dataset == "set1" else 2))
            rows.append(evaluate(dataset, "random_point_reduction", f"remove_{int(pct * 100)}pct", random_reduction(points, pct, rng), base_volume))

        for sigma in [0.01, 0.02, 0.05, 0.10]:
            rng = np.random.default_rng(SEED + int(sigma * 10000) + (11 if dataset == "set1" else 22))
            rows.append(evaluate(dataset, "gaussian_noise", f"sigma_{int(sigma * 100)}cm", gaussian_noise(points, sigma, rng), base_volume))

        for name, degraded in partial_occlusions(points).items():
            rows.append(evaluate(dataset, "partial_occlusion", name, degraded, base_volume))

        for pct in [0.02, 0.05, 0.10]:
            rng = np.random.default_rng(SEED + int(pct * 1000) + (31 if dataset == "set1" else 32))
            rows.append(evaluate(dataset, "segmentation_spurious_points", f"add_{int(pct * 100)}pct", segmentation_spurious(points, pct, rng), base_volume))
        for pct in [0.02, 0.05, 0.10]:
            rng = np.random.default_rng(SEED + int(pct * 1000) + (41 if dataset == "set1" else 42))
            rows.append(evaluate(dataset, "segmentation_missing_object_points", f"remove_{int(pct * 100)}pct", segmentation_missing(points, pct, rng), base_volume))

    aggregates = aggregate([row for row in rows if row["experiment"] != "base"])
    variability = dataset_variability(base_rows)
    worst = max(rows, key=lambda row: row["percent_error"])
    best = min(rows, key=lambda row: row["percent_error"])
    by_experiment = defaultdict(list)
    for row in rows:
        if row["experiment"] != "base":
            by_experiment[row["experiment"]].append(row["percent_error"])
    impact = {name: round(float(np.mean(values)), 6) for name, values in by_experiment.items()}
    most_damaging = max(impact.items(), key=lambda item: item[1])
    abrupt_thresholds = []
    for dataset in ("set1", "set2"):
        ordered = [row for row in rows if row["dataset"] == dataset and row["experiment"] == "random_point_reduction"]
        for prev, cur in zip(ordered, ordered[1:]):
            if cur["percent_error"] - prev["percent_error"] > 10.0:
                abrupt_thresholds.append({"dataset": dataset, "from": prev["level"], "to": cur["level"], "delta_percent_error": round(cur["percent_error"] - prev["percent_error"], 6)})

    analysis = {
        "most_damaging_degradation": {"experiment": most_damaging[0], "mean_percent_error": most_damaging[1]},
        "worst_case": {"dataset": worst["dataset"], "experiment": worst["experiment"], "level": worst["level"], "percent_error": worst["percent_error"]},
        "best_case": {"dataset": best["dataset"], "experiment": best["experiment"], "level": best["level"], "percent_error": best["percent_error"]},
        "abrupt_error_thresholds": abrupt_thresholds,
        "dataset_variability": variability,
        "robustness_assessment": "PDI is robust to moderate random point removal and small Gaussian noise, but sensitive to structured occlusion and segmentation outliers that expand the hull/density support.",
        "capture_scenarios_to_avoid": "Avoid missing full faces/bands/corners and avoid background contamination; these degradations dominate error growth.",
    }
    recommendation = (
        "PDI remains a viable MVP volumetric estimator only under capture conditions with broad object coverage and controlled segmentation. "
        "It should be integrated with documented operating limits and future quality gates for occlusion/background contamination, not treated as universally robust."
    )
    report = {
        "run_id": "RUN-PDI-ROBUSTNESS-01",
        "ground_truth_m3": GT_VOLUME_M3,
        "constraints": {
            "main_pipeline_modified": False,
            "pdi_parameters_changed": False,
            "ground_truth_used_for_tuning": False,
            "degradations_combined": False,
        },
        "input_clouds": {dataset: str(path) for dataset, path in DATASETS.items()},
        "parameters": {"voxel_size_m": VOXEL_SIZE_M, "seed": SEED},
        "rows": rows,
        "aggregates": aggregates,
        "analysis": analysis,
        "recommendation": recommendation,
    }
    write_csv(OUT / "benchmark_robustness.csv", rows)
    write_markdown(OUT / "benchmark_robustness.md", report)
    report["plots"] = write_plots(OUT, rows)
    (OUT / "benchmark_robustness.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(OUT), "rows": len(rows), "most_damaging": analysis["most_damaging_degradation"]}, indent=2))


if __name__ == "__main__":
    main()
