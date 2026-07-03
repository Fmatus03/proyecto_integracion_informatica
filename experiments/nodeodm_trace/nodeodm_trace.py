from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d
from scipy import ndimage
from scipy.spatial import cKDTree


ROOT = Path(os.environ.get("FORESTVOL_ROOT", "/app"))
DATA_ROOT = ROOT / "data"
if not DATA_ROOT.exists():
    DATA_ROOT = ROOT / "projects" / "ForestVol" / "data"
OUTPUT_DIR = ROOT / "experiments" / "nodeodm_trace"
NODEODM_ROOT = Path(os.environ.get("NODEODM_ROOT", "/nodeodm_data"))
NODEODM_MANIFEST_PATH = Path(os.environ.get("NODEODM_MANIFEST_PATH", "/tmp/nodeodm_task_manifest.json"))
PIPELINE_DIAG = ROOT / "experiments" / "pipeline_diagnostics" / "pipeline_diagnostics.json"


@dataclass(frozen=True)
class RunRef:
    dataset: str
    role: str
    session_id: str
    benchmark_pdi_cloud_rel: str | None = None


RUNS = [
    RunRef("set1", "benchmark", "a3c36266-f866-402f-8bc8-1c2b59b4a4ce", "surface_closure_diagnostics/poisson_input_cloud.ply"),
    RunRef("set1", "production", "b3c14c84-b660-407f-817f-1fc185ce3e9c"),
    RunRef("set2", "benchmark", "b6b04af0-122f-4fcc-af8a-cc553ca5e28d", "surface_closure_diagnostics_2/poisson_input_cloud.ply"),
    RunRef("set2", "production", "723f91e2-b1b5-43f7-b336-6816d8300509"),
]


DENSE_OPTION_KEYS = {
    "depthmap-resolution",
    "pc-quality",
    "mesh-size",
    "feature-quality",
    "matcher-neighbors",
    "min-num-features",
    "fast-orthophoto",
    "use-3dmesh",
    "skip-3dmodel",
    "end-with",
    "rerun",
    "rerun-from",
    "smrf-scalar",
    "smrf-slope",
    "smrf-threshold",
    "smrf-window",
    "pc-filter",
    "pc-classify",
    "ignore-gsd",
    "resize-to",
}


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_ply_header(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"exists": path.exists()}
    if not path.exists():
        return out
    lines: list[str] = []
    try:
        with path.open("rb") as fh:
            for raw in fh:
                line = raw.decode("utf-8", errors="replace").rstrip("\n")
                lines.append(line)
                if line.strip() == "end_header":
                    break
    except Exception as exc:
        out["header_error"] = str(exc)
    vertex_count = None
    for line in lines:
        if line.startswith("element vertex "):
            vertex_count = int(line.split()[-1])
            break
    out["ply_header_vertex_count"] = vertex_count
    out["ply_header"] = lines[:60]
    return out


def load_cloud(path: Path) -> Any | None:
    if not path.exists():
        return None
    cloud = o3d.io.read_point_cloud(str(path))
    if cloud.is_empty():
        return None
    return cloud


def points(cloud: Any) -> np.ndarray:
    return np.asarray(cloud.points, dtype=np.float64)


def cloud_stats(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else None,
        "sha256": sha256(path),
        **read_ply_header(path),
    }
    cloud = load_cloud(path)
    if cloud is None:
        return info
    pts = points(cloud)
    bbox = cloud.get_axis_aligned_bounding_box()
    mins = np.asarray(bbox.min_bound)
    maxs = np.asarray(bbox.max_bound)
    extent = np.asarray(bbox.get_extent())
    bbox_volume = float(np.prod(np.maximum(extent, 0.0))) if len(extent) == 3 else 0.0
    sample = pts if len(pts) <= 12000 else pts[np.linspace(0, len(pts) - 1, 12000).astype(int)]
    nn, _ = cKDTree(pts).query(sample, k=2)
    nn = nn[:, 1]
    normals = None
    if cloud.has_normals():
        normals = np.asarray(cloud.normals, dtype=np.float64)
    hist = {}
    for axis, label in enumerate(("x", "y", "z")):
        counts, edges = np.histogram(pts[:, axis], bins=30)
        hist[label] = {"counts": counts.astype(int).tolist(), "edges": [round(float(v), 6) for v in edges.tolist()]}
    info.update(
        {
            "point_count": int(len(pts)),
            "bbox_min": [round(float(v), 6) for v in mins.tolist()],
            "bbox_max": [round(float(v), 6) for v in maxs.tolist()],
            "bbox_extent": [round(float(v), 6) for v in extent.tolist()],
            "bbox_volume_m3": round(bbox_volume, 6),
            "density_points_per_m3": round(float(len(pts) / bbox_volume), 6) if bbox_volume > 0 else None,
            "mean_nn_distance_m": round(float(np.mean(nn)), 6),
            "median_nn_distance_m": round(float(np.median(nn)), 6),
            "histograms_xyz": hist,
            "has_normals": bool(cloud.has_normals()),
            "normal_mean": [round(float(v), 6) for v in normals.mean(axis=0).tolist()] if normals is not None and len(normals) else None,
            "normal_std": [round(float(v), 6) for v in normals.std(axis=0).tolist()] if normals is not None and len(normals) else None,
        }
    )
    return info


def sample_points(pts: np.ndarray, limit: int = 15000) -> np.ndarray:
    if len(pts) <= limit:
        return pts
    rng = np.random.default_rng(20260630)
    return pts[rng.choice(len(pts), size=limit, replace=False)]


def cloud_compare(a_path: Path, b_path: Path) -> dict[str, Any]:
    a = load_cloud(a_path)
    b = load_cloud(b_path)
    if a is None or b is None:
        return {"available": False, "a": str(a_path), "b": str(b_path)}
    a_pts = sample_points(points(a))
    b_pts = sample_points(points(b))
    a_tree = cKDTree(a_pts)
    b_tree = cKDTree(b_pts)
    a_to_b, _ = b_tree.query(a_pts, k=1)
    b_to_a, _ = a_tree.query(b_pts, k=1)
    icp = {}
    try:
        a_icp = a.voxel_down_sample(0.05) if len(a.points) > 20000 else a
        b_icp = b.voxel_down_sample(0.05) if len(b.points) > 20000 else b
        result = o3d.pipelines.registration.registration_icp(
            a_icp,
            b_icp,
            1.0,
            np.eye(4),
            o3d.pipelines.registration.TransformationEstimationPointToPoint(),
            o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=60),
        )
        icp = {
            "fitness": round(float(result.fitness), 6),
            "inlier_rmse_m": round(float(result.inlier_rmse), 6),
            "transformation": np.asarray(result.transformation).round(6).tolist(),
        }
    except Exception as exc:
        icp = {"available": False, "error": str(exc)}
    return {
        "a": str(a_path),
        "b": str(b_path),
        "a_to_b_mean_m": round(float(np.mean(a_to_b)), 6),
        "b_to_a_mean_m": round(float(np.mean(b_to_a)), 6),
        "chamfer_distance_m": round(float((np.mean(a_to_b) + np.mean(b_to_a)) / 2.0), 6),
        "hausdorff_distance_m": round(float(max(np.max(a_to_b), np.max(b_to_a))), 6),
        "a_overlap_at_0_25m": round(float(np.mean(a_to_b <= 0.25)), 6),
        "b_overlap_at_0_25m": round(float(np.mean(b_to_a <= 0.25)), 6),
        "icp": icp,
    }


def connected_components(path: Path, voxel_size: float = 0.25) -> dict[str, Any]:
    cloud = load_cloud(path)
    if cloud is None:
        return {"available": False, "path": str(path)}
    pts = points(cloud)
    origin = pts.min(axis=0)
    idx = np.floor((pts - origin) / voxel_size).astype(np.int32)
    dims = idx.max(axis=0) + 1
    occupancy = np.zeros(tuple(dims.tolist()), dtype=bool)
    occupancy[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    labels, count = ndimage.label(occupancy, structure=ndimage.generate_binary_structure(3, 2))
    point_labels = labels[idx[:, 0], idx[:, 1], idx[:, 2]]
    comp: list[dict[str, Any]] = []
    for label in range(1, count + 1):
        mask = point_labels == label
        cpts = pts[mask]
        if len(cpts) == 0:
            continue
        extent = cpts.max(axis=0) - cpts.min(axis=0)
        comp.append(
            {
                "label": int(label),
                "point_count": int(len(cpts)),
                "point_ratio": round(float(len(cpts) / len(pts)), 6),
                "centroid": [round(float(v), 6) for v in cpts.mean(axis=0).tolist()],
                "bbox_extent": [round(float(v), 6) for v in extent.tolist()],
            }
        )
    comp.sort(key=lambda item: item["point_count"], reverse=True)
    distances: list[float] = []
    for i in range(min(len(comp), 8)):
        ci = np.asarray(comp[i]["centroid"], dtype=float)
        for j in range(i + 1, min(len(comp), 8)):
            cj = np.asarray(comp[j]["centroid"], dtype=float)
            distances.append(float(np.linalg.norm(ci - cj)))
    return {
        "path": str(path),
        "voxel_size_m": voxel_size,
        "component_count": int(count),
        "components_top20": comp[:20],
        "largest_component_ratio": comp[0]["point_ratio"] if comp else None,
        "centroid_distance_min_top8_m": round(float(min(distances)), 6) if distances else None,
        "centroid_distance_max_top8_m": round(float(max(distances)), 6) if distances else None,
    }


def session_path(session_id: str) -> Path:
    return DATA_ROOT / "uploads" / session_id / "session.json"


def processed_path(session_id: str, rel: str = "point_cloud.ply") -> Path:
    return DATA_ROOT / "processed" / session_id / rel


def extract_nodeodm_uuid(session: dict[str, Any] | None) -> str | None:
    if not isinstance(session, dict):
        return None
    return session.get("nodeodm_task_uuid")


def find_options(task_dir: Path) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for candidate in [
        "options.json",
        "opensfm/config.yaml",
        "opensfm/config.yml",
        "images.json",
        "log.json",
    ]:
        path = task_dir / candidate
        if not path.exists():
            continue
        found[candidate] = {"path": str(path), "size_bytes": path.stat().st_size, "sha256": sha256(path)}
        if path.suffix == ".json":
            try:
                found[candidate]["content"] = read_json(path)
            except Exception as exc:
                found[candidate]["read_error"] = str(exc)
        else:
            try:
                found[candidate]["content_text_head"] = path.read_text(encoding="utf-8", errors="replace")[:8000]
            except Exception as exc:
                found[candidate]["read_error"] = str(exc)
    return found


def manifest_key(dataset: str, role: str) -> str:
    return f"{dataset}_{role}"


def manifest_options(manifest_entry: dict[str, Any] | None) -> dict[str, Any]:
    if not manifest_entry:
        return {}
    configs = manifest_entry.get("configs") or {}
    found: dict[str, Any] = {}
    for rel, content in configs.items():
        found[rel] = {"path": str(Path(manifest_entry.get("task_dir", "")) / rel), "content": content}
    return found


def flatten_options(options: Any) -> dict[str, Any]:
    if isinstance(options, dict):
        if "options" in options and isinstance(options["options"], list):
            out = {}
            for item in options["options"]:
                if isinstance(item, dict) and "name" in item:
                    out[str(item["name"])] = item.get("value")
            return out
        return {str(k): v for k, v in options.items() if not isinstance(v, (dict, list))}
    if isinstance(options, list):
        out = {}
        for item in options:
            if isinstance(item, dict) and "name" in item:
                out[str(item["name"])] = item.get("value")
        return out
    return {}


def file_tree(task_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not task_dir.exists():
        return rows
    cloud_suffixes = {".ply", ".laz", ".las", ".pcd", ".csv", ".obj", ".json", ".yaml", ".yml", ".txt", ".log"}
    for path in sorted(task_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(task_dir).as_posix()
        item: dict[str, Any] = {
            "relative_path": rel,
            "size_bytes": path.stat().st_size,
            "modified_time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(path.stat().st_mtime)),
            "producer": infer_producer(rel),
            "consumer": infer_consumer(rel),
        }
        if path.suffix.lower() == ".ply":
            item["point_cloud_stats"] = cloud_stats(path)
        elif path.suffix.lower() in cloud_suffixes:
            item["sha256"] = sha256(path)
        rows.append(item)
    return rows


def infer_producer(rel: str) -> str:
    if rel.startswith("opensfm/"):
        return "OpenSfM"
    if rel.startswith("mvs/") or "odm_openmvs" in rel:
        return "OpenMVS/ODM dense reconstruction"
    if rel.startswith("odm_filterpoints/"):
        return "ODM filterpoints"
    if rel.startswith("odm_meshing/"):
        return "ODM meshing"
    if rel.startswith("odm_texturing/"):
        return "ODM texturing"
    if rel.endswith("point_cloud.ply") or "point_cloud" in rel:
        return "NodeODM export/download artifact"
    return "NodeODM pipeline"


def infer_consumer(rel: str) -> str:
    if rel.endswith("point_cloud.ply"):
        return "ForestVol backend download -> productive PDI preparation"
    if rel.startswith("opensfm/"):
        return "OpenMVS/ODM dense stages"
    if rel.startswith("mvs/"):
        return "ODM filterpoints/meshing/export"
    if rel.startswith("odm_filterpoints/"):
        return "ForestVol downloaded cloud or later ODM stages"
    return "Traceability/reference"


def compare_options(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    a_opts = flatten_options((a.get("options.json") or {}).get("content"))
    b_opts = flatten_options((b.get("options.json") or {}).get("content"))
    keys = sorted(set(a_opts) | set(b_opts))
    diff = {}
    for key in keys:
        if a_opts.get(key) != b_opts.get(key):
            diff[key] = {"benchmark": a_opts.get(key), "production": b_opts.get(key)}
    dense = {key: diff[key] for key in diff if key in DENSE_OPTION_KEYS or "pc" in key or "depth" in key or "mesh" in key or "feature" in key}
    return {
        "all_option_diff": diff,
        "dense_reconstruction_option_diff": dense,
        "benchmark_options": a_opts,
        "production_options": b_opts,
    }


def plot_cloud_pair(dataset: str, benchmark_raw: Path, production_raw: Path, benchmark_pdi: Path | None) -> None:
    fig = plt.figure(figsize=(11, 8))
    ax = fig.add_subplot(111, projection="3d")
    for path, color, label in [
        (benchmark_raw, "#2f80ed", "benchmark raw point_cloud.ply"),
        (production_raw, "#eb5757", "production raw point_cloud.ply"),
        (benchmark_pdi, "#27ae60", "benchmark PDI poisson_input_cloud.ply"),
    ]:
        if path is None or not path.exists():
            continue
        cloud = load_cloud(path)
        if cloud is None:
            continue
        pts = sample_points(points(cloud), 6000)
        ax.scatter(pts[:, 0], pts[:, 1], pts[:, 2], s=1, alpha=0.28, c=color, label=label)
    ax.set_title(f"{dataset}: NodeODM/benchmark cloud trace")
    ax.set_xlabel("X m")
    ax.set_ylabel("Y m")
    ax.set_zlabel("Z m")
    ax.legend(markerscale=5)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / f"{dataset}_artifact_cloud_overlay.png", dpi=180)
    plt.close(fig)


def write_graph(report: dict[str, Any]) -> None:
    lines = [
        "# NodeODM Artifact Graph",
        "",
        "```mermaid",
        "flowchart TD",
        '  A["Input images"] --> B["OpenSfM: features, tracks, reconstruction.json"]',
        '  B --> C["OpenMVS / MVS dense reconstruction"]',
        '  C --> D["odm_filterpoints / filtered point cloud"]',
        '  D --> E["NodeODM exported point_cloud.ply"]',
        '  E --> F["ForestVol backend data/processed/<session>/point_cloud.ply"]',
        '  F --> G["Productive cleanup + DBSCAN"]',
        '  G --> H["PDI input"]',
        '  F --> I["Benchmark legacy mesh diagnostics"]',
        '  I --> J["surface_closure_diagnostics*/poisson_input_cloud.ply"]',
        "```",
        "",
    ]
    for dataset, data in report["datasets"].items():
        lines.extend([f"## {dataset}", ""])
        for role, run in data["runs"].items():
            lines.extend(
                [
                    f"### {role}",
                    "",
                    f"- session: `{run['session_id']}`",
                    f"- nodeodm uuid: `{run.get('nodeodm_task_uuid')}`",
                    f"- backend point cloud: `{run['backend_point_cloud']['path']}`",
                    f"- backend point cloud sha256: `{run['backend_point_cloud'].get('sha256')}`",
                    f"- backend point count: `{run['backend_point_cloud'].get('point_count')}`",
                    "",
                ]
            )
            if run.get("benchmark_pdi_cloud"):
                lines.extend(
                    [
                        f"- benchmark PDI cloud: `{run['benchmark_pdi_cloud']['path']}`",
                        f"- benchmark PDI sha256: `{run['benchmark_pdi_cloud'].get('sha256')}`",
                        f"- benchmark PDI point count: `{run['benchmark_pdi_cloud'].get('point_count')}`",
                        "",
                    ]
                )
    (OUTPUT_DIR / "artifact_graph.md").write_text("\n".join(lines), encoding="utf-8")


def write_report(report: dict[str, Any], diffs: dict[str, Any]) -> None:
    lines = [
        "# Reconstruction Trace Report",
        "",
        "Restricciones: no se modifico PDI, DBSCAN, NodeODM, OpenSfM ni parametros productivos. Esta fase solo inspecciona artefactos existentes.",
        "",
        "## Conclusion unica",
        "",
        report["root_cause"]["classification"],
        "",
        report["root_cause"]["evidence_summary"],
        "",
        "## Evidencia por dataset",
        "",
    ]
    for dataset, data in report["datasets"].items():
        eq = data["same_file_answer"]
        diff = diffs[dataset]
        lines.extend(
            [
                f"### {dataset}",
                "",
                f"- ¿Benchmark usa exactamente el mismo archivo que produccion?: **{eq['answer']}**.",
                f"- Benchmark NodeODM UUID: `{data['runs']['benchmark']['nodeodm_task_uuid']}`.",
                f"- Produccion NodeODM UUID: `{data['runs']['production']['nodeodm_task_uuid']}`.",
                f"- Hash raw benchmark: `{eq['benchmark_raw_sha256']}`.",
                f"- Hash raw produccion: `{eq['production_raw_sha256']}`.",
                f"- Hash nube benchmark PDI: `{eq.get('benchmark_pdi_sha256')}`.",
                f"- Diferencias de parametros densos NodeODM: `{len(diff['parameter_diff']['dense_reconstruction_option_diff'])}`.",
                f"- Comparacion raw benchmark vs raw produccion Chamfer: `{diff['raw_cloud_comparison']['chamfer_distance_m']}` m; Hausdorff: `{diff['raw_cloud_comparison']['hausdorff_distance_m']}` m.",
                f"- Fragmentacion RAW benchmark: `{diff['raw_fragmentation']['benchmark']['component_count']}` componentes; produccion: `{diff['raw_fragmentation']['production']['component_count']}` componentes.",
                "",
            ]
        )
        if data["runs"]["benchmark"].get("benchmark_pdi_cloud"):
            c = diff["benchmark_raw_vs_benchmark_pdi_cloud"]
            lines.extend(
                [
                    f"- Raw benchmark vs nube benchmark realmente usada por PDI: Chamfer `{c['chamfer_distance_m']}` m; overlap raw->PDI `{c['a_overlap_at_0_25m']}`.",
                    "",
                ]
            )
    lines.extend(
        [
            "## Archivos generados",
            "",
            "- `reconstruction_trace.json`",
            "- `reconstruction_diff.json`",
            "- `nodeodm_parameter_diff.json`",
            "- `pointcloud_hashes.json`",
            "- `artifact_graph.md`",
            "- `reconstruction_report.md`",
        ]
    )
    (OUTPUT_DIR / "reconstruction_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    trace: dict[str, Any] = {
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "root": str(ROOT),
        "data_root": str(DATA_ROOT),
        "nodeodm_root": str(NODEODM_ROOT),
        "nodeodm_manifest_path": str(NODEODM_MANIFEST_PATH),
        "datasets": {},
    }
    nodeodm_manifest = read_json(NODEODM_MANIFEST_PATH) or {}
    hashes: dict[str, Any] = {}
    diffs: dict[str, Any] = {}
    parameter_diffs: dict[str, Any] = {}
    csv_rows: list[dict[str, Any]] = []

    by_dataset: dict[str, dict[str, RunRef]] = {}
    for run in RUNS:
        by_dataset.setdefault(run.dataset, {})[run.role] = run

    for dataset, refs in by_dataset.items():
        trace["datasets"][dataset] = {"runs": {}}
        hashes[dataset] = {}
        for role, ref in refs.items():
            session = read_json(session_path(ref.session_id))
            uuid = extract_nodeodm_uuid(session)
            task_dir = NODEODM_ROOT / uuid if uuid else Path("__missing__")
            manifest_entry = nodeodm_manifest.get(manifest_key(ref.dataset, ref.role), {})
            backend_cloud = processed_path(ref.session_id)
            bench_pdi = processed_path(ref.session_id, ref.benchmark_pdi_cloud_rel) if ref.benchmark_pdi_cloud_rel else None
            options = manifest_options(manifest_entry) or find_options(task_dir)
            run_data = {
                "session_id": ref.session_id,
                "session_json_path": str(session_path(ref.session_id)),
                "session": session,
                "nodeodm_task_uuid": uuid,
                "nodeodm_task_dir": str(task_dir),
                "nodeodm_task_dir_exists": bool(manifest_entry.get("exists")) or task_dir.exists(),
                "options_and_configs": options,
                "artifact_tree": manifest_entry.get("artifact_tree") or file_tree(task_dir),
                "artifact_file_count": manifest_entry.get("file_count"),
                "backend_point_cloud": cloud_stats(backend_cloud),
            }
            if bench_pdi is not None:
                run_data["benchmark_pdi_cloud"] = cloud_stats(bench_pdi)
            trace["datasets"][dataset]["runs"][role] = run_data
            hashes[dataset][role] = {
                "session_id": ref.session_id,
                "nodeodm_task_uuid": uuid,
                "backend_point_cloud": run_data["backend_point_cloud"],
            }
            if bench_pdi is not None:
                hashes[dataset][role]["benchmark_pdi_cloud"] = run_data["benchmark_pdi_cloud"]
            csv_rows.append(
                {
                    "dataset": dataset,
                    "role": role,
                    "session_id": ref.session_id,
                    "nodeodm_task_uuid": uuid,
                    "cloud_kind": "backend_point_cloud",
                    "path": str(backend_cloud),
                    "sha256": run_data["backend_point_cloud"].get("sha256"),
                    "size_bytes": run_data["backend_point_cloud"].get("size_bytes"),
                    "point_count": run_data["backend_point_cloud"].get("point_count"),
                    "bbox_extent": run_data["backend_point_cloud"].get("bbox_extent"),
                }
            )
            if bench_pdi is not None:
                csv_rows.append(
                    {
                        "dataset": dataset,
                        "role": role,
                        "session_id": ref.session_id,
                        "nodeodm_task_uuid": uuid,
                        "cloud_kind": "benchmark_pdi_cloud",
                        "path": str(bench_pdi),
                        "sha256": run_data["benchmark_pdi_cloud"].get("sha256"),
                        "size_bytes": run_data["benchmark_pdi_cloud"].get("size_bytes"),
                        "point_count": run_data["benchmark_pdi_cloud"].get("point_count"),
                        "bbox_extent": run_data["benchmark_pdi_cloud"].get("bbox_extent"),
                    }
                )

        bench = trace["datasets"][dataset]["runs"]["benchmark"]
        prod = trace["datasets"][dataset]["runs"]["production"]
        bench_raw = Path(bench["backend_point_cloud"]["path"])
        prod_raw = Path(prod["backend_point_cloud"]["path"])
        bench_pdi = Path(bench["benchmark_pdi_cloud"]["path"]) if bench.get("benchmark_pdi_cloud") else None
        param_diff = compare_options(bench["options_and_configs"], prod["options_and_configs"])
        parameter_diffs[dataset] = param_diff
        same_file_answer = {
            "answer": "NO",
            "benchmark_raw_path": str(bench_raw),
            "production_raw_path": str(prod_raw),
            "benchmark_raw_sha256": bench["backend_point_cloud"].get("sha256"),
            "production_raw_sha256": prod["backend_point_cloud"].get("sha256"),
            "benchmark_raw_point_count": bench["backend_point_cloud"].get("point_count"),
            "production_raw_point_count": prod["backend_point_cloud"].get("point_count"),
            "benchmark_nodeodm_uuid": bench.get("nodeodm_task_uuid"),
            "production_nodeodm_uuid": prod.get("nodeodm_task_uuid"),
        }
        if bench_pdi is not None:
            same_file_answer.update(
                {
                    "benchmark_pdi_path": str(bench_pdi),
                    "benchmark_pdi_sha256": bench["benchmark_pdi_cloud"].get("sha256"),
                    "benchmark_pdi_point_count": bench["benchmark_pdi_cloud"].get("point_count"),
                }
            )
        if bench["backend_point_cloud"].get("sha256") == prod["backend_point_cloud"].get("sha256"):
            same_file_answer["answer"] = "YES_RAW_POINT_CLOUD_MATCHES"
        if bench_pdi is not None and bench["benchmark_pdi_cloud"].get("sha256") == prod["backend_point_cloud"].get("sha256"):
            same_file_answer["answer"] = "YES_BENCHMARK_PDI_MATCHES_PRODUCTION_RAW"
        trace["datasets"][dataset]["same_file_answer"] = same_file_answer
        raw_cmp = cloud_compare(bench_raw, prod_raw)
        pdi_cmp = cloud_compare(bench_raw, bench_pdi) if bench_pdi is not None else {"available": False}
        prod_vs_bench_pdi = cloud_compare(prod_raw, bench_pdi) if bench_pdi is not None else {"available": False}
        diffs[dataset] = {
            "same_file_answer": same_file_answer,
            "parameter_diff": param_diff,
            "raw_cloud_comparison": raw_cmp,
            "benchmark_raw_vs_benchmark_pdi_cloud": pdi_cmp,
            "production_raw_vs_benchmark_pdi_cloud": prod_vs_bench_pdi,
            "raw_fragmentation": {
                "benchmark": connected_components(bench_raw),
                "production": connected_components(prod_raw),
            },
        }
        plot_cloud_pair(dataset, bench_raw, prod_raw, bench_pdi)

    classifications = []
    evidence = []
    for dataset, data in trace["datasets"].items():
        same = data["same_file_answer"]
        param_diff = parameter_diffs[dataset]
        if same["answer"] == "NO":
            classifications.append("A")
            evidence.append(
                f"{dataset}: benchmark/producion usan archivos o UUIDs distintos; raw hashes {same['benchmark_raw_sha256']} vs {same['production_raw_sha256']}; "
                f"benchmark PDI hash {same.get('benchmark_pdi_sha256')}."
            )
        elif param_diff["dense_reconstruction_option_diff"]:
            classifications.append("B")
            evidence.append(f"{dataset}: mismo archivo raw, pero opciones densas difieren.")
        else:
            classifications.append("C")
            evidence.append(f"{dataset}: mismo archivo/opciones no demostradas como distintas; posible ejecucion densa no deterministica.")
    final_class = "A) El benchmark y produccion estan usando archivos distintos."
    if all(c == "B" for c in classifications):
        final_class = "B) Estan usando exactamente el mismo archivo pero NodeODM fue ejecutado con distinta configuracion."
    elif all(c == "C" for c in classifications):
        final_class = "C) La reconstruccion densa produjo otra nube usando las mismas imagenes."
    elif not all(c == "A" for c in classifications):
        final_class = "D) Causa mixta demostrable entre datasets."
    trace["root_cause"] = {
        "classification": final_class,
        "evidence_summary": " ".join(evidence),
    }

    with (OUTPUT_DIR / "pointcloud_hashes.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=sorted({k for row in csv_rows for k in row}))
        writer.writeheader()
        writer.writerows(csv_rows)
    (OUTPUT_DIR / "reconstruction_trace.json").write_text(json.dumps(jsonable(trace), indent=2), encoding="utf-8")
    (OUTPUT_DIR / "reconstruction_diff.json").write_text(json.dumps(jsonable(diffs), indent=2), encoding="utf-8")
    (OUTPUT_DIR / "nodeodm_parameter_diff.json").write_text(json.dumps(jsonable(parameter_diffs), indent=2), encoding="utf-8")
    (OUTPUT_DIR / "pointcloud_hashes.json").write_text(json.dumps(jsonable(hashes), indent=2), encoding="utf-8")
    write_graph(trace)
    write_report(trace, diffs)
    print(json.dumps({"output_dir": str(OUTPUT_DIR), "root_cause": trace["root_cause"]}, indent=2))


if __name__ == "__main__":
    main()
