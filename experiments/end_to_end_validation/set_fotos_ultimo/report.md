# E2E Validation with set_fotos_ultimo

## Alcance
Pipeline completo desde imagenes con NodeODM sobre `set_fotos_ultimo`. La unica insercion experimental fue `obb_plus_curvature` inmediatamente antes del PDI. No hubo busqueda ni ajuste de parametros.

## Configuracion
- Algoritmo: `obb_plus_curvature`
- `obb_percentile`: `80`
- `curvature_percentile`: `80`

## Comparacion
| Caso | Volumen m3 | Dif. vs real m3 | Error % | Dif. vs benchmark m3 |
|---|---:|---:|---:|---:|
| pipeline_original_reference | 234.0469 | 114.3069 | 95.462586 |  |
| benchmark_winner_reference | 121.2031 | 1.4631 | 1.221897 | 0.0 |
| set_fotos_ultimo_e2e_with_winner_filter | 123.9844 | 4.2444 | 3.54468 | 2.7813 |

## Validaciones
- Session ID: `a1ae51a5-1d9e-4c73-9e24-600321d26eb4`
- NodeODM task: `e67aa093-e1b2-4a61-92b7-cf8c9073b857`
- Scale factor reconstructed ArUco: `0.56331326`
- Puntos antes del filtro: `48684`
- Puntos despues del filtro: `19788`
- Componentes despues del filtro eps=0.35: `2`
- Volumetria completada: `True`
- Diferencia absoluta vs benchmark: `2.7813` m3

## Entregables
- `pipeline_output.ply`
- `filtered_cloud.ply`
- `overlay_before_after.ply`
- `front.png`, `side.png`, `top.png`, `iso.png`
- `metrics.json`, `comparison.csv`, `comparison.json`

