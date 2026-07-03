# Hito 0.5 Closed Report

## Declaracion oficial

**HITO 0.5: NOT CLOSED**

El cierre formal fue evaluado contra el contrato de aceptacion definido para Set 1. Aunque las dos ejecuciones end-to-end se completaron sin intervencion manual, ambas excedieron el umbral maximo de error de `20%` contra el ground truth oficial `119.74 m3`.

Por lo tanto, el harness **no debe actualizar HITO 0.5 a CLOSED**, no debe declarar baseline aceptado y no debe marcar `ready_for_next_milestone`.

## Contrato de aceptacion aplicado

- Dataset bloqueante: Set 1, `projects/ForestVol/set_imagenes+guia/set_fotos_castillo_de_madera`
- Ground truth: `119.74 m3`
- Umbral obligatorio: error porcentual `<= 20%`
- Reproducibilidad: `2` ejecuciones consecutivas
- Intervencion manual permitida: `no`
- Set 2: benchmark informativo, no bloqueante

## Pipeline ejecutado

Set 1 se ejecuto desde imagenes originales con:

1. Imagenes originales
2. Calibracion ArUco/GCP
3. NodeODM
4. OpenSfM / dense point cloud via NodeODM
5. Outlier Removal
6. Voxelization con `voxel_size_m = 0.07`
7. DBSCAN con `eps = 0.5`, `min_points = 10`
8. Cluster Selection `top_3_by_points`
9. PDI con `voxel_size_m = 0.25`
10. Volumen final vs ground truth

El runner reproducible queda en `experiments/hito_0_5_close/hito_0_5_close_runner.py`.

## Resultados Set 1

| Run | Session ID | NodeODM task | Volumen final | Error abs | Error % | Estado |
|---:|---|---|---:|---:|---:|---|
| 1 | `065d24e9-e723-42a5-b1c5-f14a5e4bc36b` | `85ee2d31-702c-43f8-871e-ac6f2858d048` | 285.9531 | 166.2131 | 138.811675 | FAIL |
| 2 | `a44ee3a6-b7d0-4c62-b075-1a2865dcded0` | `36216849-b85f-48b1-a6c5-380fce12966d` | 243.0938 | 123.3538 | 103.018039 | FAIL |

## Verificacion de reproducibilidad

| Criterio | Resultado |
|---|---|
| Dos ejecuciones consecutivas realizadas | PASS |
| NodeODM completo en ambas ejecuciones | PASS |
| Sin intervencion manual entre corridas | PASS |
| Error <= 20% en Run 1 | FAIL |
| Error <= 20% en Run 2 | FAIL |
| Variacion de volumen entre corridas | 42.8593 m3 |
| Reproducibilidad aceptable para cierre | FAIL |

Decision: **NOT CLOSED**.

## Metricas por etapa

### Set 1 Run 1

| Etapa | Puntos | Perdida % | BBox m3 | Densidad |
|---|---:|---:|---:|---:|
| RAW Dense Point Cloud | 358198 | - | 6070.487761 | 59.006461 |
| Outlier Removal | 353658 | 1.2675 | 5921.683048 | 59.722548 |
| Voxelization | 32508 | 90.8081 | 5896.120010 | 5.513456 |
| DBSCAN + Cluster Selection | 30479 | 6.2415 | 1208.527318 | 25.219951 |
| PDI | 30479 | 0.0 | 1208.527318 | 25.219951 |

- Clusters DBSCAN: `33`
- Noise points: `128`
- Clusters seleccionados: `[0, 2, 20]`
- Tiempo total: `293.687946 s`
- Memoria Python peak: `165.837127 MB`

### Set 1 Run 2

| Etapa | Puntos | Perdida % | BBox m3 | Densidad |
|---|---:|---:|---:|---:|
| RAW Dense Point Cloud | 424981 | - | 119965.250500 | 3.542534 |
| Outlier Removal | 418286 | 1.5754 | 17629.657182 | 23.726270 |
| Voxelization | 28064 | 93.2907 | 17595.342227 | 1.594968 |
| DBSCAN + Cluster Selection | 26261 | 6.4246 | 862.100019 | 30.461663 |
| PDI | 26261 | 0.0 | 862.100019 | 30.461663 |

- Clusters DBSCAN: `54`
- Noise points: `224`
- Clusters seleccionados: `[6, 0, 3]`
- Tiempo total: `268.358104 s`
- Memoria Python peak: `165.834317 MB`

## Set 2 informativo

Set 2 se mantiene como benchmark de robustez no bloqueante. La evidencia informativa vigente desde `experiments/segmentation_pipeline_full/final_selection.json` reporta:

| Dataset | Estrategia | Volumen | Error abs | Error % | Puntos | Clusters |
|---|---|---:|---:|---:|---:|---:|
| set2 | `top_k_by_pdi_volume` | 48.3125 | 71.4275 | 59.652163 | 16832 | 3 |

Este resultado no afecta el estado del hito por definicion del contrato, pero confirma una limitacion de robustez pendiente.

## Estado del harness

- `HITO 0.5 -> NOT CLOSED`
- Baseline aceptado: `no actualizado`
- Ready for next milestone: `false`
- Evidencia principal: `experiments/hito_0_5_close/hito_0_5_close_results.json`
- Artefactos por corrida:
  - `experiments/hito_0_5_close/set1_run_1/result.json`
  - `experiments/hito_0_5_close/set1_run_2/result.json`
  - `experiments/hito_0_5_close/set1_run_1/selected_pdi_input.ply`
  - `experiments/hito_0_5_close/set1_run_2/selected_pdi_input.ply`

## Limitaciones conocidas

- La configuracion experimental que ajusto bien sobre una nube Set 1 previa no se reprodujo al reconstruir nuevamente desde imagenes.
- NodeODM genero nubes RAW con diferencias fuertes entre corridas: `358198` vs `424981` puntos y bounding boxes muy distintos.
- La seleccion `top_3_by_points` captura componentes que inflan el soporte PDI en ambas corridas nuevas.
- El pipeline corre sin intervencion manual, pero aun no cumple precision ni reproducibilidad de volumen.

## Recomendacion

No cerrar Hito 0.5 todavia. El siguiente paso debe estabilizar la reconstruccion/segmentacion Set 1 en dos corridas consecutivas antes de promover baseline o avanzar al siguiente hito.
