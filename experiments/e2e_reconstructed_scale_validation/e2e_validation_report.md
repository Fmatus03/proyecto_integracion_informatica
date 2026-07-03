# E2E reconstructed ArUco scale validation

Estado: **BLOQUEADO POR INFRAESTRUCTURA**

Fecha: 2026-07-01

Dataset solicitado:

`projects/ForestVol/set_imagenes+guia/set_fotos_castillo_de_madera_defnitivo`

Tamaño físico del ArUco usado para la validación: **1.0 m por lado**.

## Alcance ejecutado

Se intentó iniciar la validación E2E sin modificar código, algoritmos, parámetros, NodeODM, OpenSfM, DBSCAN, PDI, segmentación ni reconstrucción.

El bloqueo ocurre antes de generar una nueva nube desde imágenes: NodeODM no está disponible localmente y Docker Desktop/daemon tampoco está corriendo o no expone la API esperada.

Por lo tanto, **no se acepta ningún volumen E2E nuevo**, **no se calcula mejora**, y **no se declara éxito del nuevo contrato de escala** en esta corrida.

## Evidencia del bloqueo

Comprobaciones realizadas:

| Recurso | Resultado |
|---|---|
| `http://localhost:3000/info` | No accesible: `No es posible conectar con el servidor remoto` |
| `http://localhost:3001/info` | No accesible: `No es posible conectar con el servidor remoto` |
| `docker ps` en sandbox | No conecta a `npipe:////./pipe/docker_engine` |
| `docker ps` con permisos elevados | No conecta a `npipe:////./pipe/dockerDesktopLinuxEngine` |

El `docker-compose.yml` del proyecto expone NodeODM como `${NODEODM_PORT:-3001}:3000`, por eso se verificaron ambos puertos relevantes: `3000` y `3001`.

## Validaciones obligatorias

### 1. Detección del ArUco

No ejecutada en una reconstrucción E2E nueva, porque NodeODM no produjo una nube desde el dataset solicitado.

La auditoría visual previa del detector sobre la última nube existente queda disponible como contexto en:

`experiments/reconstructed_aruco_validation/`

Artefactos previos relevantes:

| Artefacto | Ruta |
|---|---|
| ArUco detectado | `experiments/reconstructed_aruco_validation/detected_aruco.ply` |
| Overlay escena/castillo/ArUco | `experiments/reconstructed_aruco_validation/scene_with_aruco_overlay.ply` |
| Todos los candidatos | `experiments/reconstructed_aruco_validation/aruco_candidates.ply` |
| Métricas | `experiments/reconstructed_aruco_validation/aruco_metrics.json` |
| Tabla de candidatos | `experiments/reconstructed_aruco_validation/aruco_candidates.csv` |
| Reporte visual | `experiments/reconstructed_aruco_validation/aruco_validation_report.md` |

Resumen de esa auditoría previa, solo como referencia visual y cuantitativa:

| Métrica | Valor |
|---|---:|
| Candidato seleccionado | 1 |
| Puntos utilizados | 1849 |
| Lado reconstruido | 2.104863488962084 unidades |
| Lado real | 1.0 m |
| Factor estimado | 0.4750901924253072 m/unidad |
| Confidence | 0.4352492312773519 |

Esta auditoría previa **no sustituye** la validación E2E solicitada, porque no reconstruye desde cero el dataset definitivo.

### 2. Escalado

No verificable en E2E.

No existe una nueva nube reconstruida desde el dataset definitivo en esta corrida, por lo que no se puede informar objetivamente:

- factor aplicado a toda la nube,
- dimensiones antes del escalado,
- dimensiones después del escalado.

### 3. Segmentación

No ejecutada en E2E.

No se puede informar de forma válida:

- puntos seleccionados,
- bbox,
- centroid,
- clusters utilizados.

### 4. PDI

No ejecutado en E2E.

No se generaron:

- volumen del convex hull,
- volumen final PDI.

### 5. Resultado final

No hay volumen E2E nuevo.

| Pipeline | Volumen | Error |
|---|---:|---:|
| Escala anterior | 946.0781 m³ | 690.110322 % |
| Nuevo escalado | No ejecutado | No calculable |

Volumen esperado: **119.74 m³**.

La mejora obtenida no puede calcularse todavía porque el pipeline nuevo no produjo un volumen bajo las condiciones solicitadas.

### 6. Estabilidad

No se pudo ejecutar la primera corrida completa, por lo que la segunda corrida queda correctamente marcada como no ejecutada.

| Métrica | Run 1 | Run 2 |
|---|---|---|
| Estado | No ejecutado | No ejecutado |
| Factor de escala | N/A | N/A |
| Volumen | N/A | N/A |
| Error | N/A | N/A |
| Estabilidad | No evaluable | No evaluable |

## Respuestas al criterio de éxito

| Pregunta | Respuesta objetiva |
|---|---|
| ¿El ArUco fue detectado correctamente? | No verificable en E2E. Solo existe auditoría previa sobre una nube ya existente. |
| ¿El nuevo factor de escala fue aplicado? | No verificable. La reconstrucción desde imágenes no comenzó. |
| ¿La nube quedó correctamente escalada? | No verificable. No hay nueva nube E2E. |
| ¿El volumen final disminuyó respecto al pipeline anterior? | No verificable. No se obtuvo volumen nuevo. |
| ¿Cuál es el nuevo error porcentual? | No calculable. |
| ¿El nuevo contrato de escala mejora significativamente la precisión? | No demostrable en esta corrida. |

## Siguiente condición necesaria

Para ejecutar la validación solicitada sin cambiar algoritmos ni parámetros, se necesita levantar Docker Desktop/NodeODM y confirmar que alguno de estos endpoints responda:

- `http://localhost:3001/info`, según el `docker-compose.yml` del proyecto.
- `http://localhost:3000/info`, si se usa un NodeODM externo con ese puerto.

Cuando NodeODM esté disponible, la validación debe repetirse desde cero con el mismo dataset y el mismo tamaño físico de ArUco: **1.0 m**.
