# Pipeline Stage Geometry Audit

Nube base: `C:\Users\Fabian Matus\OneDrive\Escritorio\harness_con_separacion_de_proyectos\projects\ForestVol\data\processed\971d6e25-8ff0-41d2-8784-c981dec7ccbf\point_cloud.ply`

No se ejecuto NodeODM ni se modifico pipeline productivo. Esta auditoria llama funciones existentes sobre la nube ya generada y conserva los parametros productivos. Para comparar coordenadas, la nube NodeODM se analiza tambien en metros aplicando el factor ya auditado `0.54611448`.

## Etapas auditadas

| Etapa | Puntos | Conservado vs anterior | Componentes | AABB XYZ | Hull m3 | Densidad mediana r0.20 |
|---|---:|---:|---:|---|---:|---:|
| 01_nodeodm_point_cloud_scaled | 746225 |  | 47 | 17.022, 20.458, 10.308 | 1184.070 | 895.25 |
| 02_after_clean_point_cloud | 737554 | 98.84% | 40 | 12.662, 16.491, 8.719 | 656.042 | 895.25 |
| 03_after_segmentation_voxelization | 48483 | 6.57% | 40 | 12.649, 16.479, 8.683 | 659.307 | 507.31 |
| 04_immediately_before_segment | 737554 | same as clean stage | 40 | 12.662, 16.491, 8.719 | 657.852 | 895.25 |
| 05_after_segment_woodpile_components | 45511 | 6.17% | 1 | 11.131, 10.589, 4.322 | 211.065 | 566.99 |
| 06_pdi_input | 45511 | 100.00% | 1 | 11.131, 10.589, 4.322 | 211.065 | 537.15 |

## Evolucion de regiones externas

Las regiones externas se definieron offline desde las componentes low-support de la auditoria anterior. Para cada etapa se mide si hay puntos dentro de esos vol?menes y si, en la base DBSCAN de esa etapa, pertenecen al componente principal.

| Region | NodeODM | Clean | Voxel | Pre-segment | Post-segment | PDI input |
|---:|---|---|---|---|---|---|
| 0 | connected | connected | connected | connected | fused | fused |
| 1 | connected | connected | connected | connected | fused | fused |
| 2 | fused | fused | fused | fused | fused | fused |
| 3 | fused | fused | fused | fused | fused | fused |
| 4 | fused | fused | fused | fused | fused | fused |
| 5 | fused | fused | fused | fused | fused | fused |
| 6 | fused | fused | fused | fused | fused | fused |
| 7 | fused | fused | fused | fused | fused | fused |

## Conclusion cuantitativa

La tabla de evolucion muestra si las regiones externas ya existen y si estan conectadas antes de la seleccion final. Si una region aparece como `connected` o `fused` en `01_nodeodm_point_cloud_scaled`, la union ya esta presente en el artefacto descargado desde NodeODM. Si aparece separada antes y conectada despues de `03_after_segmentation_voxelization`, la fusion nace por la voxelizacion/DBSCAN.

Los overlays usan el mismo sistema de coordenadas: gris = puntos de la etapa, rojo = zonas externas low-support detectadas en la nube final. La secuencia `stage_evolution_iso.gif` permite ver la evolucion etapa por etapa.
