# Raw vs Voxel Connectivity Validation

Nube RAW: `C:\Users\Fabian Matus\OneDrive\Escritorio\harness_con_separacion_de_proyectos\projects\ForestVol\data\processed\971d6e25-8ff0-41d2-8784-c981dec7ccbf\point_cloud.ply`

No se reconstruyo ni se modifico pipeline productivo. Se analizaron capsulas locales de radio `0.3` m alrededor de los contactos detectados en `local_bridge_validation`, siempre con conectividad `eps = 0.35` m.

## Resultado por region

| Region | RAW conectada | Componentes RAW | Primer voxel fusionado | Max voxel separado | Distancia minima RAW | Huecos RAW | Puntos RAW zona |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0 | True | 1 | 0.01 | None | 0.0 | 0 | 1397 |
| 1 | True | 1 | 0.01 | None | 0.0 | 0 | 442 |
| 2 | True | 1 | 0.01 | None | 0.0 | 0 | 1802 |
| 3 | False | 2 | None | 0.1 | 0.43753105613252696 | 1 | 851 |
| 4 | True | 1 | 0.01 | None | 0.0 | 0 | 2956 |
| 5 | True | 1 | 0.01 | None | 0.0 | 0 | 3191 |
| 6 | True | 1 | 0.01 | None | 0.0 | 0 | 2762 |
| 7 | True | 1 | 0.01 | None | 0.0 | 0 | 613 |

## Barrido voxel

| Region | 0.01 | 0.02 | 0.03 | 0.04 | 0.05 | 0.06 | 0.07 | 0.08 | 0.10 |
|---:|---|---|---|---|---|---|---|---|---|
| 0 | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada |
| 1 | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada |
| 2 | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada |
| 3 | separada | separada | separada | separada | separada | separada | separada | separada | separada |
| 4 | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada |
| 5 | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada |
| 6 | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada |
| 7 | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada | fusionada |

## Conclusion obligatoria

1. Superficie continua en RAW: `7/8` contactos ya estan conectados en RAW bajo eps=0.35 m.
2. Voxelizacion crea nuevas uniones: regiones `[]` pasan de separadas en RAW a fusionadas tras voxelizar. Lista vacia significa que no se observo creacion nueva por voxelizacion.
3. Tamano minimo de voxel que fusiona: `critical_voxel_threshold.csv`.
4. Maximo voxel que conserva separacion: `critical_voxel_threshold.csv`.
5. Si la mayoria ya esta conectada en RAW, el origen principal corresponde a la reconstruccion fotogrametrica/NodeODM; si aparecen solo despues del voxel, corresponde al procesamiento posterior.

Los overlays: RAW gris; voxel verde si la zona esta conectada, rojo si permanece separada.
