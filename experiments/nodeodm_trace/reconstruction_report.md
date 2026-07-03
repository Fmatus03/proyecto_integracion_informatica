# Reconstruction Trace Report

Restricciones respetadas: no se modifico PDI, DBSCAN, NodeODM, OpenSfM ni parametros productivos. Esta fase solo inspecciona artefactos existentes.

## Conclusion unica

A) El benchmark y produccion estan usando archivos distintos.

La causa exacta de la no equivalencia es que el benchmark no consumio el `point_cloud.ply` de las sesiones productivas. Los benchmarks usaron artefactos de sesiones/UUIDs NodeODM anteriores y, para PDI, usaron `surface_closure_diagnostics*/poisson_input_cloud.ply`, no el `data/processed/<session>/point_cloud.ply` productivo.

## Evidencia de archivos

### Set 1

- Benchmark session: `a3c36266-f866-402f-8bc8-1c2b59b4a4ce`.
- Benchmark NodeODM UUID: `56396d01-c139-445e-ba50-55644781e877`.
- Produccion session: `b3c14c84-b660-407f-817f-1fc185ce3e9c`.
- Produccion NodeODM UUID: `4d324ed3-3ec9-446b-9976-39285560b6b5`.
- Raw benchmark `point_cloud.ply`: SHA256 `6dda4d260a9cf2c7c9cc722379a3624b20c429b950c1bcd11c8acf29dc32430f`, `301159` puntos.
- Raw produccion `point_cloud.ply`: SHA256 `99c67aeed8feb3ab06bfe0f74c932af67aabbe5ebb0c8736b879c042846af777`, `401873` puntos.
- Nube usada por PDI benchmark: `surface_closure_diagnostics/poisson_input_cloud.ply`, SHA256 `32332ecad9d2bfe4401dcdb1335a646a4b7f5aceaeec7463204108ad1f3c2603`, `19879` puntos.
- Diferencias de parametros densos NodeODM: `0`.
- Raw benchmark vs raw produccion: Chamfer `0.968652 m`, Hausdorff `26.952083 m`.
- Fragmentacion RAW: benchmark `131` componentes; produccion `249` componentes.

### Set 2

- Benchmark session: `b6b04af0-122f-4fcc-af8a-cc553ca5e28d`.
- Benchmark NodeODM UUID registrado en session.json: `002ca5e3-6eca-4aba-b3e2-623f97878136`.
- Produccion session: `723f91e2-b1b5-43f7-b336-6816d8300509`.
- Produccion NodeODM UUID: `86f11977-7789-42d8-b4b0-852f623f1df0`.
- Raw benchmark `point_cloud.ply`: SHA256 `b75c4bbd7b6d60c24cf7a57f12c1a06158a5bcb03d2c476348f55c5fe860d343`, `696994` puntos.
- Raw produccion `point_cloud.ply`: SHA256 `4ede2ae47fd561c67a1de73afcb3adcfc20297164b2084c911ff3785dda6d88b`, `371766` puntos.
- Nube usada por PDI benchmark: `surface_closure_diagnostics_2/poisson_input_cloud.ply`, SHA256 `d19ac428c46ba8b23166eeba364cc45273e95e0b7c5f62bed7cc5065acdd89d7`, `26113` puntos.
- Diferencias de parametros densos NodeODM: `0`.
- Raw benchmark vs raw produccion: Chamfer `2.097365 m`, Hausdorff `13.988097 m`.
- Fragmentacion RAW: benchmark `163` componentes; produccion `43` componentes.

## Verificacion de reutilizacion/cache

- Set 1: no se encontro evidencia de UUID cruzado en `options.json`; benchmark y produccion son tasks distintos.
- Set 2: si hay evidencia de artefacto duplicado/reutilizado dentro de NodeODM:
  - `b6b04.../session.json` registra `nodeodm_task_uuid = 002ca5e3-6eca-4aba-b3e2-623f97878136`.
  - `002ca5e3.../options.json` contiene `name/project_path = 37fe01cd-356f-4776-952a-17e989f8452b`.
  - `002ca5e3.../odm_filterpoints/point_cloud.ply` y `37fe01cd.../odm_filterpoints/point_cloud.ply` tienen el mismo SHA256: `525dffc0ce6e89c19456695196d8547ef3115b11dca1de37eaba19c2d2ebbe55`.

Esto demuestra que al menos el benchmark Set 2 no es una referencia limpia a un unico task NodeODM nuevo; contiene una referencia cruzada/duplicada. Aun asi, la conclusion principal no cambia: el benchmark y produccion no consumen el mismo archivo.

## Configuracion NodeODM

La comparacion automatica de `options.json` muestra `0` diferencias en parametros densos relevantes (`feature_quality`, `pc_quality`, `mesh_size`, `matcher_neighbors`, `end_with`, `depthmap_resolution`). Las diferencias detectadas son identificadores/rutas (`name`, `project_path`, `gcp`), no parametros de reconstruccion densa.

## Respuesta requerida

Benchmark usa exactamente el mismo archivo que produccion: NO.

El benchmark usa:

- Set 1: `data/processed/a3c36266-f866-402f-8bc8-1c2b59b4a4ce/surface_closure_diagnostics/poisson_input_cloud.ply`.
- Set 2: `data/processed/b6b04af0-122f-4fcc-af8a-cc553ca5e28d/surface_closure_diagnostics_2/poisson_input_cloud.ply`.

Produccion usa:

- Set 1: `data/processed/b3c14c84-b660-407f-817f-1fc185ce3e9c/point_cloud.ply`.
- Set 2: `data/processed/723f91e2-b1b5-43f7-b336-6816d8300509/point_cloud.ply`.

DBSCAN no es la causa primaria de la divergencia: las nubes RAW ya difieren por hash, UUID, cantidad de puntos, Chamfer/Hausdorff y fragmentacion antes de cualquier filtrado productivo.

## Artefactos

- `reconstruction_trace.json`
- `reconstruction_diff.json`
- `nodeodm_parameter_diff.json`
- `pointcloud_hashes.json`
- `pointcloud_hashes.csv`
- `nodeodm_task_manifest.json`
- `nodeodm_reuse_check.json`
- `artifact_graph.md`
- `reconstruction_report.md`
- `set1_artifact_cloud_overlay.png`
- `set2_artifact_cloud_overlay.png`
