from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path
from typing import Any

import numpy as np

from experiments.cloud_unification.cloud_provider_adapter import load_dataset_cloud_source

from pdi_estimator import (
    DEFAULT_VOXEL_SIZE_M,
    confidence_from_bootstrap,
    confidence_score,
    estimate_volume,
    quality_gates,
    read_point_cloud,
    result_to_dict,
)


ROOT = Path(os.environ.get("PDI_MVP_ROOT") or "/app")
OUT = Path(os.environ.get("PDI_MVP_OUT") or ROOT / "data/pdi_mvp_readiness")
GT_VOLUME_M3 = float(os.environ.get("PDI_MVP_GT_M3") or "119.74")
VOXEL_SIZE_M = float(os.environ.get("PDI_MVP_VOXEL_SIZE_M") or str(DEFAULT_VOXEL_SIZE_M))
BASELINE_JSON = Path(os.environ.get("PDI_MVP_BASELINE_JSON") or ROOT / "data/volume_estimator_benchmark/benchmark_volume_estimators.json")
ROBUSTNESS_JSON = Path(os.environ.get("PDI_MVP_ROBUSTNESS_JSON") or ROOT / "data/pdi_robustness_benchmark/benchmark_robustness.json")

DATASETS = {
    "set1": load_dataset_cloud_source("set1").path,
    "set2": load_dataset_cloud_source("set2").path,
}


def approx_memory_mb() -> float | None:
    try:
        import resource

        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(float(value / 1024.0), 3)
    except Exception:
        return None


def load_previous_pdi() -> dict[str, dict[str, Any]]:
    data = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
    output: dict[str, dict[str, Any]] = {}
    for row in data["rows"]:
        if row["method"] == "Point Density Integration":
            output[row["dataset"]] = row
    return output


def load_robustness_context() -> dict[str, Any]:
    if not ROBUSTNESS_JSON.exists():
        return {}
    data = json.loads(ROBUSTNESS_JSON.read_text(encoding="utf-8"))
    return {
        "most_damaging_degradation": data.get("analysis", {}).get("most_damaging_degradation"),
        "worst_case": data.get("analysis", {}).get("worst_case"),
        "robustness_assessment": data.get("analysis", {}).get("robustness_assessment"),
        "recommendation": data.get("recommendation"),
    }


def error_metrics(volume: float) -> tuple[float, float]:
    absolute = abs(float(volume) - GT_VOLUME_M3)
    return round(absolute, 6), round((absolute / GT_VOLUME_M3) * 100.0, 6)


def run_dataset(dataset: str, path: Path, previous: dict[str, Any], stability_cv: float | None) -> dict[str, Any]:
    points = read_point_cloud(path)
    memory_before = approx_memory_mb()
    start = time.perf_counter()
    quality = quality_gates(points, VOXEL_SIZE_M)
    stability = confidence_from_bootstrap(points)
    result = estimate_volume(points, VOXEL_SIZE_M)
    confidence = confidence_score(quality, stability_cv=stability.get("volume_cv"))
    total_elapsed = time.perf_counter() - start
    memory_after = approx_memory_mb()
    abs_error, pct_error = error_metrics(result.volume_m3)
    previous_volume = previous.get("volume_m3")
    delta = None if previous_volume is None else round(float(result.volume_m3 - previous_volume), 9)
    equivalent = bool(delta is not None and abs(delta) <= 1e-9)
    return {
        "dataset": dataset,
        "input_cloud": str(path),
        "point_count": int(len(points)),
        "pdi": result_to_dict(result),
        "absolute_error_m3": abs_error,
        "percent_error": pct_error,
        "quality": quality,
        "stability_probe": stability,
        "confidence": confidence,
        "previous_pdi_volume_m3": previous_volume,
        "volume_delta_vs_previous_m3": delta,
        "numeric_equivalence_with_previous_pdi": equivalent,
        "total_time_seconds": round(float(total_elapsed), 6),
        "approx_memory_before_mb": memory_before,
        "approx_memory_after_mb": memory_after,
        "memory_delta_mb": None if memory_before is None or memory_after is None else round(memory_after - memory_before, 3),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "dataset",
        "volume_m3",
        "previous_pdi_volume_m3",
        "volume_delta_vs_previous_m3",
        "absolute_error_m3",
        "percent_error",
        "confidence_score_percent",
        "confidence_level",
        "gate_pass",
        "gate_warning",
        "gate_fail",
        "point_count",
        "mean_density_points_per_m3",
        "isolated_point_ratio",
        "outlier_ratio",
        "spatial_coverage_ratio",
        "lateral_coverage_ratio",
        "top_coverage_ratio",
        "bottom_coverage_ratio",
        "voxel_components",
        "dominant_component_voxel_ratio",
        "execution_time_seconds",
        "total_time_seconds",
        "approx_memory_after_mb",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            metrics = row["quality"]["metrics"]
            writer.writerow(
                {
                    "dataset": row["dataset"],
                    "volume_m3": row["pdi"]["volume_m3"],
                    "previous_pdi_volume_m3": row["previous_pdi_volume_m3"],
                    "volume_delta_vs_previous_m3": row["volume_delta_vs_previous_m3"],
                    "absolute_error_m3": row["absolute_error_m3"],
                    "percent_error": row["percent_error"],
                    "confidence_score_percent": row["confidence"]["score_percent"],
                    "confidence_level": row["confidence"]["level"],
                    "gate_pass": row["quality"]["gate_counts"]["PASS"],
                    "gate_warning": row["quality"]["gate_counts"]["WARNING"],
                    "gate_fail": row["quality"]["gate_counts"]["FAIL"],
                    "point_count": row["point_count"],
                    "mean_density_points_per_m3": metrics["mean_density_points_per_m3"],
                    "isolated_point_ratio": metrics["isolated_point_ratio"],
                    "outlier_ratio": metrics["outlier_ratio"],
                    "spatial_coverage_ratio": metrics["spatial_coverage_ratio"],
                    "lateral_coverage_ratio": metrics["lateral_coverage_ratio"],
                    "top_coverage_ratio": metrics["top_coverage_ratio"],
                    "bottom_coverage_ratio": metrics["bottom_coverage_ratio"],
                    "voxel_components": metrics["voxel_components"],
                    "dominant_component_voxel_ratio": metrics["dominant_component_voxel_ratio"],
                    "execution_time_seconds": row["pdi"]["execution_time_seconds"],
                    "total_time_seconds": row["total_time_seconds"],
                    "approx_memory_after_mb": row["approx_memory_after_mb"],
                }
            )


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# PDI MVP Readiness Benchmark\n\n",
        f"Run ID: `{report['run_id']}`\n\n",
        f"Ground Truth used only for final error calculation: `{GT_VOLUME_M3} m3`\n\n",
        "## Equivalence And Readiness\n\n",
        "| Dataset | Volume m3 | Previous PDI m3 | Delta | Error % | Confidence | Gates PASS/WARN/FAIL | Time s |\n",
        "|---|---:|---:|---:|---:|---|---|---:|\n",
    ]
    for row in report["datasets"]:
        gates = row["quality"]["gate_counts"]
        lines.append(
            f"| {row['dataset']} | {row['pdi']['volume_m3']} | {row['previous_pdi_volume_m3']} | "
            f"{row['volume_delta_vs_previous_m3']} | {row['percent_error']} | "
            f"{row['confidence']['score_percent']}% {row['confidence']['level']} | "
            f"{gates['PASS']}/{gates['WARNING']}/{gates['FAIL']} | {row['total_time_seconds']} |\n"
        )
    lines.extend(
        [
            "\n## Diagnostics\n\n",
        ]
    )
    for row in report["datasets"]:
        lines.append(f"### {row['dataset']}\n\n")
        lines.append(f"- Point count: `{row['point_count']}`\n")
        lines.append(f"- Quality metrics: `{json.dumps(row['quality']['metrics'], ensure_ascii=False)}`\n")
        lines.append("- Confidence diagnosis:\n")
        for reason in row["confidence"]["diagnosis"]:
            lines.append(f"  - {reason}\n")
        lines.append("\n")
    lines.extend(
        [
            "## Decision\n\n",
            f"- Final decision: `{report['decision']['ready_for_mvp_integration']}`\n",
            f"- Basis: {report['decision']['basis']}\n",
            "\n## Traceability\n\n",
            "- No production pipeline code was modified.\n",
            "- PDI parameters were not changed.\n",
            "- Quality gates and confidence score do not use Ground Truth.\n",
            "- Ground Truth is used only in the final benchmark error columns.\n",
        ]
    )
    path.write_text("".join(lines), encoding="utf-8")


def write_plots(out: Path, rows: list[dict[str, Any]]) -> list[str]:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return []
    paths: list[str] = []
    labels = [row["dataset"] for row in rows]
    errors = [row["percent_error"] for row in rows]
    confidence = [row["confidence"]["score_percent"] for row in rows]
    fig, ax1 = plt.subplots(figsize=(8, 4))
    ax1.bar(labels, errors, color="#4b7bec", label="Percent error")
    ax1.set_ylabel("Percent error")
    ax2 = ax1.twinx()
    ax2.plot(labels, confidence, color="#20bf6b", marker="o", label="Confidence")
    ax2.set_ylabel("Confidence score")
    ax1.set_title("PDI MVP readiness: error vs confidence")
    fig.tight_layout()
    path = out / "pdi_readiness_error_confidence.png"
    fig.savefig(path)
    plt.close(fig)
    paths.append(str(path))

    gate_labels = ["PASS", "WARNING", "FAIL"]
    data = np.asarray([[row["quality"]["gate_counts"][label] for label in gate_labels] for row in rows], dtype=float)
    fig, ax = plt.subplots(figsize=(8, 4))
    bottom = np.zeros(len(rows))
    colors = {"PASS": "#20bf6b", "WARNING": "#f7b731", "FAIL": "#eb3b5a"}
    for idx, label in enumerate(gate_labels):
        ax.bar(labels, data[:, idx], bottom=bottom, label=label, color=colors[label])
        bottom += data[:, idx]
    ax.set_ylabel("Quality gate count")
    ax.set_title("PDI quality gates")
    ax.legend()
    fig.tight_layout()
    path = out / "pdi_quality_gates.png"
    fig.savefig(path)
    plt.close(fig)
    paths.append(str(path))
    return paths


def write_audit(path: Path) -> None:
    lines = [
        "# Point Density Integration Technical Audit\n\n",
        "## Scope\n\n",
        "This document audits the current Point Density Integration estimator as an isolated experimental component. It does not define a production-pipeline change.\n\n",
        "## Geometric Assumptions\n\n",
        "- Input is a segmented object point cloud in metric coordinates.\n",
        "- The segmented cloud has broad spatial support around the object.\n",
        "- Background contamination is low; off-object points are not part of the intended support.\n",
        "- The estimator can use voxelized density support as an auxiliary solid for volume, without requiring a watertight mesh.\n\n",
        "## Parameters\n\n",
        "- `voxel_size_m`: `0.25`.\n",
        "- Density threshold: `max(1, ceil(hull_density_points_per_m3 * voxel_size_m^3 * 0.35))`.\n",
        "- Solidification: binary dilation with 3D connectivity-2 for 2 iterations, hole fill, binary closing for 1 iteration, second hole fill, then dominant connected component.\n",
        "- No Ground Truth is used to set any parameter.\n\n",
        "## Implementation Stages\n\n",
        "- Input: finite Nx3 point cloud loaded from PLY.\n",
        "- Preprocessing: finite-point filter only.\n",
        "- Estimation: ConvexHull density, voxel point counts, dense-voxel selection, solid occupancy, volume by solid voxel count.\n",
        "- Postprocessing: dominant connected component in the solid occupancy grid.\n",
        "- Metrics: volume, threshold, hull density, solid voxels, quality gates, confidence score and benchmark error.\n\n",
        "## Dependencies\n\n",
        "- Open3D for PLY point-cloud loading.\n",
        "- NumPy for array operations.\n",
        "- SciPy ConvexHull, cKDTree and ndimage.\n",
        "- Matplotlib only for benchmark plots.\n\n",
        "## Complexity\n\n",
        "- Convex hull: approximately O(n log n) in typical 3D cases, with higher worst-case behavior depending on hull structure.\n",
        "- Voxel indexing/counting: O(n).\n",
        "- Morphological operations: O(V), where V is the voxel-grid cell count.\n",
        "- Quality gates: nearest-neighbor diagnostics use O(n log n) on a capped sample; coverage and component metrics are O(n + V).\n",
        "- Memory: O(n + V). Runtime memory is dominated by boolean/int voxel grids.\n\n",
        "## Known Limitations\n\n",
        "- Spurious background points can expand the convex hull and voxel support, causing severe overestimation.\n",
        "- Structured occlusion can remove full faces or bands and cause underestimation.\n",
        "- The result is quantized by voxel size.\n",
        "- The method does not produce a high-fidelity mesh; the mesh is not the product.\n",
        "- Quality gates are diagnostic only and do not repair the cloud or alter the volume.\n\n",
        "## Observed Strengths\n\n",
        "- Lowest mean volumetric error among evaluated estimators in the previous benchmark.\n",
        "- Fast execution on Set 1 and Set 2.\n",
        "- Robust to moderate random point removal in the previous robustness benchmark.\n",
        "- Does not depend on Poisson watertightness or mesh repair.\n",
    ]
    path.write_text("".join(lines), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    previous = load_previous_pdi()
    stability_values = [row["volume_m3"] for row in previous.values() if row.get("volume_m3") is not None]
    stability_cv = float(np.std(stability_values, ddof=1) / np.mean(stability_values)) if len(stability_values) > 1 else None
    started = time.perf_counter()
    rows = [run_dataset(dataset, path, previous.get(dataset, {}), stability_cv) for dataset, path in DATASETS.items()]
    all_equivalent = all(row["numeric_equivalence_with_previous_pdi"] for row in rows)
    fail_count = sum(row["quality"]["gate_counts"]["FAIL"] for row in rows)
    mean_confidence = float(np.mean([row["confidence"]["score_percent"] for row in rows]))
    decision = "SI" if all_equivalent and fail_count == 0 and mean_confidence >= 60.0 else "NO"
    basis = (
        f"volumes_equivalent={all_equivalent}; total_fail_gates={fail_count}; "
        f"mean_confidence={round(mean_confidence, 2)}%; "
        "decision threshold requires unchanged PDI volume, zero FAIL gates on current Set 1/Set 2, and mean confidence >= 60%."
    )
    report = {
        "run_id": "RUN-PDI-MVP-READINESS-01",
        "constraints": {
            "main_pipeline_modified": False,
            "pdi_behavior_changed": False,
            "ground_truth_used_for_tuning": False,
            "quality_gates_stop_pipeline": False,
            "nodeodm_modified": False,
            "opensfm_modified": False,
            "open3d_modified": False,
        },
        "ground_truth_m3": GT_VOLUME_M3,
        "parameters": {"voxel_size_m": VOXEL_SIZE_M},
        "inputs": {dataset: str(path) for dataset, path in DATASETS.items()},
        "datasets": rows,
        "robustness_context": load_robustness_context(),
        "decision": {"ready_for_mvp_integration": decision, "basis": basis},
        "total_runtime_seconds": round(float(time.perf_counter() - started), 6),
    }
    write_csv(OUT / "benchmark_pdi_mvp_readiness.csv", rows)
    write_markdown(OUT / "benchmark_pdi_mvp_readiness.md", report)
    write_audit(OUT / "pdi_technical_audit.md")
    report["plots"] = write_plots(OUT, rows)
    (OUT / "benchmark_pdi_mvp_readiness.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(OUT), "decision": decision, "mean_confidence": round(mean_confidence, 2), "equivalent": all_equivalent}, indent=2))


if __name__ == "__main__":
    main()
