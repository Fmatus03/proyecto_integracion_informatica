# Validacion final Hito 0.5 con dataset definitivo

## Resumen ejecutivo

Dataset validado: `/app/projects/ForestVol/set_imagenes+guia/set_fotos_castillo_de_madera_defnitivo`.

Imagenes utilizadas por corrida: `95`.

Ground truth: `119.74 m3`.

Criterio de aceptacion: error porcentual `<= 20.0%`, reproducibilidad en al menos `2` corridas y sin intervencion manual.

Decision final: **HITO 0.5 = NOT CLOSED**.

No se modifico el pipeline productivo porque el criterio de aceptacion no fue satisfecho.

## Comparacion entre corridas

| Run | Session ID | NodeODM Task ID | Imagenes | Tiempo s | Volumen m3 | Error abs m3 | Error % | Estado |
|---:|---|---|---:|---:|---:|---:|---:|---|
| 1 | `d78e0ca6-6259-47b1-89a7-2278acf95119` | `3fa0447b-f109-43d8-abb7-161e9a863cfa` | 95 | 1780.591705 | 805.9531 | 686.2131 | 573.085936 | FAIL |
| 2 | `ecd0f8b7-64f5-437b-9048-2ae83609e8e7` | `ba72bb1c-f0fc-491c-8d80-71a0bb97e3d2` | 95 | 1722.819222 | 946.0781 | 826.3381 | 690.110322 | FAIL |

## Metricas por etapa

### Corrida 1

| Etapa | Puntos | Perdida % | BBox m3 | Dimensiones XYZ m | Centroide |
|---|---:|---:|---:|---|---|
| RAW Dense Point Cloud | 1673943 | None | 17626.455767 | `[29.323956, 29.670074, 20.259271]` | `[-9.812625, -0.374394, 1.925084]` |
| Outlier Removal | 1658250 | 0.9375 | 8945.901881 | `[25.467827, 25.46838, 13.792117]` | `[-9.835429, -0.388992, 1.929922]` |
| Voxelization | 125935 | 92.4055 | 8919.683596 | `[25.458653, 25.461152, 13.760556]` | `[-8.481758, 0.108866, 1.747261]` |
| DBSCAN + Cluster Selection | 119692 | 4.9573 | 3786.17457 | `[20.257236, 21.31806, 8.767439]` | `[-8.617018, 0.072244, 1.802624]` |
| PDI | 119692 | 0.0 | 3786.17457 | `[20.257236, 21.31806, 8.767439]` | `[-8.617018, 0.072244, 1.802624]` |

- Clusters DBSCAN: `121`
- Clusters seleccionados: `[0, 71, 11]`
- Puntos finales usados por PDI: `119692`
- Puntos RAW: `1673943`
- Puntos tras Outlier Removal: `1658250`
- Puntos tras Segmentacion: `119692`

### Corrida 2

| Etapa | Puntos | Perdida % | BBox m3 | Dimensiones XYZ m | Centroide |
|---|---:|---:|---:|---|---|
| RAW Dense Point Cloud | 1786481 | None | 27014.074271 | `[32.07781, 38.604008, 21.814888]` | `[8.357905, 3.959841, 2.751252]` |
| Outlier Removal | 1771982 | 0.8116 | 16229.3943 | `[28.113837, 31.323624, 18.429358]` | `[8.383536, 3.983113, 2.764115]` |
| Voxelization | 146740 | 91.7189 | 16171.004855 | `[28.099381, 31.294378, 18.38967]` | `[7.213892, 2.978177, 2.39665]` |
| DBSCAN + Cluster Selection | 141274 | 3.725 | 4425.672767 | `[23.552737, 22.492586, 8.354078]` | `[7.321014, 2.945702, 2.392841]` |
| PDI | 141274 | 0.0 | 4425.672767 | `[23.552737, 22.492586, 8.354078]` | `[7.321014, 2.945702, 2.392841]` |

- Clusters DBSCAN: `104`
- Clusters seleccionados: `[0, 27, 48]`
- Puntos finales usados por PDI: `141274`
- Puntos RAW: `1786481`
- Puntos tras Outlier Removal: `1771982`
- Puntos tras Segmentacion: `141274`

## Estabilidad observada

- Volumenes: `[805.9531, 946.0781]` m3.
- Errores porcentuales: `[573.085936, 690.110322]`.
- Delta maximo de volumen: `140.125` m3 (`117.024386`% del GT).
- Corridas exitosas segun umbral: `0` de `2`.

## Conclusion

**HITO 0.5 = NOT CLOSED**

La solucion experimental no demostro estabilidad/precision suficiente con el dataset definitivo; permanece confinada a `experiments/` y no se promueve a produccion.
