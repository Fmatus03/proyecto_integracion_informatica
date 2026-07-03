# Comparacion critica RAW vs selected_pdi_input

Session ID: `ecd0f8b7-64f5-437b-9048-2ae83609e8e7`. NodeODM Task ID: `ba72bb1c-f0fc-491c-8d80-71a0bb97e3d2`.

Volumen PDI: `946.0781 m3`; error: `690.110322%`.

## Hallazgo principal

`selected_pdi_input` conserva una envolvente de `[23.552737, 22.492586, 8.354078]` m y un bbox de `4425.672767 m3`. Esa geometria no corresponde a un castillo aislado.

![RAW vs selected](images/07_raw_vs_selected_overlay_xy.png)

## Medidas por etapa

|stage|point_count|bbox_extent_m|bbox_volume_m3|centroid|distance_to_aruco_center_m|distance_to_castle_center_m|
|---|---|---|---|---|---|---|
|RAW Dense Point Cloud|1786481|[32.07781, 38.604008, 21.814888]|27014.074271|[8.357905, 3.959841, 2.751252]|9.015906|1.494014|
|Outlier Removal|1771982|[28.113837, 31.323624, 18.429358]|16229.3943|[8.383536, 3.983113, 2.764115]|9.051108|1.530692|
|Voxelization|146740|[28.099381, 31.294378, 18.38967]|16171.004855|[7.213892, 2.978177, 2.39665]|7.547293|0.112001|
|DBSCAN + Cluster Selection|141274|[23.552737, 22.492586, 8.354078]|4425.672767|[7.321014, 2.945702, 2.392841]|7.63108|0.0|
|PDI|141274|[23.552737, 22.492586, 8.354078]|4425.672767|[7.321014, 2.945702, 2.392841]|7.63108|0.0|
|selected_pdi_input.ply|141274|[23.552737, 22.492586, 8.354078]|4425.672767|[7.321014, 2.945702, 2.392841]|7.63108|0.0|

## Regiones no pertenecientes al castillo en selected_pdi_input

- Huella horizontal seleccionada superior a `23 m x 22 m`, compatible con terreno/fondo alrededor del objeto.
- Cluster dominante exacto `0`: `140388` puntos, caja `23.55 x 19.53 x 8.35 m`; no puede ser solo el castillo.
- Clusters secundarios seleccionados `27` y `48` agregan fragmentos externos, pero el problema principal ya esta dentro del cluster dominante.
