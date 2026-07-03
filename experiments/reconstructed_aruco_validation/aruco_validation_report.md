# Validacion visual y cuantitativa del detector ArUco 3D

No se modifico el pipeline, NodeODM, OpenSfM, DBSCAN, PDI ni parametros. Se trabajo sobre la ultima nube reconstruida existente.

## Fuente

- Nube reconstruida: `C:\Users\Fabian Matus\OneDrive\Escritorio\harness_con_separacion_de_proyectos\projects\ForestVol\data\processed\ecd0f8b7-64f5-437b-9048-2ae83609e8e7\point_cloud.ply`
- Nube segmentada usada solo para overlay visual: `C:\Users\Fabian Matus\OneDrive\Escritorio\harness_con_separacion_de_proyectos\experiments\hito_0_5_close\dataset_definitivo_run_2\selected_pdi_input.ply`
- Puntos raw: `1786481`
- Puntos castillo segmentado: `141274`
- Puntos blanco/negro antes del muestreo: `769385`
- Puntos usados por detector tras limite: `250000`
- Componentes conectados evaluados: `22`
- Candidatos aceptados: `4`

## Formula de confidence

```text
confidence = square_ratio * max(0, 1 - flatness_ratio) * min(1, point_count / 500) / (1 + distance_to_expected_center / marker_size_m)
```

- Aumenta con `square_ratio` cercano a 1.
- Aumenta con `flatness_ratio` cercano a 0.
- Aumenta con cantidad de puntos hasta saturar en 500.
- Disminuye con distancia al centro GCP esperado `(0.5, 0.5, 0.0)`.
- No hay pesos adicionales: los terminos se multiplican directamente.
- Umbrales: `side in [0.25, 5.0]`, `square_ratio >= 0.45`, `flatness_ratio <= 0.35`, `point_count >= 80`.

## Parametros

| Parametro | Valor |
|---|---:|
| `max_candidate_points` | `250000` |
| `min_candidate_points` | `80` |
| `color_saturation_tolerance` | `45` |
| `dark_threshold` | `80` |
| `bright_threshold` | `175` |
| `voxel_size_units` | `0.1` |
| `min_square_ratio` | `0.45` |
| `max_flatness_ratio` | `0.35` |
| `min_side_ratio` | `0.25` |
| `max_side_ratio` | `5.0` |

## Candidatos aceptados

| ID | Puntos | Centroide | Dist GCP | Lado | Width | Height | Square | Flatness | Normal | Confidence |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---|---:|
| 1 | 1849 | `[-0.0149, 0.2941, 0.0392]` | 0.5559 | 2.1049 | 2.2846 | 1.9251 | 0.8426 | 0.1963 | `[-0.0482, -0.1013, 0.9937]` | 0.435249 |
| 2 | 283 | `[7.8480, 0.9115, 4.8804]` | 8.8307 | 1.0405 | 1.4153 | 0.6656 | 0.4703 | 0.0419 | `[-0.0893, 0.0507, -0.9947]` | 0.025944 |
| 3 | 228 | `[6.7403, 1.2868, 4.8380]` | 7.9351 | 1.2083 | 1.6563 | 0.7603 | 0.4591 | 0.0423 | `[0.0313, -0.0364, 0.9988]` | 0.022436 |
| 4 | 115 | `[5.7653, 10.0841, 0.2538]` | 10.9382 | 1.2226 | 1.6167 | 0.8284 | 0.5124 | 0.2814 | `[0.0691, -0.0737, 0.9949]` | 0.007094 |

## Candidato ganador

- Candidate ID: `1`
- Puntos usados: `1849`
- Lado reconstruido: `2.104863` unidades
- Factor escala: `0.47509019` m/unidad
- Confidence: `0.435249`

| Termino | Valor |
|---|---:|
| square_ratio | 0.842640 |
| max(0, 1 - flatness_ratio) | 0.803661 |
| min(1, point_count / 500) | 1.000000 |
| 1 + distance / marker_size | 1.555883 |
| confidence final | 0.435249 |

## Diagnostico del candidato ganador

- ¿El candidato corresponde visualmente al ArUco real? **Si, con reservas.** En `views/iso.png` y `views/top.png` el candidato rojo aparece junto al castillo, en la zona esperada del marcador/GCP, separado de los candidatos lejanos. La evidencia cuantitativa lo respalda: centroide `[-0.0149, 0.2941, 0.0392]`, distancia al centro GCP esperado `0.5559`, `1849` puntos y normal casi vertical `[-0.0482, -0.1013, 0.9937]`.
- ¿Esta completo o parcial? **Parcial/expandido.** El lado medido es mayor que el marcador real y `square_ratio=0.842640`, no un cuadrado perfecto.
- ¿Esta contaminado con puntos externos? **Si, moderadamente.** `plane_thickness=0.448560` y `flatness_ratio=0.196339` indican que no es una lamina limpia.
- ¿El plano esta correctamente ajustado? **Aceptable pero no ideal.** Pasa el umbral de planitud, pero el espesor debe revisarse visualmente.
- ¿La caja utilizada coincide con el borde del ArUco? **No perfectamente.** La caja azul es robusta por percentiles y puede incluir puntos externos por contaminacion/reconstruccion parcial.

## Archivos generados

- `detected_aruco.ply`
- `scene_with_aruco_overlay.ply`
- `aruco_candidates.ply`
- `aruco_metrics.json`
- `aruco_candidates.csv`
- `views/front.png`, `back.png`, `left.png`, `right.png`, `top.png`, `iso.png`

## Respuesta objetiva

El detector encontro el candidato que visualmente corresponde al sector del ArUco real reconstruido, pero la evidencia muestra que esta parcial o contaminado. No hay un candidato alternativo mejor: los demas estan mucho mas lejos del GCP esperado (`7.94` a `10.94` unidades), tienen menos puntos (`115` a `283`) y menor confidence (`0.0071` a `0.0259`) frente al candidato seleccionado (`0.435249`).
