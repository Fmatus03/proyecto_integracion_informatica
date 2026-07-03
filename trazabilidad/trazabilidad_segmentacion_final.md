# Trazabilidad segmentacion final

## Hipotesis iniciales

- La perdida principal ocurre en la segmentacion previa a PDI, no en PDI.
- Reducir `voxel_size` y revisar seleccion de clusters puede disminuir error vs ground truth.
- Mayor volumen no es criterio de exito; se optimiza error absoluto contra `119.74 m3`.

## Experimentos realizados

- Auditoria completa RAW -> Outlier Removal -> Voxel Down Sample -> DBSCAN -> Ranking -> Cluster Selection -> PDI.
- Sensibilidad de `voxel_size` entre `0.01` y `0.10` en ambos sets.
- Matriz DBSCAN fijando el mejor voxel por set.
- Comparacion de estrategias de seleccion: actual, Top-K por volumen PDI, densidad, puntos, ponderada, proximidad, bbox overlap y adjacency.

## Resultado objetivo

| Dataset | Pipeline experimental | Volumen | Error abs | Error % | Clusters | Puntos |
|---|---|---:|---:|---:|---:|---:|
| set1 | voxel=0.07, eps=0.5, min_points=10, top_k_by_points | 119.1875 | 0.5525 | 0.461416 | 3 | 19958 |
| set2 | voxel=0.02, eps=0.5, min_points=10, top_k_by_pdi_volume | 48.3125 | 71.4275 | 59.652163 | 3 | 16832 |

## Decisiones tomadas

- No se modifica produccion en este paso.
- Las mejores variantes quedan como candidatos experimentales, no como configuracion productiva.
- La validacion productiva exige ejecutar nuevamente desde imagenes, sin reutilizar outputs previos.
- Fases 6 a 9 quedan bloqueadas: set1 mejora de forma fuerte, pero set2 aun mantiene error alto y no cumple mejora clara/suficiente en ambos datasets.

## Cambios implementados

- Se agrego el experimento reproducible `experiments/segmentation_pipeline_full/segmentation_pipeline_full.py`.
- Se generaron logs JSON/CSV y graficos bajo `experiments/segmentation_pipeline_full/`.

## Comparacion antes/despues

| Dataset | Baseline volumen | Baseline error abs | Baseline error % | Candidato volumen | Candidato error abs | Candidato error % |
|---|---:|---:|---:|---:|---:|---:|
| set1 | 69.8281 | 49.9119 | 41.683564 | 119.1875 | 0.5525 | 0.461416 |
| set2 | 39.0156 | 80.7244 | 67.416402 | 48.3125 | 71.4275 | 59.652163 |

No hay cambios productivos aun; el despues es un candidato experimental.

## Graficos y artefactos

- `experiments/segmentation_pipeline_full/voxel_sensitivity_error.png`
- `experiments/segmentation_pipeline_full/audit_pipeline_stages.json`
- `experiments/segmentation_pipeline_full/voxel_sensitivity.csv`
- `experiments/segmentation_pipeline_full/dbscan_sensitivity.csv`
- `experiments/segmentation_pipeline_full/cluster_strategy_comparison.csv`
- `experiments/segmentation_pipeline_full/final_selection.json`

## Limitaciones

- Esta corrida reutiliza nubes ya materializadas en `experiments/pipeline_stage_analysis` para aislar segmentacion.
- La fase end-to-end desde imagenes requiere disponibilidad operativa de NodeODM/OpenSfM.
- Las metricas de memoria son de asignaciones Python observables con `tracemalloc`, no RSS total del proceso nativo de Open3D.

## Riesgos

- Parametros que reducen error en estos dos sets pueden sobreajustar si no se valida con mas capturas.
- Estrategias Top-K por volumen pueden inflar volumen sin corregir geometria; por eso no se usan como criterio primario.

## Recomendaciones futuras

- Ejecutar fase end-to-end desde imagenes con los candidatos ganadores.
- Agregar mas datasets con ground truth certificado antes de promover cambios.
- Persistir un contrato de benchmark que compare produccion y experimento con la misma fuente CloudProvider.
