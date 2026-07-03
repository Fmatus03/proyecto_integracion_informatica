from __future__ import annotations

import csv
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d
from scipy.spatial import ConvexHull, cKDTree


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

RAW_CLOUD = ROOT / "projects/ForestVol/data/processed/971d6e25-8ff0-41d2-8784-c981dec7ccbf/point_cloud.ply"
FINAL_VOLUME_CLOUD = ROOT / "experiments/volume_input_audit/selected_volume_cloud.ply"
BRIDGE_METRICS = ROOT / "experiments/local_bridge_validation/bridge_metrics.json"
RAW_VS_VOXEL = ROOT / "experiments/raw_vs_voxel_connectivity_validation/voxel_sweep_metrics.json"
SCALE_FACTOR = 0.54611448

RADIUS_LOCAL_DENSITY_M = 0.20
CONTACT_CROP_RADIUS_M = 0.45
EPS_CONNECTIVITY_M = 0.35
NORMAL_RADIUS_M = 0.35
MAX_NN = 40


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def read_cloud(path: Path, scale: float | None = None) -> tuple[o3d.geometry.PointCloud, np.ndarray]:
    cloud = o3d.io.read_point_cloud(str(path))
    points = np.asarray(cloud.points, dtype=np.float64)
    if scale is not None:
        points = points * scale
        cloud.points = o3d.utility.Vector3dVector(points)
    return cloud, points


def write_cloud(path: Path, points: np.ndarray, colors: np.ndarray | None = None) -> None:
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(points)
    if colors is not None:
        cloud.colors = o3d.utility.Vector3dVector(colors)
    o3d.io.write_point_cloud(str(path), cloud, write_ascii=False)


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def usefulness(path: Path) -> str:
    name = path.name.lower()
    parts = str(path).lower()
    if name == "point_cloud.ply":
        return "Nube densa RAW/descargada; evidencia principal de geometria ya reconstruida."
    if "preliminary_mesh" in name or name.endswith(".obj") or "mesh" in name:
        return "Malla/superficie; util para distinguir nube densa vs reconstruccion de superficie."
    if "reconstruction" in name:
        return "Estructura SfM/camaras/poses/tracks; util para soporte por vista si corresponde a la misma corrida."
    if "camera" in name:
        return "Modelo o resultado de camaras; util para cobertura si corresponde a la misma corrida."
    if "features" in name or "matches" in name or "tracks" in name:
        return "Evidencia de matching; util para soporte fotogrametrico si esta completo."
    if "depth" in parts:
        return "Artefacto de profundidad/TSDF; util para contrastar densificacion o MVS."
    if "report" in name or name.endswith(".pdf"):
        return "Reporte ODM; util para parametros/resumen si disponible."
    if "ortho" in parts or "dsm" in parts or "dtm" in parts:
        return "Producto raster ODM; util para contexto, no para conectividad 3D puntual."
    if name.endswith(".json") or name.endswith(".csv"):
        return "Metadatos/metricas; util para trazabilidad si pertenece a la corrida auditada."
    return "Artefacto relacionado; utilidad dependiente de pertenencia a la corrida."


def inventory() -> list[dict]:
    roots = [ROOT / "projects/ForestVol", ROOT / "experiments"]
    patterns = {
        ".ply",
        ".obj",
        ".json",
        ".csv",
        ".pdf",
        ".nvm",
        ".tif",
        ".tiff",
        ".laz",
        ".las",
        ".pcd",
        ".exr",
        ".npz",
        ".npy",
        ".yaml",
        ".txt",
    }
    keywords = (
        "point_cloud",
        "mesh",
        "textured",
        "reconstruction",
        "camera",
        "shot",
        "track",
        "depth",
        "dsm",
        "dtm",
        "ortho",
        "report",
        "odm",
        "opensfm",
        "features",
        "matches",
        "cloud",
        "model",
    )
    rows: list[dict] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in patterns:
                continue
            s = str(path).lower()
            if not any(k in s for k in keywords):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            rows.append(
                {
                    "path": rel(path),
                    "bytes": stat.st_size,
                    "extension": path.suffix.lower(),
                    "last_modified_epoch": stat.st_mtime,
                    "candidate_latest_session": "971d6e25-8ff0-41d2-8784-c981dec7ccbf" in str(path),
                    "utility": usefulness(path),
                }
            )
    rows.sort(key=lambda r: (not r["candidate_latest_session"], r["path"]))
    return rows


def aabb(points: np.ndarray) -> dict:
    mn = points.min(axis=0)
    mx = points.max(axis=0)
    ext = mx - mn
    return {"min": mn.tolist(), "max": mx.tolist(), "extent_m": ext.tolist(), "volume_m3": float(np.prod(ext))}


def convex_hull_volume(points: np.ndarray) -> float | None:
    if len(points) < 4:
        return None
    try:
        return float(ConvexHull(points).volume)
    except Exception:
        return None


def local_counts(points: np.ndarray, radius: float) -> np.ndarray:
    tree = cKDTree(points)
    return np.asarray([len(x) - 1 for x in tree.query_ball_point(points, radius)], dtype=np.int32)


def knn_stats(points: np.ndarray, k: int = 20) -> tuple[np.ndarray, np.ndarray]:
    tree = cKDTree(points)
    kk = min(k + 1, len(points))
    dist, idx = tree.query(points, k=kk)
    if kk <= 1:
        return np.zeros(len(points)), np.zeros(len(points))
    kdist = dist[:, -1]
    neighbor_pts = points[idx[:, 1:]]
    centered = neighbor_pts - points[:, None, :]
    cov = np.einsum("nki,nkj->nij", centered, centered) / max(1, kk - 1)
    eig = np.linalg.eigvalsh(cov)
    eig = np.maximum(eig, 1e-12)
    curvature = eig[:, 0] / eig.sum(axis=1)
    return kdist, curvature


def normal_consistency(points: np.ndarray) -> np.ndarray:
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    cloud.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=NORMAL_RADIUS_M, max_nn=MAX_NN)
    )
    normals = np.asarray(cloud.normals)
    tree = cKDTree(points)
    idxs = tree.query_ball_point(points, NORMAL_RADIUS_M)
    out = np.zeros(len(points), dtype=np.float64)
    for i, idx in enumerate(idxs):
        if len(idx) <= 2:
            out[i] = np.nan
            continue
        dots = np.abs(normals[idx] @ normals[i])
        out[i] = float(np.nanmean(dots))
    return out


def pca_thickness(points: np.ndarray) -> dict:
    if len(points) < 4:
        return {"thickness_m": None, "rms_thickness_m": None, "planarity_ratio": None}
    centered = points - points.mean(axis=0)
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)
    normal = eigvecs[:, order[0]]
    signed = centered @ normal
    return {
        "thickness_m": float(np.percentile(signed, 95) - np.percentile(signed, 5)),
        "rms_thickness_m": float(np.sqrt(np.mean(signed**2))),
        "planarity_ratio": float(max(eigvals[order[0]], 0.0) / max(eigvals[order[-1]], 1e-12)),
        "normal": normal.tolist(),
    }


def load_regions() -> list[dict]:
    bridge = json.loads(BRIDGE_METRICS.read_text(encoding="utf-8"))
    raw_vox = json.loads(RAW_VS_VOXEL.read_text(encoding="utf-8")) if RAW_VS_VOXEL.exists() else {}
    endpoint_by_region = {}
    for r in raw_vox.get("regions", []):
        endpoint_by_region[int(r["region_id"])] = {
            "external_endpoint_xyz": r.get("external_endpoint"),
            "castle_endpoint_xyz": r.get("castle_endpoint"),
            "raw_connected": r.get("raw", {}).get("connected"),
            "raw_point_count": r.get("raw", {}).get("point_count"),
        }
    regions = []
    for r in bridge["regions"]:
        rid = int(r["region_id"])
        item = {
            "region_id": rid,
            "external_component_points_final": r.get("external_component_points"),
            "external_endpoint_index_final": r.get("external_endpoint"),
            "castle_endpoint_index_final": r.get("castle_endpoint"),
            "minimum_vertex_cut_size": r.get("minimum_vertex_cut_size"),
            "minimum_edge_cut_size": r.get("minimum_edge_cut_size"),
        }
        item.update(endpoint_by_region.get(rid, {}))
        regions.append(item)
    return regions


def summarize_array(x: np.ndarray) -> dict:
    x = np.asarray(x)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return {"count": 0}
    return {
        "count": int(len(x)),
        "mean": float(np.mean(x)),
        "median": float(np.median(x)),
        "std": float(np.std(x)),
        "p05": float(np.percentile(x, 5)),
        "p25": float(np.percentile(x, 25)),
        "p75": float(np.percentile(x, 75)),
        "p95": float(np.percentile(x, 95)),
    }


def color_by_metric(values: np.ndarray, cmap_name: str = "viridis") -> np.ndarray:
    values = np.asarray(values, dtype=float)
    finite = np.isfinite(values)
    scaled = np.zeros_like(values)
    if finite.any():
        lo, hi = np.percentile(values[finite], [2, 98])
        if hi <= lo:
            hi = lo + 1.0
        scaled[finite] = np.clip((values[finite] - lo) / (hi - lo), 0, 1)
    cmap = plt.get_cmap(cmap_name)
    return cmap(scaled)[:, :3]


def view_scatter(points: np.ndarray, colors: np.ndarray, path: Path, view: str, title: str) -> None:
    fig = plt.figure(figsize=(10, 8), dpi=160)
    sample = points
    c = colors
    limit = 70000 if view == "iso" else 100000
    if len(points) > limit:
        rng = np.random.default_rng(42)
        idx = rng.choice(len(points), size=limit, replace=False)
        sample = points[idx]
        c = colors[idx]
    if view == "iso":
        ax = fig.add_subplot(111, projection="3d")
        ax.scatter(sample[:, 0], sample[:, 1], sample[:, 2], c=c, s=0.25, linewidths=0)
        ax.view_init(elev=25, azim=-45)
        ax.set_xlabel("X m")
        ax.set_ylabel("Y m")
        ax.set_zlabel("Z m")
    else:
        axes = {"front": (0, 2), "side": (1, 2), "top": (0, 1)}
        a, b = axes[view]
        ax = fig.add_subplot(111)
        ax.scatter(sample[:, a], sample[:, b], c=c, s=0.35, linewidths=0)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel(["X m", "Y m", "Z m"][a])
        ax.set_ylabel(["X m", "Y m", "Z m"][b])
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def save_hist(values_by_label: dict[str, np.ndarray], path: Path, title: str, xlabel: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
    for label, values in values_by_label.items():
        values = np.asarray(values)
        values = values[np.isfinite(values)]
        if len(values):
            ax.hist(values, bins=45, alpha=0.55, density=True, label=label)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("densidad")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def classification_table(metrics: dict) -> list[tuple[str, str, str]]:
    regions = metrics["regions"]
    raw_connected = sum(1 for r in regions if r["raw_connected_previous_audit"] is True)
    total = len(regions)
    contact = metrics["comparative_audits"]["contact_regions_union"]
    core = metrics["comparative_audits"]["core_reference"]
    return [
        (
            "La union geometrica ya existe en RAW",
            "Hecho demostrado",
            f"{raw_connected}/{total} regiones estaban conectadas en RAW en la auditoria raw-vs-voxel; esta auditoria reutiliza esas zonas y no ejecuta voxelizacion productiva.",
        ),
        (
            "Voxelizacion como mecanismo creador",
            "Hecho demostrado negativo",
            "La auditoria raw-vs-voxel no encontro ninguna region que pasara de separada a fusionada entre 0.01 y 0.10 m.",
        ),
        (
            "Densificacion/MVS o nube densa como origen observable",
            "Evidencia fuerte",
            "La geometria adicional esta en point_cloud.ply, que es el producto denso descargado desde NodeODM; no hay evidencia de que etapas posteriores la creen.",
        ),
        (
            "Soporte local geometrico distinto en contactos",
            "Evidencia moderada",
            f"Comparacion RAW-vs-RAW. Mediana vecinos r=0.20 m: contactos={contact['local_neighbors_r020'].get('median')}, core={core['local_neighbors_r020'].get('median')}; kdist20 mediana contactos={contact['kdist20_m'].get('median')}, core={core['kdist20_m'].get('median')}.",
        ),
        (
            "Errores de matching especificos por camara",
            "Hipotesis no demostrable con los artefactos disponibles",
            "No se encontro reconstruction/tracks/depth maps de la ultima corrida 971d... que permita asignar cada punto denso a camaras o matches.",
        ),
        (
            "Reconstruccion de zonas ocluidas/interpolacion",
            "Hipotesis con evidencia geometrica indirecta",
            "Se miden espesor, curvatura, normales y planitud en las zonas de contacto, pero sin depth maps/tracks no se puede atribuir causalidad interna exacta.",
        ),
    ]


def write_reports(inv: list[dict], metrics: dict, region_rows: list[dict], comparative: dict) -> None:
    inv_latest = [r for r in inv if r.get("candidate_latest_session")]
    full_opensfm = [
        r
        for r in inv
        if "projects/ForestVol/data/nodeodm" in r["path"].replace("\\", "/")
        and ("opensfm" in r["path"].lower() or "images.json" in r["path"].lower())
    ]
    table = classification_table(metrics)

    report = []
    report.append("# Auditoria cientifica de mecanismo fotogrametrico\n")
    report.append("## Alcance\n")
    report.append("Esta auditoria es offline. No modifica pipeline productivo, no reconstruye imagenes, no ejecuta NodeODM y no cambia parametros. Lee artefactos existentes y reutiliza las regiones espurias ya localizadas por auditorias previas.\n")
    report.append("## Artefactos disponibles\n")
    report.append(f"- Artefactos inventariados: `{len(inv)}`.\n")
    report.append(f"- Artefactos que pertenecen directamente a la ultima sesion `971d...`: `{len(inv_latest)}`.\n")
    report.append(f"- Artefactos OpenSfM/NodeODM encontrados en cache local historica: `{len(full_opensfm)}`.\n")
    report.append("- Inventario completo: `artifact_inventory.csv` y `artifact_inventory.json`.\n")
    report.append("\n### Limitacion critica de trazabilidad por camara\n")
    report.append("Para la ultima sesion auditada `971d6e25-8ff0-41d2-8784-c981dec7ccbf` se encontro el `point_cloud.ply`, pero no un paquete completo de `reconstruction.json`, `tracks`, `depth maps` o `opensfm` asociado a esa misma corrida dentro de los artefactos disponibles. Por eso las auditorias de soporte por camara y matching quedan disenadas y documentadas, pero no pueden demostrar causalidad puntual por camara sobre la ultima nube.\n")
    report.append("## Bateria de auditorias implementada\n")
    report.append("| Auditoria | Pregunta | Metricas | Entregables | Estado |\n")
    report.append("|---|---|---|---|---|\n")
    report.append("| Inventario ODM/OpenSfM | Que evidencia existe realmente? | rutas, tamano, utilidad, pertenencia a ultima sesion | artifact_inventory.csv/json | implementada |\n")
    report.append("| Continuidad RAW en contactos | La geometria adicional ya esta en RAW? | componentes eps=0.35, puntos por crop, cortes previos | region_mechanism_metrics.csv | implementada |\n")
    report.append("| Densidad local | Las uniones tienen soporte local bajo/alto? | vecinos r=0.20, kdist20 | density_histogram.png, raw_density_overlay.ply | implementada |\n")
    report.append("| Normales | Las superficies son coherentes o caoticas? | abs(dot normal local) | normal_consistency_histogram.png | implementada |\n")
    report.append("| Curvatura | Son superficies suaves/interpoladas o bordes bruscos? | lambda_min/sum(lambda) | curvature_histogram.png | implementada |\n")
    report.append("| Espesor/planitud | Hay laminas artificiales o superficies gruesas? | thickness p05-p95, planarity_ratio | mechanism_metrics.json | implementada |\n")
    report.append("| Soporte fotogrametrico por camara | Cuantas camaras observan cada region? | observaciones por punto, cobertura angular | disenada | bloqueada por falta de tracks/depth de la ultima sesion |\n")
    report.append("| Matching/depth maps | La union nace en MVS o en SfM/matching? | profundidad por imagen, reproyeccion, consistencia multi-vista | disenada | bloqueada por falta de depth/tracks de la ultima sesion |\n")
    report.append("\n## Resultados por region\n")
    report.append("| Region | pts RAW contacto | comps eps=.35 | densidad mediana | kdist20 mediana | curvatura mediana | coherencia normales | espesor p05-p95 | conectada RAW previa |\n")
    report.append("|---:|---:|---:|---:|---:|---:|---:|---:|---|\n")
    for r in region_rows:
        report.append(
            f"| {r['region_id']} | {r['raw_contact_points']} | {r['raw_contact_components_eps035']} | "
            f"{r['local_density_neighbors_median_r020']:.2f} | {r['kdist20_median_m']:.4f} | "
            f"{r['curvature_median']:.6f} | {r['normal_consistency_median_absdot']:.4f} | "
            f"{r['thickness_p05_p95_m']:.4f} | {r['raw_connected_previous_audit']} |\n"
        )
    report.append("\n## Comparacion contactos vs core del castillo\n")
    c = comparative["contact_regions_union"]
    core = comparative["core_reference"]
    report.append(f"- Puntos core muestreados: `{core['points']}`; puntos union de contactos: `{c['points']}`.\n")
    report.append(f"- Densidad mediana r=0.20 m: core `{core['local_neighbors_r020']['median']}`, contactos `{c['local_neighbors_r020']['median']}`.\n")
    report.append(f"- kdist20 mediana: core `{core['kdist20_m']['median']}`, contactos `{c['kdist20_m']['median']}`.\n")
    report.append(f"- Curvatura mediana: core `{core['curvature']['median']}`, contactos `{c['curvature']['median']}`.\n")
    report.append(f"- Coherencia normal mediana: core `{core['normal_consistency_absdot']['median']}`, contactos `{c['normal_consistency_absdot']['median']}`.\n")
    report.append("\n## Clasificacion de conclusiones\n")
    report.append("| Afirmacion | Clasificacion | Evidencia |\n")
    report.append("|---|---|---|\n")
    for claim, level, evidence in table:
        report.append(f"| {claim} | {level} | {evidence} |\n")
    report.append("\n## Criterios de aceptacion/rechazo por mecanismo\n")
    report.append("- Densificacion MVS: aceptable como mecanismo observable si la geometria esta en `point_cloud.ply` RAW y no en etapas posteriores. Resultado: evidencia fuerte, pero no se puede aislar algoritmo interno exacto sin depth maps.\n")
    report.append("- Interpolacion/reconstruccion de superficies: evidencia moderada si las zonas de contacto son continuas, planas/suaves y con espesor laminar. Resultado: revisar `thickness`, `curvature` y overlays.\n")
    report.append("- Errores de matching: no demostrable con los datos actuales; requiere tracks/reconstruction/depth asociados a la misma corrida.\n")
    report.append("- Multiples vistas/cobertura baja: no demostrable con los datos actuales; requiere poses y visibilidad por punto de la misma corrida.\n")
    report.append("- Procesamiento posterior: rechazado por auditorias previas y por la presencia de la union en RAW.\n")
    report.append("\n## Visualizaciones\n")
    report.append("- `raw_contact_regions_overlay.ply`: RAW gris + regiones de contacto rojas.\n")
    report.append("- `contact_density_overlay.ply`: RAW gris + densidad local en contactos.\n")
    report.append("- `raw_density_overlay.ply`: nube RAW coloreada por densidad.\n")
    report.append("- `views/raw_contact_front.png`, `side`, `top`, `iso`.\n")
    report.append("- Histogramas: `density_histogram.png`, `kdist20_histogram.png`, `curvature_histogram.png`, `normal_consistency_histogram.png`.\n")
    (OUT / "report.md").write_text("".join(report), encoding="utf-8")

    trace = []
    trace.append("# Traceability\n\n")
    trace.append(f"- Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}.\n")
    trace.append("- Se leyo el pedido del usuario y se definio una auditoria offline encapsulada.\n")
    trace.append(f"- Se uso nube RAW: `{RAW_CLOUD}`.\n")
    trace.append(f"- Se uso nube final de volumen para regiones/contexto: `{FINAL_VOLUME_CLOUD}`.\n")
    trace.append(f"- Se reutilizaron contactos de: `{BRIDGE_METRICS}` y `{RAW_VS_VOXEL}`.\n")
    trace.append("- Decision: no ejecutar NodeODM ni funciones del pipeline productivo; solo lecturas y calculos geometricos independientes.\n")
    trace.append("- Decision: clasificar soporte por camara como bloqueado si no existen tracks/depth/reconstruction de la ultima sesion.\n")
    trace.append("- Evidencia primaria: point_cloud RAW escalada, regiones de contacto localizadas, continuidad previa raw-vs-voxel, metricas de densidad/normales/curvatura/espesor.\n")
    trace.append("- Parametros registrados en `mechanism_metrics.json`.\n")
    trace.append("- Comando reproducible: `python experiments/photogrammetry_mechanism_audit/run_photogrammetry_mechanism_audit.py`.\n")
    (OUT / "traceability.md").write_text("".join(trace), encoding="utf-8")

    design = []
    design.append("# Diseno de bateria cientifica\n\n")
    design.append("Cada auditoria se plantea con objetivo, hipotesis, procedimiento, metricas, visualizaciones y criterio.\n\n")
    audits = [
        ("Inventario", "Saber que evidencia existe.", "Si faltan tracks/depth de la ultima sesion, no se puede probar soporte por camara.", "Buscar artefactos ODM/OpenSfM existentes.", "conteo, ruta, utilidad", "CSV/JSON", "Aceptar solo afirmaciones soportadas por archivos presentes."),
        ("Soporte fotogrametrico", "Medir observaciones por punto.", "Regiones espurias tendrian bajo numero de vistas o mala geometria angular.", "Reproyectar puntos usando poses/tracks/depth de la misma corrida.", "n camaras, angulo base, reprojection residual", "heatmaps por region", "Rechazar si soporte comparable al core; aceptar si soporte significativamente menor."),
        ("Cobertura visual", "Detectar zonas ocluidas o mal vistas.", "Superficies espurias nacen donde hay pocas vistas utiles.", "Calcular visibilidad/cobertura angular por punto.", "solid angle, baseline, redundancia", "overlays de cobertura", "Aceptar si contactos tienen cobertura baja vs core."),
        ("Densidad", "Comparar soporte local.", "Geometria espuria tiene densidad distinta o baja.", "KDTree local r=0.20 y kdist20.", "vecinos, kdist", "histogramas/PLY", "Aceptar diferencia si medianas/percentiles se separan claramente."),
        ("Normales", "Medir coherencia superficial.", "Interpolaciones tendran normales mas coherentes/laminares o inconsistentes segun ruido.", "Estimar normales y abs(dot) local.", "normal consistency", "histograma", "Clasificar segun diferencia vs core."),
        ("Curvatura", "Buscar superficies suavizadas/puentes.", "Interpolacion crea curvatura baja o transiciones suaves no cilindricas.", "PCA local.", "curvatura lambda_min/sum", "histograma/overlay", "Aceptar evidencia si contactos difieren del core."),
        ("Espesor", "Detectar laminas artificiales.", "Superficies interpoladas tienen espesor p05-p95 bajo y alta planitud.", "PCA por crop de contacto.", "thickness, planarity", "PLY por region", "Aceptar evidencia si espesor/planitud difiere del core."),
        ("Depth/MVS", "Aislar si nace en mapas de profundidad.", "Si depth maps ya contienen la superficie, origen es MVS.", "Comparar depth maps originales contra nube densa.", "residuales profundidad, consistencia multi-vista", "overlays por imagen", "Bloqueado sin depth maps de la misma corrida."),
    ]
    design.append("| Auditoria | Objetivo | Hipotesis | Procedimiento | Metricas | Visualizaciones | Criterio |\n")
    design.append("|---|---|---|---|---|---|---|\n")
    for row in audits:
        design.append("| " + " | ".join(row) + " |\n")
    (OUT / "audit_battery_design.md").write_text("".join(design), encoding="utf-8")


def main() -> int:
    start = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "views").mkdir(exist_ok=True)

    inv = inventory()
    if inv:
        with (OUT / "artifact_inventory.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(inv[0].keys()))
            writer.writeheader()
            writer.writerows(inv)
    (OUT / "artifact_inventory.json").write_text(json.dumps(inv, indent=2), encoding="utf-8")

    _, raw_points = read_cloud(RAW_CLOUD, scale=SCALE_FACTOR)
    _, final_points = read_cloud(FINAL_VOLUME_CLOUD)
    regions = load_regions()

    endpoints = []
    for r in regions:
        if r.get("external_endpoint_xyz") and r.get("castle_endpoint_xyz"):
            endpoints.append(r["external_endpoint_xyz"])
            endpoints.append(r["castle_endpoint_xyz"])
    endpoints_arr = np.asarray(endpoints, dtype=float)
    final_box = aabb(final_points)
    final_min = np.asarray(final_box["min"]) - 0.15
    final_max = np.asarray(final_box["max"]) + 0.15
    raw_in_final_bbox = np.all((raw_points >= final_min) & (raw_points <= final_max), axis=1)
    if len(endpoints_arr):
        d_to_contacts, _ = cKDTree(endpoints_arr).query(raw_points, k=1)
        core_mask = raw_in_final_bbox & (d_to_contacts > 1.2)
    else:
        core_mask = raw_in_final_bbox
    core_points = raw_points[core_mask]

    raw_kdist20, _ = knn_stats(raw_points, 20)
    raw_density_proxy = 1.0 / np.maximum(raw_kdist20, 1e-6)
    density_colors = color_by_metric(raw_density_proxy, "plasma")
    write_cloud(OUT / "raw_density_overlay.ply", raw_points, density_colors)

    region_rows = []
    all_contact_indices = set()
    for r in regions:
        rid = r["region_id"]
        ext = np.asarray(r.get("external_endpoint_xyz"), dtype=float)
        cas = np.asarray(r.get("castle_endpoint_xyz"), dtype=float)
        if ext.shape != (3,) or cas.shape != (3,):
            continue
        segment = cas - ext
        seg_len = float(np.linalg.norm(segment))
        if seg_len < 1e-9:
            dseg = np.linalg.norm(raw_points - ext, axis=1)
        else:
            t = np.clip(((raw_points - ext) @ segment) / (seg_len**2), 0, 1)
            proj = ext + t[:, None] * segment
            dseg = np.linalg.norm(raw_points - proj, axis=1)
        crop_idx = np.where(dseg <= CONTACT_CROP_RADIUS_M)[0]
        all_contact_indices.update(crop_idx.tolist())
        crop = raw_points[crop_idx]
        if len(crop) == 0:
            continue
        counts = local_counts(crop, RADIUS_LOCAL_DENSITY_M)
        kdist, curvature = knn_stats(crop, 20)
        consistency = normal_consistency(crop) if len(crop) >= 20 else np.full(len(crop), np.nan)
        thickness = pca_thickness(crop)
        comp_cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(crop))
        labels = np.asarray(comp_cloud.cluster_dbscan(eps=EPS_CONNECTIVITY_M, min_points=3, print_progress=False))
        comps = labels[labels >= 0]
        sizes = np.bincount(comps) if len(comps) else np.array([], dtype=int)

        write_cloud(OUT / f"region_{rid:02d}_contact_density.ply", crop, color_by_metric(counts, "viridis"))

        region_rows.append(
            {
                "region_id": rid,
                "raw_contact_points": int(len(crop)),
                "raw_contact_components_eps035": int(len(sizes)),
                "raw_contact_largest_component_points": int(sizes.max()) if len(sizes) else 0,
                "endpoint_distance_m": seg_len,
                "local_density_neighbors_median_r020": float(np.median(counts)),
                "local_density_neighbors_p05_r020": float(np.percentile(counts, 5)),
                "kdist20_median_m": float(np.median(kdist)),
                "curvature_median": float(np.median(curvature)),
                "normal_consistency_median_absdot": float(np.nanmedian(consistency)),
                "thickness_p05_p95_m": thickness["thickness_m"],
                "planarity_ratio": thickness["planarity_ratio"],
                "aabb_volume_m3": aabb(crop)["volume_m3"],
                "convex_hull_volume_m3": convex_hull_volume(crop),
                "raw_connected_previous_audit": r.get("raw_connected"),
                "minimum_vertex_cut_previous_audit": r.get("minimum_vertex_cut_size"),
                "minimum_edge_cut_previous_audit": r.get("minimum_edge_cut_size"),
            }
        )

    contact_idx = np.array(sorted(all_contact_indices), dtype=int)
    contact_mask_raw = np.zeros(len(raw_points), dtype=bool)
    contact_mask_raw[contact_idx] = True
    contact_points = raw_points[contact_mask_raw]

    core_sample = core_points
    if len(core_sample) > 50000:
        rng = np.random.default_rng(7)
        core_sample = core_sample[rng.choice(len(core_sample), size=50000, replace=False)]
    core_counts = local_counts(core_sample, RADIUS_LOCAL_DENSITY_M)
    core_kdist, core_curv = knn_stats(core_sample, 20)
    contact_counts = local_counts(contact_points, RADIUS_LOCAL_DENSITY_M) if len(contact_points) else np.array([])
    contact_kdist, contact_curv = knn_stats(contact_points, 20) if len(contact_points) else (np.array([]), np.array([]))
    contact_cons = normal_consistency(contact_points) if len(contact_points) >= 20 else np.array([])
    core_cons = normal_consistency(core_sample) if len(core_sample) >= 20 else np.array([])

    comparative = {
        "core_reference": {
            "points": int(len(core_sample)),
            "local_neighbors_r020": summarize_array(core_counts),
            "kdist20_m": summarize_array(core_kdist),
            "curvature": summarize_array(core_curv),
            "normal_consistency_absdot": summarize_array(core_cons),
            "thickness": pca_thickness(core_sample),
        },
        "contact_regions_union": {
            "points": int(len(contact_points)),
            "local_neighbors_r020": summarize_array(contact_counts),
            "kdist20_m": summarize_array(contact_kdist),
            "curvature": summarize_array(contact_curv),
            "normal_consistency_absdot": summarize_array(contact_cons),
            "thickness": pca_thickness(contact_points) if len(contact_points) else {},
        },
    }

    with (OUT / "region_mechanism_metrics.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(region_rows[0].keys()) if region_rows else ["region_id"])
        writer.writeheader()
        writer.writerows(region_rows)

    metrics = {
        "parameters": {
            "scale_factor_m_per_unit": SCALE_FACTOR,
            "radius_local_density_m": RADIUS_LOCAL_DENSITY_M,
            "contact_crop_radius_m": CONTACT_CROP_RADIUS_M,
            "eps_connectivity_m": EPS_CONNECTIVITY_M,
            "normal_radius_m": NORMAL_RADIUS_M,
            "max_nn": MAX_NN,
        },
        "sources": {
            "raw_cloud": str(RAW_CLOUD),
            "final_volume_cloud": str(FINAL_VOLUME_CLOUD),
            "bridge_metrics": str(BRIDGE_METRICS),
            "raw_vs_voxel_metrics": str(RAW_VS_VOXEL),
            "raw_cloud_sha256": file_sha256(RAW_CLOUD),
            "final_volume_cloud_sha256": file_sha256(FINAL_VOLUME_CLOUD),
        },
        "raw_cloud_scaled": {
            "points": int(len(raw_points)),
            "aabb": aabb(raw_points),
            "convex_hull_volume_m3": convex_hull_volume(raw_points[:: max(1, len(raw_points) // 120000)]),
        },
        "final_volume_cloud": {
            "points": int(len(final_points)),
            "aabb": aabb(final_points),
            "convex_hull_volume_m3": convex_hull_volume(final_points),
        },
        "regions": region_rows,
        "comparative_audits": comparative,
        "artifact_inventory_count": len(inv),
        "runtime_seconds": time.time() - start,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "open3d": getattr(o3d, "__version__", "unknown"),
            "numpy": np.__version__,
        },
    }
    (OUT / "mechanism_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    overlay_colors = np.tile(np.array([[0.55, 0.55, 0.55]]), (len(raw_points), 1))
    overlay_colors[contact_mask_raw] = np.array([1.0, 0.1, 0.05])
    write_cloud(OUT / "raw_contact_regions_overlay.ply", raw_points, overlay_colors)

    contact_density_colors = np.tile(np.array([[0.55, 0.55, 0.55]]), (len(raw_points), 1))
    if len(contact_points):
        contact_density_colors[contact_mask_raw] = color_by_metric(local_counts(contact_points, RADIUS_LOCAL_DENSITY_M), "magma")
    write_cloud(OUT / "contact_density_overlay.ply", raw_points, contact_density_colors)

    for view in ["front", "side", "top", "iso"]:
        view_scatter(raw_points, overlay_colors, OUT / "views" / f"raw_contact_{view}.png", view, "RAW + regiones de contacto")
        view_scatter(raw_points, density_colors, OUT / "views" / f"raw_density_{view}.png", view, "Densidad local RAW")

    save_hist({"core_castillo": core_counts, "contactos_espurios": contact_counts}, OUT / "density_histogram.png", "Densidad local r=0.20 m", "vecinos")
    save_hist({"core_castillo": core_kdist, "contactos_espurios": contact_kdist}, OUT / "kdist20_histogram.png", "Distancia al vecino 20", "m")
    save_hist({"core_castillo": core_curv, "contactos_espurios": contact_curv}, OUT / "curvature_histogram.png", "Curvatura PCA local", "lambda_min / sum(lambda)")
    save_hist({"core_castillo": core_cons, "contactos_espurios": contact_cons}, OUT / "normal_consistency_histogram.png", "Coherencia de normales", "abs(dot normal local)")

    write_reports(inv, metrics, region_rows, comparative)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
