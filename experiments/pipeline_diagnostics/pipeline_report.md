# Pipeline Cloud Diagnostics

Restricciones respetadas: no se modifico PDI, NodeODM, OpenSfM ni parametros productivos. El diagnostico replica la preparacion productiva solo para medir.

## Decision diagnostica

### set1

- Primer punto de divergencia: `nodeodm_raw_point_cloud`.
- Cuello de botella: OpenSfM/NodeODM reconstruction output differs before productive filtering.
- Puntos productivos PDI: 15799 vs benchmark: 19879 (ratio 0.794758).
- BBox productivo: [7.105177, 9.493006, 6.497416] m vs benchmark: [8.984155, 14.980714, 5.088158] m.
- Densidad productiva: 36.050418 pts/m3 vs benchmark: 29.028473 pts/m3.
- Chamfer: 1.669309 m; Hausdorff: 5.374957 m.
- Solapamiento productivo->benchmark @0.25m: 0.0.
- ICP fitness: 0.775233; ICP RMSE: 0.127069 m.

OpenSfM / NodeODM:

- task UUID: 4d324ed3-3ec9-446b-9976-39285560b6b5
- camaras reconstruidas: 18
- landmarks reconstruidos: 12024
- tracks/observaciones: 31671
- reprojection error px: 0.4519559220438218

Filtros productivos medidos:

- statistical_outlier: 401873 -> 398562 puntos; eliminado 0.82%.
- segmentacion DBSCAN: selecciono 15799 puntos; labels [14, 0]; razon plausible_woodpile_components.

### set2

- Primer punto de divergencia: `nodeodm_raw_point_cloud`.
- Cuello de botella: OpenSfM/NodeODM reconstruction output differs before productive filtering.
- Puntos productivos PDI: 3278 vs benchmark: 26113 (ratio 0.125531).
- BBox productivo: [8.137795, 9.814177, 6.736833] m vs benchmark: [6.79913, 9.099231, 6.277325] m.
- Densidad productiva: 6.092458 pts/m3 vs benchmark: 67.239444 pts/m3.
- Chamfer: 6.787717 m; Hausdorff: 10.237346 m.
- Solapamiento productivo->benchmark @0.25m: 0.0.
- ICP fitness: 0.0; ICP RMSE: 0.0 m.

OpenSfM / NodeODM:

- task UUID: 86f11977-7789-42d8-b4b0-852f623f1df0
- camaras reconstruidas: 28
- landmarks reconstruidos: 14722
- tracks/observaciones: 43113
- reprojection error px: 0.42176454077084424

Filtros productivos medidos:

- statistical_outlier: 371766 -> 364166 puntos; eliminado 2.04%.
- segmentacion DBSCAN: selecciono 3278 puntos; labels [4, 8]; razon plausible_woodpile_components.

## Artefactos

- `pipeline_diagnostics.json`
- `pipeline_metrics.csv`
- `cloud_comparison.json`
- `cloud_statistics.json`
- `*_cloud_overlay.png`
- `*_xyz_histograms.png`
- `point_count_evolution.png`
- `bbox_volume_evolution.png`