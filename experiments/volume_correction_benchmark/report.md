# Volume Correction Benchmark

## Alcance
Benchmark experimental independiente. No modifica pipeline productivo, NodeODM, OpenSfM ni reconstruye imagenes. Todos los metodos parten de la misma nube RAW escalada y del mismo universo de competencia.

## Entrada comun
- RAW: `C:\Users\Fabian Matus\OneDrive\Escritorio\harness_con_separacion_de_proyectos\projects\ForestVol\data\processed\971d6e25-8ff0-41d2-8784-c981dec7ccbf\point_cloud.ply`
- Input comun de competencia: `C:\Users\Fabian Matus\OneDrive\Escritorio\harness_con_separacion_de_proyectos\experiments\volume_input_audit\selected_volume_cloud.ply`
- Factor de escala aplicado para el experimento: `0.54611448`
- Puntos RAW escalados: `746225`
- Puntos de competencia exactos: `45511`
- Baseline PDI reproducido sobre input comun: `234.0469` m3
Este input es la nube que entra a volumetria y proviene de la RAW escalada; se usa para que el benchmark corrija el exceso real observado, sin modificar el pipeline productivo.

## Criterio
Volumen objetivo: `119.74` m3. Ranking por menor error absoluto, luego menor error porcentual, luego menor complejidad.

## Ganador
- Algoritmo: `obb_plus_curvature`
- Parametros: `{"curvature_percentile": 80, "obb_percentile": 80}`
- Volumen obtenido: `121.2031` m3
- Error absoluto: `1.4631` m3
- Error porcentual: `1.221897` %
- Mejora vs pipeline actual `234.0469` m3: `112.8438` m3 de error absoluto menos (`98.720025` %).

## Top 10
| Rank | Algorithm | Params | Volume | Abs error | % error | Removed % |
|---:|---|---|---:|---:|---:|---:|
| 1 | obb_plus_curvature | `{"curvature_percentile": 80, "obb_percentile": 80}` | 121.2031 | 1.4631 | 1.221897 | 61.554349 |
| 2 | compactness | `{"score_percentile": 55}` | 121.5781 | 1.8381 | 1.535076 | 45.026477 |
| 3 | obb_plus_curvature | `{"curvature_percentile": 90, "obb_percentile": 80}` | 121.8281 | 2.0881 | 1.743862 | 56.733537 |
| 4 | obb_shrink | `{"axis_percentile": 80}` | 122.1094 | 2.3694 | 1.978787 | 51.912724 |
| 5 | obb_plus_curvature | `{"curvature_percentile": 60, "obb_percentile": 80}` | 122.1562 | 2.4162 | 2.017872 | 71.19158 |
| 6 | center_distance | `{"keep_percentile": 60}` | 117.2812 | 2.4588 | 2.053449 | 40.005713 |
| 7 | center_plus_density | `{"center_percentile": 80, "density_percentile": 40}` | 115.0625 | 4.6775 | 3.90638 | 51.003054 |
| 8 | density_filter | `{"radius_m": 0.2, "remove_below_density_percentile": 60}` | 125.4375 | 5.6975 | 4.758226 | 58.755026 |
| 9 | center_distance | `{"keep_percentile": 65}` | 125.5938 | 5.8538 | 4.888759 | 35.009119 |
| 10 | center_plus_density | `{"center_percentile": 70, "density_percentile": 10}` | 126.6562 | 6.9162 | 5.776015 | 37.234954 |

## Entregables
- `ranking.csv`, `ranking.json`, `all_runs.csv`
- `best_configuration.json`, `best_configuration.md`
- `pointclouds/`: input comun y top 10 corregidos
- `overlays/`: verde conservado, rojo eliminado para top 10
- `plots/top20_error.png`, `plots/top20_volume.png`
- `metrics/benchmark_summary.json`
