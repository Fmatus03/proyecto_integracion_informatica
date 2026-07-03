# Volume Input Audit

Source cloud: `C:\Users\Fabian Matus\OneDrive\Escritorio\harness_con_separacion_de_proyectos\projects\ForestVol\data\processed\971d6e25-8ff0-41d2-8784-c981dec7ccbf\point_cloud.ply`

No se ejecuto NodeODM ni se reconstruyo la nube. No se modifico OpenSfM, DBSCAN, PDI, segmentacion, escalado ni parametros.

## Conjunto auditado

Se audito exactamente el `point_cloud` que `mesh_service.generate_preliminary_volumetry()` entrega a `_estimate_pdi_volume()` despues de:

1. `_load_point_cloud()`
2. `scale(0.54611448)`
3. `_clean_point_cloud(voxel_size_m=None, outlier_neighbors=24, outlier_std_ratio=2.0)`
4. `_segment_woodpile_components(segmentation_voxel_size_m=0.06, cluster_eps_m=0.35, cluster_min_points=20, max_components=2)`
5. `_estimate_pdi_volume(point_cloud, 0.25)`

## Metricas principales

| Metrica | Valor |
|---|---:|
| Puntos raw escalados | 746225 |
| Puntos tras limpieza mesh_service | 737554 |
| Universo de segmentacion voxel 0.06 | 48483 |
| Puntos usados por volumen | 45511 |
| Puntos rechazados del universo de segmentacion | 2972 |
| % usado vs raw escalado | 6.0988% |
| % usado vs universo segmentacion | 93.8700% |
| Componentes conectados sin ruido | 40 |
| Componentes importantes >=10% | 1 |
| Componentes seleccionados | [0] |

## Geometria del input final de volumen

| Metrica | X | Y | Z | Volumen |
|---|---:|---:|---:|---:|
| AABB | 11.1312 m | 10.5886 m | 4.3218 m | 509.3771 m3 |
| OBB PCA | 10.8471 m | 10.9005 m | 4.7735 m | 564.4094 m3 |

- Convex hull del input final: `211.064573` m3
- Volumen PDI calculado por mesh_service: `234.0469` m3
- Hull PDI reportado por mesh_service: `211.064573` m3
- Voxeles ocupados: `2912`
- Voxeles densos: `2703`
- Voxeles solidos: `14979`

## Componentes conectados

| Componente | Seleccionado | Puntos | Ratio | AABB m3 | Extent XYZ | Hull m3 |
|---:|---|---:|---:|---:|---|---:|
| 0 | True | 45511 | 1.0000 | 509.3771 | 11.131, 10.589, 4.322 | 211.0646 |
| 4 | False | 304 | 0.0067 | 2.6971 | 2.447, 2.104, 0.524 | 0.6840 |
| 23 | False | 168 | 0.0037 | 0.2942 | 1.527, 1.308, 0.147 | 0.0512 |
| 19 | False | 111 | 0.0024 | 0.1990 | 0.926, 0.823, 0.261 | 0.0374 |
| 10 | False | 96 | 0.0021 | 0.2502 | 0.981, 0.480, 0.531 | 0.0221 |
| 8 | False | 95 | 0.0021 | 0.1343 | 0.617, 1.009, 0.216 | 0.0169 |
| 3 | False | 94 | 0.0021 | 0.2497 | 0.884, 1.069, 0.264 | 0.0295 |
| 21 | False | 91 | 0.0020 | 0.0822 | 1.055, 0.962, 0.081 | 0.0047 |
| 13 | False | 88 | 0.0019 | 0.1619 | 0.722, 1.049, 0.214 | 0.0248 |
| 15 | False | 87 | 0.0019 | 0.1626 | 0.915, 0.865, 0.206 | 0.0143 |
| 24 | False | 83 | 0.0018 | 0.5388 | 0.530, 1.025, 0.992 | 0.0381 |
| 20 | False | 69 | 0.0015 | 0.1672 | 0.445, 0.949, 0.396 | 0.0069 |

## Validacion visual objetiva

Los archivos `front.png`, `side.png`, `top.png`, `iso.png` y `selection_overlay.ply` usan: gris = nube completa raw escalada muestreada, rojo = puntos descartados del universo de segmentacion, verde = input exacto de PDI.

1. Suelo incluido: revisar puntos verdes cercanos a la base. Z min del input final = -1.0067 m; Z max = 3.3150 m.
2. Ramas alrededor: cualquier estructura roja fue descartada; cualquier estructura verde irregular externa esta incluida en PDI.
3. Arboles vecinos: las estructuras verticales externas deben aparecer rojas si fueron descartadas; verdes si entraron al volumen.
4. Quinta hilera: altura del input final = 4.3218 m.
5. Segunda pila parcial: componentes importantes >=10% = 1; seleccionados = [0].
6. Nube flotante incluida: `connected_components.ply` colorea componentes; componentes verdes aislados indicarian inclusion.
7. Puntos fuera del castillo: todo punto verde fuera del castillo en `selection_overlay.ply` esta incluido en el volumen.

## Conclusion cuantitativa

El volumen se calcula sobre 45511 puntos finales. La seleccion incluye 1 componente(s): [0]. El volumen PDI oficial recalculado sobre ese input es 234.0469 m3 y el convex hull del mismo input es 211.064573 m3. La decision sobre mala seleccion, deformacion o ambas debe basarse en los puntos verdes del overlay y en la tabla de componentes anterior.
