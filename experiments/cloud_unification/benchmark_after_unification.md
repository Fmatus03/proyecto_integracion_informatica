# Benchmark After Cloud Unification

Benchmark ejecutado usando exclusivamente `CloudProvider -> data/processed/<session>/point_cloud.ply`.

| Dataset | SHA256 | Puntos | Volumen nuevo | Error % | Confidence | Gates P/W/F | Volumen benchmark antiguo | Volumen productivo antiguo |
|---|---|---:|---:|---:|---|---|---:|---:|
| set1 | `99c67aeed8fe...` | 401873 | 69.8281 | 41.6836 | 100.0 HIGH | 12/0/0 | 97.375 | 69.8281 |
| set2 | `4ede2ae47fd5...` | 371766 | 39.0156 | 67.4164 | 25.0 CRITICAL | 7/0/5 | 132.671875 | 39.0156 |

## Validacion de equivalencia

Cada fila fue validada antes de ejecutar volumetria. Si SHA256, ruta canonical, cantidad de puntos, bbox o centroide no coincidian con la fuente productiva, el benchmark abortaba.

## Decision

- Equivalencia benchmark-produccion: `True`
- PDI, DBSCAN, NodeODM, OpenSfM y parametros no fueron modificados.
