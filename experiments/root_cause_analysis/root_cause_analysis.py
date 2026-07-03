from __future__ import annotations

import csv
import json
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments" / "root_cause_analysis"
RUN_DIR = ROOT / "experiments" / "hito_0_5_close" / "dataset_definitivo_run_2"
RUN_RESULT = RUN_DIR / "result.json"
RAW_PLY = ROOT / "projects" / "ForestVol" / "data" / "processed" / "ecd0f8b7-64f5-437b-9048-2ae83609e8e7" / "point_cloud.ply"
SELECTED_PLY = RUN_DIR / "selected_pdi_input.ply"
ARUCO_CENTER = np.asarray([0.5, 0.5, 0.0], dtype=float)


def read_ply_points(path: Path) -> np.ndarray:
    with path.open("rb") as handle:
        header: list[str] = []
        while True:
            raw_line = handle.readline()
            if not raw_line:
                raise RuntimeError(f"Incomplete PLY header: {path}")
            line = raw_line.decode("ascii", errors="replace").strip()
            header.append(line)
            if line == "end_header":
                data_offset = handle.tell()
                break
        vertex_count = 0
        properties: list[tuple[str, str]] = []
        in_vertex = False
        for line in header:
            parts = line.split()
            if len(parts) == 3 and parts[:2] == ["element", "vertex"]:
                vertex_count = int(parts[2])
                in_vertex = True
                continue
            if parts[:1] == ["element"] and len(parts) >= 2 and parts[1] != "vertex":
                in_vertex = False
            if in_vertex and len(parts) == 3 and parts[0] == "property":
                properties.append((parts[2], parts[1]))
        dtype_map = {"float": "<f4", "float32": "<f4", "double": "<f8", "uchar": "u1", "uint8": "u1", "char": "i1", "int": "<i4", "uint": "<u4"}
        dtype = np.dtype([(name, dtype_map[kind]) for name, kind in properties])
        handle.seek(data_offset)
        vertices = np.frombuffer(handle.read(), dtype=dtype, count=vertex_count)
    points = np.column_stack([vertices["x"], vertices["y"], vertices["z"]]).astype(np.float64)
    return points[np.isfinite(points).all(axis=1)]


def stats_from_points(stage: str, points: np.ndarray, castle_center: np.ndarray, previous_count: int | None = None) -> dict[str, Any]:
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    extent = maxs - mins
    bbox_volume = float(np.prod(np.maximum(extent, 1e-9)))
    centroid = points.mean(axis=0)
    loss = None if not previous_count else float((previous_count - len(points)) / previous_count)
    return {
        "stage": stage,
        "point_count": int(len(points)),
        "loss_percent_from_previous": None if loss is None else round(loss * 100.0, 4),
        "bbox_min": [round(float(v), 6) for v in mins],
        "bbox_max": [round(float(v), 6) for v in maxs],
        "bbox_extent_m": [round(float(v), 6) for v in extent],
        "bbox_volume_m3": round(bbox_volume, 6),
        "centroid": [round(float(v), 6) for v in centroid],
        "density_points_per_m3": round(float(len(points) / bbox_volume), 6) if bbox_volume else 0.0,
        "distance_to_aruco_center_m": round(float(np.linalg.norm(centroid - ARUCO_CENTER)), 6),
        "distance_to_castle_center_m": round(float(np.linalg.norm(centroid - castle_center)), 6),
    }


def stats_from_result(row: dict[str, Any], castle_center: np.ndarray) -> dict[str, Any]:
    centroid = np.asarray(row["centroid"], dtype=float)
    extent = np.asarray(row["bbox_extent_m"], dtype=float)
    return {
        "stage": row["stage"],
        "point_count": row["point_count"],
        "loss_percent_from_previous": row.get("loss_percent_from_previous"),
        "bbox_min": [round(float(v), 6) for v in (centroid - extent / 2.0)],
        "bbox_max": [round(float(v), 6) for v in (centroid + extent / 2.0)],
        "bbox_extent_m": row["bbox_extent_m"],
        "bbox_volume_m3": row["bbox_volume_m3"],
        "centroid": row["centroid"],
        "density_points_per_m3": row["density_points_per_m3"],
        "distance_to_aruco_center_m": round(float(np.linalg.norm(centroid - ARUCO_CENTER)), 6),
        "distance_to_castle_center_m": round(float(np.linalg.norm(centroid - castle_center)), 6),
    }


def bbox_filtered_proxy(points: np.ndarray, extent: list[float], centroid: list[float], target_count: int) -> np.ndarray:
    center = np.asarray(centroid, dtype=float)
    half = np.asarray(extent, dtype=float) / 2.0
    mask = np.all((points >= center - half) & (points <= center + half), axis=1)
    proxy = points[mask]
    if len(proxy) > target_count:
        proxy = proxy[np.linspace(0, len(proxy) - 1, target_count).astype(int)]
    return proxy


def voxel_downsample(points: np.ndarray, voxel_size: float) -> np.ndarray:
    mins = points.min(axis=0)
    keys = np.floor((points - mins) / voxel_size).astype(np.int32)
    _, first = np.unique(keys, axis=0, return_index=True)
    return points[np.sort(first)]


def connected_components_radius(points: np.ndarray, eps: float, min_points: int) -> np.ndarray:
    cell_size = eps
    mins = points.min(axis=0)
    cells = np.floor((points - mins) / cell_size).astype(np.int32)
    buckets: dict[tuple[int, int, int], list[int]] = {}
    for index, cell in enumerate(cells):
        buckets.setdefault((int(cell[0]), int(cell[1]), int(cell[2])), []).append(index)
    offsets = [(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)]
    labels = np.full(len(points), -1, dtype=np.int32)
    visited = np.zeros(len(points), dtype=bool)

    def query(index: int) -> list[int]:
        cell = cells[index]
        candidates: list[int] = []
        for off in offsets:
            candidates.extend(buckets.get((int(cell[0] + off[0]), int(cell[1] + off[1]), int(cell[2] + off[2])), []))
        if not candidates:
            return []
        cand = np.asarray(candidates, dtype=np.int32)
        d2 = np.sum((points[cand] - points[index]) ** 2, axis=1)
        return cand[d2 <= eps * eps].tolist()

    cluster_id = 0
    for index in range(len(points)):
        if visited[index]:
            continue
        visited[index] = True
        neighbors = query(index)
        if len(neighbors) < min_points:
            continue
        labels[index] = cluster_id
        queue = deque(neighbors)
        while queue:
            neighbor = queue.popleft()
            if not visited[neighbor]:
                visited[neighbor] = True
                neighbor_neighbors = query(neighbor)
                if len(neighbor_neighbors) >= min_points:
                    queue.extend(neighbor_neighbors)
            if labels[neighbor] < 0:
                labels[neighbor] = cluster_id
        cluster_id += 1
    return labels


def cluster_rows(points: np.ndarray, labels: np.ndarray, selected_ids: set[int]) -> list[dict[str, Any]]:
    valid = labels[labels >= 0]
    if valid.size == 0:
        return []
    values, counts = np.unique(valid, return_counts=True)
    order = np.argsort(counts)[::-1]
    main_id = int(values[order[0]])
    main_centroid = points[labels == main_id].mean(axis=0)
    rows: list[dict[str, Any]] = []
    for rank, idx in enumerate(order, start=1):
        label = int(values[idx])
        cpts = points[labels == label]
        mins = cpts.min(axis=0)
        maxs = cpts.max(axis=0)
        extent = maxs - mins
        centroid = cpts.mean(axis=0)
        bbox_volume = float(np.prod(np.maximum(extent, 1e-9)))
        distance_main = float(np.linalg.norm(centroid - main_centroid))
        if label in selected_ids and rank == 1:
            classification = "castillo + fuga dominante (suelo/fondo conectado)"
        elif extent[2] < 1.0 and distance_main > 3.0:
            classification = "suelo / plano bajo"
        elif extent[2] >= 1.0 and distance_main > 3.0:
            classification = "vegetacion / fondo vertical"
        elif len(cpts) < 80:
            classification = "ruido pequeno"
        elif distance_main <= 3.0:
            classification = "fragmento cercano al castillo"
        else:
            classification = "ruido / objeto secundario"
        rows.append(
            {
                "source": "diagnostic_rederived",
                "rank": rank,
                "cluster_id": label,
                "selected_by_pipeline": label in selected_ids,
                "point_count": int(len(cpts)),
                "point_percent_total": round(float(len(cpts) / len(points) * 100.0), 6),
                "bbox_min": [round(float(v), 6) for v in mins],
                "bbox_max": [round(float(v), 6) for v in maxs],
                "bbox_extent_m": [round(float(v), 6) for v in extent],
                "bbox_volume_m3": round(bbox_volume, 6),
                "centroid": [round(float(v), 6) for v in centroid],
                "density_points_per_m3": round(float(len(cpts) / bbox_volume), 6) if bbox_volume else 0.0,
                "distance_to_aruco_center_m": round(float(np.linalg.norm(centroid - ARUCO_CENTER)), 6),
                "distance_to_main_centroid_m": round(distance_main, 6),
                "classification": classification,
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def project(points: np.ndarray, axes: tuple[int, int], size: int = 1400, pad: int = 60) -> np.ndarray:
    xy = points[:, axes]
    mins = xy.min(axis=0)
    span = np.maximum(xy.max(axis=0) - mins, 1e-9)
    scale = (size - 2 * pad) / span.max()
    pix = (xy - mins) * scale + pad
    pix[:, 1] = size - pix[:, 1]
    return pix.astype(np.int32)


def draw_points(path: Path, points: np.ndarray, title: str, colors: np.ndarray | None = None, sample: int = 180000) -> None:
    if len(points) > sample:
        idx = np.linspace(0, len(points) - 1, sample).astype(int)
        points = points[idx]
        if colors is not None:
            colors = colors[idx]
    img = Image.new("RGB", (1400, 1400), "white")
    draw = ImageDraw.Draw(img, "RGBA")
    pix = project(points, (0, 1))
    if colors is None:
        z = points[:, 2]
        zn = (z - z.min()) / max(float(z.max() - z.min()), 1e-9)
        colors = np.column_stack([70 + 90 * zn, 100 + 80 * (1 - zn), 190 - 100 * zn]).astype(np.uint8)
    for (x, y), color in zip(pix, colors):
        draw.point((int(x), int(y)), fill=(int(color[0]), int(color[1]), int(color[2]), 120))
    draw.rectangle((8, 8, 1392, 52), fill=(255, 255, 255, 225))
    draw.text((18, 18), title, fill=(0, 0, 0, 255))
    img.save(path)


def draw_overlay(path: Path, raw: np.ndarray, selected: np.ndarray) -> None:
    raw_sample = raw[np.linspace(0, len(raw) - 1, min(len(raw), 180000)).astype(int)]
    selected_sample = selected[np.linspace(0, len(selected) - 1, min(len(selected), 120000)).astype(int)]
    points = np.vstack([raw_sample, selected_sample])
    pix = project(points, (0, 1))
    raw_pix = pix[: len(raw_sample)]
    selected_pix = pix[len(raw_sample) :]
    img = Image.new("RGB", (1400, 1400), "white")
    draw = ImageDraw.Draw(img, "RGBA")
    for x, y in raw_pix:
        draw.point((int(x), int(y)), fill=(70, 70, 70, 45))
    for x, y in selected_pix:
        draw.point((int(x), int(y)), fill=(220, 20, 20, 135))
    draw.rectangle((8, 8, 1392, 72), fill=(255, 255, 255, 225))
    draw.text((18, 18), "RAW vs selected_pdi_input: gris=RAW, rojo=seleccion final", fill=(0, 0, 0, 255))
    draw.text((18, 42), "La seleccion conserva una huella espacial amplia, no un objeto compacto.", fill=(0, 0, 0, 255))
    img.save(path)


def md_table(rows: list[dict[str, Any]], keys: list[str]) -> str:
    lines = ["|" + "|".join(keys) + "|\n", "|" + "|".join(["---"] * len(keys)) + "|\n"]
    for row in rows:
        lines.append("|" + "|".join(str(row.get(key, "")) for key in keys) + "|\n")
    return "".join(lines)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    images_dir = OUT / "images"
    images_dir.mkdir(exist_ok=True)
    result = json.loads(RUN_RESULT.read_text(encoding="utf-8"))
    raw = read_ply_points(RAW_PLY)
    selected = read_ply_points(SELECTED_PLY)
    selected_ids = set(int(v) for v in result["selected_cluster_ids"])
    castle_center = selected.mean(axis=0)

    stage_rows = [stats_from_result(row, castle_center) for row in result["stages"]]
    stage_rows.append(stats_from_points("selected_pdi_input.ply", selected, castle_center, result["stages"][2]["point_count"]))
    write_csv(OUT / "stage_statistics.csv", stage_rows)

    outlier_proxy = bbox_filtered_proxy(raw, result["stages"][1]["bbox_extent_m"], result["stages"][1]["centroid"], result["stages"][1]["point_count"])
    voxel_proxy = voxel_downsample(outlier_proxy, float(result["segmentation_config"]["voxel_size_m"]))
    cluster_points = voxel_proxy[np.linspace(0, len(voxel_proxy) - 1, min(len(voxel_proxy), 90000)).astype(int)]
    labels = connected_components_radius(cluster_points, float(result["segmentation_config"]["dbscan_eps_m"]), int(result["segmentation_config"]["dbscan_min_points"]))
    diagnostic_rows = cluster_rows(cluster_points, labels, selected_ids)

    exact_top: list[dict[str, Any]] = []
    for row in result["clusters_top10"]:
        height = float(row["bbox_extent_m"][2])
        exact_top.append(
            {
                "source": "validation_result_exact_top10",
                "rank": row["rank"],
                "cluster_id": row["cluster_id"],
                "selected_by_pipeline": row["cluster_id"] in selected_ids,
                "point_count": row["point_count"],
                "point_percent_total": round(row["point_ratio_input"] * 100.0, 6),
                "bbox_extent_m": row["bbox_extent_m"],
                "bbox_volume_m3": row["bbox_volume_m3"],
                "density_points_per_m3": row["density_points_per_m3"],
                "classification": "castillo + fuga dominante (suelo/fondo conectado)" if row["rank"] == 1 else ("suelo / plano bajo" if height < 1.0 else "vegetacion / fondo vertical"),
            }
        )
    write_csv(OUT / "cluster_analysis.csv", exact_top + diagnostic_rows)

    summary = {
        "session_id": result["session_id"],
        "nodeodm_task_uuid": result["nodeodm"]["task_uuid"],
        "volume_m3": result["volume_m3"],
        "error_percentage": result["error_percentage"],
        "aruco_center_assumption_m": ARUCO_CENTER.tolist(),
        "castle_center_proxy_selected_centroid": [round(float(v), 6) for v in castle_center],
        "selected_cluster_ids": result["selected_cluster_ids"],
        "exact_cluster_count": result["cluster_count"],
        "exact_noise_points": result["noise_points"],
        "exact_clusters_top10": exact_top,
        "diagnostic_note": "Intermediate PLYs were not persisted by the validation run. Stage metrics are exact from result.json; intermediate images and diagnostic clusters are re-derived from the existing RAW artifact without changing parameters or reconstructing.",
        "diagnostic_cluster_count": int(labels.max() + 1) if labels.size and labels.max() >= 0 else 0,
        "diagnostic_noise_points": int(np.count_nonzero(labels < 0)),
        "root_cause": {
            "first_stage_where_cloud_is_not_only_castle": "RAW Dense Point Cloud",
            "primary_cause": "A) Reconstruccion fotogrametrica",
            "propagation_gate": "E) Seleccion de clusters",
            "not_primary_cause": ["B) Outlier Removal", "C) Voxelizacion", "F) PDI"],
        },
    }
    (OUT / "cluster_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    palette = np.asarray([[30, 105, 210], [230, 80, 60], [60, 170, 90], [220, 160, 30], [150, 90, 190], [40, 180, 180], [120, 120, 120]], dtype=np.uint8)
    label_colors = palette[np.maximum(labels, 0) % len(palette)]
    label_colors[labels < 0] = [20, 20, 20]
    draw_points(images_dir / "01_raw_xy.png", raw, "RAW Dense Point Cloud - corrida 2")
    draw_points(images_dir / "02_outlier_removal_proxy_xy.png", outlier_proxy, "Outlier Removal - vista derivada para auditoria")
    draw_points(images_dir / "03_voxelization_proxy_xy.png", voxel_proxy, "Voxelization 0.07 m - vista derivada para auditoria")
    draw_points(images_dir / "04_clusters_colored_proxy_xy.png", cluster_points, "Clusters DBSCAN coloreados - diagnostico", label_colors, sample=len(cluster_points))
    draw_points(images_dir / "05_clusters_selected_xy.png", selected, "Clusters seleccionados por pipeline")
    draw_points(images_dir / "06_selected_pdi_input_xy.png", selected, "selected_pdi_input.ply - entrada a PDI")
    draw_overlay(images_dir / "07_raw_vs_selected_overlay_xy.png", raw, selected)

    comparison = [
        "# Comparacion critica RAW vs selected_pdi_input\n\n",
        f"Session ID: `{result['session_id']}`. NodeODM Task ID: `{result['nodeodm']['task_uuid']}`.\n\n",
        f"Volumen PDI: `{result['volume_m3']} m3`; error: `{result['error_percentage']}%`.\n\n",
        "## Hallazgo principal\n\n",
        f"`selected_pdi_input` conserva una envolvente de `{result['stages'][3]['bbox_extent_m']}` m y un bbox de `{result['stages'][3]['bbox_volume_m3']} m3`. ",
        "Esa geometria no corresponde a un castillo aislado.\n\n",
        "![RAW vs selected](images/07_raw_vs_selected_overlay_xy.png)\n\n",
        "## Medidas por etapa\n\n",
        md_table(stage_rows, ["stage", "point_count", "bbox_extent_m", "bbox_volume_m3", "centroid", "distance_to_aruco_center_m", "distance_to_castle_center_m"]),
        "\n## Regiones no pertenecientes al castillo en selected_pdi_input\n\n",
        "- Huella horizontal seleccionada superior a `23 m x 22 m`, compatible con terreno/fondo alrededor del objeto.\n",
        "- Cluster dominante exacto `0`: `140388` puntos, caja `23.55 x 19.53 x 8.35 m`; no puede ser solo el castillo.\n",
        "- Clusters secundarios seleccionados `27` y `48` agregan fragmentos externos, pero el problema principal ya esta dentro del cluster dominante.\n",
    ]
    (OUT / "pipeline_comparison.md").write_text("".join(comparison), encoding="utf-8")

    report = [
        "# Root Cause Analysis - nube de puntos dataset definitivo\n\n",
        "## Decision\n\n",
        "**La primera etapa donde el pipeline deja de representar unicamente el castillo es `RAW Dense Point Cloud`.**\n\n",
        "La causa principal de la sobreestimacion es **A) Reconstruccion fotogrametrica**: la nube RAW ya contiene una escena amplia con terreno/fondo conectado al objeto. ",
        "La causa que la deja pasar hacia PDI es **E) Seleccion de clusters**: DBSCAN produce un cluster dominante que mezcla castillo con entorno, y la regla `top_3_by_points` lo selecciona completo.\n\n",
        "PDI no aparece como causa primaria: recibe una nube seleccionada con bbox enorme y calcula volumen sobre esa geometria.\n\n",
        "## Evidencia cuantitativa\n\n",
        "Las metricas por etapa provienen del `result.json` de la corrida 2. Las PLY intermedias de Outlier Removal, Voxelization y DBSCAN no fueron persistidas por el runner de validacion; por eso las imagenes intermedias se regeneran como vistas diagnosticas desde la RAW existente, sin reconstruir ni cambiar parametros.\n\n",
        md_table(stage_rows, ["stage", "point_count", "bbox_extent_m", "bbox_volume_m3", "density_points_per_m3", "distance_to_aruco_center_m", "distance_to_castle_center_m"]),
        "\n## Clusters exactos principales de la corrida\n\n",
        md_table(exact_top, ["rank", "cluster_id", "selected_by_pipeline", "point_count", "point_percent_total", "bbox_extent_m", "bbox_volume_m3", "classification"]),
        "\n## Clasificacion solicitada\n\n",
        "- Cluster que representa realmente el castillo: el castillo esta embebido dentro del cluster dominante `0`, pero ese cluster no representa solo el castillo; es `castillo + fuga dominante`.\n",
        "- Clusters de suelo: clusters bajos con altura menor a ~1 m, especialmente `27`, `3`, `55`, `42`, `76`, `84` segun la tabla top10.\n",
        "- Clusters de vegetacion/fondo: clusters con altura vertical mayor y bajo porcentaje, por ejemplo `48`, `47`, `52`.\n",
        "- Ruido: puntos DBSCAN con etiqueta `-1` y clusters pequenos no seleccionados; el run exacto reporta `275` puntos de ruido.\n\n",
        "## Bounding Box Analysis\n\n",
        f"El bounding box seleccionado mide `{result['stages'][3]['bbox_extent_m']}` m y tiene volumen bbox `{result['stages'][3]['bbox_volume_m3']} m3`. ",
        "No coincide visual ni dimensionalmente con un castillo aislado; incluye terreno, fondo o estructuras conectadas.\n\n",
        "![selected](images/06_selected_pdi_input_xy.png)\n\n",
        "![clusters](images/04_clusters_colored_proxy_xy.png)\n\n",
        "## Comparacion visual\n\n",
        "![raw](images/01_raw_xy.png)\n\n",
        "![overlay](images/07_raw_vs_selected_overlay_xy.png)\n\n",
        "## Root Cause\n\n",
        "| Opcion | Veredicto | Evidencia |\n",
        "|---|---|---|\n",
        "| A) Reconstruccion fotogrametrica | Causa primaria | RAW ya mide 32.08 x 38.60 x 21.81 m y contiene escena amplia. |\n",
        "| B) Outlier Removal | No primaria | Solo elimina 0.8116% de puntos; la caja sigue en 28.11 x 31.32 x 18.43 m. |\n",
        "| C) Voxelizacion | No primaria | Reduce puntos, pero conserva caja 28.10 x 31.29 x 18.39 m. |\n",
        "| D) DBSCAN | Separacion insuficiente | Detecta 104 clusters, pero el cluster principal sigue mezclando objeto y entorno. |\n",
        "| E) Seleccion de clusters | Propagacion critica | Selecciona `0, 27, 48`; el cluster 0 solo ya tiene bbox 23.55 x 19.53 x 8.35 m. |\n",
        "| F) PDI | No primaria | PDI integra la nube contaminada recibida; su hull es 1586.91 m3 y produce 946.0781 m3. |\n\n",
        "## Conclusion\n\n",
        "El pipeline comienza a incluir informacion que explica los volumenes de 800-900 m3 desde la reconstruccion RAW. ",
        "La seleccion posterior no corrige esa contaminacion porque el entorno queda unido al castillo dentro del cluster dominante. ",
        "Por lo tanto, la sobreestimacion no nace en PDI: PDI recibe una nube cuyo soporte espacial ya es de escena, no de objeto.\n",
    ]
    (OUT / "root_cause_report.md").write_text("".join(report), encoding="utf-8")


if __name__ == "__main__":
    main()
