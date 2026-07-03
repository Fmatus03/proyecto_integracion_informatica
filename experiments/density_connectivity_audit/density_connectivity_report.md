# Auditoria cuantitativa de densidad y conectividad

Nube auditada: `C:\Users\Fabian Matus\OneDrive\Escritorio\harness_con_separacion_de_proyectos\experiments\volume_input_audit\selected_volume_cloud.ply`

No se modifico pipeline productivo, parametros, DBSCAN, PDI, ArUco, escalado ni `mesh_service`. La auditoria es offline sobre el PLY final que entra a `_estimate_pdi_volume()`.

## Metricas locales calculadas

Para cada punto se calcularon vecinos dentro de 0.05, 0.10, 0.15, 0.20 y 0.30 m; distancia al vecino 5, 10, 20 y 30; distancia media a 30 vecinos; densidad local r=0.20 m; y score de soporte local normalizado.

## Clustering solo por metricas de densidad

No se uso XYZ, forma del castillo, numero esperado de troncos ni conocimiento semantico. Features: `['neighbors_0_10m', 'neighbors_0_20m', 'neighbors_0_30m', 'kdist_10m', 'kdist_20m', 'kdist_30m', 'mean_dist_30nn', 'local_density_r0_20', 'support_local']`.

| k | inertia | silhouette proxy |
|---:|---:|---:|
| 2 | 244285.56 | 0.7121 |
| 3 | 162515.42 | 0.6297 |
| 4 | 119373.67 | 0.5303 |

Cluster seleccionado: `2`. Separacion de distribucion: `yes`.

| Grupo | Rank soporte | Puntos | % | mediana soporte | mediana densidad r0.20 | mediana vecinos r0.20 | mediana kdist20 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 1 | 38417 | 84.41% | 0.5746 | 1700.97 | 57.0 | 0.1232 |
| 1 | 0 | 7094 | 15.59% | 0.3471 | 775.88 | 26.0 | 0.1711 |

## Comparacion low-support vs high-support

| Metrica | Low-support mediana | High-support mediana | Ratio low/high |
|---|---:|---:|---:|
| vecinos 0.20 m | 26.00 | 57.00 | 0.456 |
| densidad r0.20 | 775.88 | 1700.97 | 0.456 |
| kdist20 | 0.1711 | 0.1232 | 1.389 |
| soporte local | 0.3471 | 0.5746 | 0.604 |

## Puentes de conectividad

Grafo espacial construido con radio `0.35` m, igual al eps de DBSCAN productivo. Se analizaron las mayores regiones low-support y el camino mas corto hasta el mayor componente high-support.

| Region | Puntos region | Camino puntos | Longitud camino | Densidad puente | Soporte puente | Desconecta al remover camino |
|---:|---:|---:|---:|---:|---:|---|
| 0 | 5035 | 2 | 0.1324 | 746.04 | 0.3948 | False |
| 1 | 1694 | 2 | 0.2891 | 895.25 | 0.3519 | False |
| 2 | 134 | 2 | 0.3244 | 1357.79 | 0.4915 | False |
| 3 | 17 | 7 | 1.7189 | 690.62 | 0.3397 | True |
| 4 | 17 | 2 | 0.2263 | 1536.84 | 0.5076 | False |
| 5 | 16 | 2 | 0.2493 | 731.12 | 0.3497 | False |
| 6 | 14 | 2 | 0.2604 | 1357.79 | 0.4275 | False |
| 7 | 14 | 2 | 0.1595 | 969.85 | 0.4137 | False |

## Criterio matematico candidato

Umbral candidato de soporte local: `0.4278`.

- Porcentaje esperado de puntos eliminados: `17.32%`
- Porcentaje del grupo low-support capturado: `98.80%`
- Riesgo estimado sobre puntos no-low-support: `2.28%`

Este criterio NO fue implementado como filtro; solo se reporta como evidencia estadistica.

## Respuestas explicitas

1. Las regiones que parecen ruido tienen menor densidad: si, el grupo low-support tiene mediana de vecinos r0.20 = 26.00 contra 57.00 en high-support.
2. Existe umbral natural: si, moderado, segun silhouette proxy y histogramas.
3. Distribucion bimodal o continua: `yes`.
4. Menor soporte fotogrametrico/geometrico: si, soporte mediano low=0.3471, high=0.5746.
5. El algoritmo actual las considera parte del mismo componente porque existen cadenas de puntos dentro de eps=0.35 m que conectan regiones low-support al cuerpo high-support.
6. Existe puente de conexion: ver `bridge_analysis.ply`; puntos azules son caminos mas cortos.
7. Donde esta el puente: coordenadas y bbox por region en `connectivity_metrics.json`.
8. Puntos del puente: total unico en caminos analizados = 21.
9. Longitud: reportada por region en la tabla y JSON.
10. Densidad del puente: reportada por region y agregada en `connectivity_metrics.json`.
11. Eliminar unicamente el puente desconectaria la region: columna `Desconecta al remover camino`; es una prueba sobre el grafo eps=0.35 m.
12. Problema principal: combinacion de conectividad y densidad. Las regiones externas poseen menor soporte, pero siguen conectadas por caminos espaciales validos bajo el eps productivo.
