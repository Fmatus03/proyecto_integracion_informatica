# Auditoria cientifica de mecanismo fotogrametrico
## Alcance
Esta auditoria es offline. No modifica pipeline productivo, no reconstruye imagenes, no ejecuta NodeODM y no cambia parametros. Lee artefactos existentes y reutiliza las regiones espurias ya localizadas por auditorias previas.
## Artefactos disponibles
- Artefactos inventariados: `322`.
- Artefactos que pertenecen directamente a la ultima sesion `971d...`: `1`.
- Artefactos OpenSfM/NodeODM encontrados en cache local historica: `13`.
- Inventario completo: `artifact_inventory.csv` y `artifact_inventory.json`.

### Limitacion critica de trazabilidad por camara
Para la ultima sesion auditada `971d6e25-8ff0-41d2-8784-c981dec7ccbf` se encontro el `point_cloud.ply`, pero no un paquete completo de `reconstruction.json`, `tracks`, `depth maps` o `opensfm` asociado a esa misma corrida dentro de los artefactos disponibles. Por eso las auditorias de soporte por camara y matching quedan disenadas y documentadas, pero no pueden demostrar causalidad puntual por camara sobre la ultima nube.
## Bateria de auditorias implementada
| Auditoria | Pregunta | Metricas | Entregables | Estado |
|---|---|---|---|---|
| Inventario ODM/OpenSfM | Que evidencia existe realmente? | rutas, tamano, utilidad, pertenencia a ultima sesion | artifact_inventory.csv/json | implementada |
| Continuidad RAW en contactos | La geometria adicional ya esta en RAW? | componentes eps=0.35, puntos por crop, cortes previos | region_mechanism_metrics.csv | implementada |
| Densidad local | Las uniones tienen soporte local bajo/alto? | vecinos r=0.20, kdist20 | density_histogram.png, raw_density_overlay.ply | implementada |
| Normales | Las superficies son coherentes o caoticas? | abs(dot normal local) | normal_consistency_histogram.png | implementada |
| Curvatura | Son superficies suaves/interpoladas o bordes bruscos? | lambda_min/sum(lambda) | curvature_histogram.png | implementada |
| Espesor/planitud | Hay laminas artificiales o superficies gruesas? | thickness p05-p95, planarity_ratio | mechanism_metrics.json | implementada |
| Soporte fotogrametrico por camara | Cuantas camaras observan cada region? | observaciones por punto, cobertura angular | disenada | bloqueada por falta de tracks/depth de la ultima sesion |
| Matching/depth maps | La union nace en MVS o en SfM/matching? | profundidad por imagen, reproyeccion, consistencia multi-vista | disenada | bloqueada por falta de depth/tracks de la ultima sesion |

## Resultados por region
| Region | pts RAW contacto | comps eps=.35 | densidad mediana | kdist20 mediana | curvatura mediana | coherencia normales | espesor p05-p95 | conectada RAW previa |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | 4621 | 1 | 752.00 | 0.0316 | 0.030436 | 0.8377 | 0.2264 | True |
| 1 | 801 | 1 | 168.00 | 0.0537 | 0.024664 | 0.6713 | 0.2749 | True |
| 2 | 3420 | 1 | 516.00 | 0.0395 | 0.043004 | 0.7109 | 0.2376 | True |
| 3 | 1698 | 1 | 188.00 | 0.0479 | 0.050002 | 0.6422 | 0.3638 | False |
| 4 | 9130 | 1 | 1523.00 | 0.0217 | 0.085854 | 0.6659 | 0.3251 | True |
| 5 | 7012 | 1 | 776.00 | 0.0292 | 0.014351 | 0.6680 | 0.3097 | True |
| 6 | 5337 | 1 | 759.00 | 0.0310 | 0.013918 | 0.7110 | 0.2018 | True |
| 7 | 2918 | 1 | 866.50 | 0.0276 | 0.014411 | 0.5808 | 0.2796 | True |

## Comparacion contactos vs core del castillo
- Puntos core muestreados: `50000`; puntos union de contactos: `34090`.
- Densidad mediana r=0.20 m: core `143.0`, contactos `831.0`.
- kdist20 mediana: core `0.07739081347834545`, contactos `0.029951342383783552`.
- Curvatura mediana: core `0.04093036898398728`, contactos `0.032443254438337746`.
- Coherencia normal mediana: core `0.8355224024796091`, contactos `0.6854354007459444`.

## Clasificacion de conclusiones
| Afirmacion | Clasificacion | Evidencia |
|---|---|---|
| La union geometrica ya existe en RAW | Hecho demostrado | 7/8 regiones estaban conectadas en RAW en la auditoria raw-vs-voxel; esta auditoria reutiliza esas zonas y no ejecuta voxelizacion productiva. |
| Voxelizacion como mecanismo creador | Hecho demostrado negativo | La auditoria raw-vs-voxel no encontro ninguna region que pasara de separada a fusionada entre 0.01 y 0.10 m. |
| Densificacion/MVS o nube densa como origen observable | Evidencia fuerte | La geometria adicional esta en point_cloud.ply, que es el producto denso descargado desde NodeODM; no hay evidencia de que etapas posteriores la creen. |
| Soporte local geometrico distinto en contactos | Evidencia moderada | Comparacion RAW-vs-RAW. Mediana vecinos r=0.20 m: contactos=831.0, core=143.0; kdist20 mediana contactos=0.029951342383783552, core=0.07739081347834545. |
| Errores de matching especificos por camara | Hipotesis no demostrable con los artefactos disponibles | No se encontro reconstruction/tracks/depth maps de la ultima corrida 971d... que permita asignar cada punto denso a camaras o matches. |
| Reconstruccion de zonas ocluidas/interpolacion | Hipotesis con evidencia geometrica indirecta | Se miden espesor, curvatura, normales y planitud en las zonas de contacto, pero sin depth maps/tracks no se puede atribuir causalidad interna exacta. |

## Criterios de aceptacion/rechazo por mecanismo
- Densificacion MVS: aceptable como mecanismo observable si la geometria esta en `point_cloud.ply` RAW y no en etapas posteriores. Resultado: evidencia fuerte, pero no se puede aislar algoritmo interno exacto sin depth maps.
- Interpolacion/reconstruccion de superficies: evidencia moderada si las zonas de contacto son continuas, planas/suaves y con espesor laminar. Resultado: revisar `thickness`, `curvature` y overlays.
- Errores de matching: no demostrable con los datos actuales; requiere tracks/reconstruction/depth asociados a la misma corrida.
- Multiples vistas/cobertura baja: no demostrable con los datos actuales; requiere poses y visibilidad por punto de la misma corrida.
- Procesamiento posterior: rechazado por auditorias previas y por la presencia de la union en RAW.

## Visualizaciones
- `raw_contact_regions_overlay.ply`: RAW gris + regiones de contacto rojas.
- `contact_density_overlay.ply`: RAW gris + densidad local en contactos.
- `raw_density_overlay.ply`: nube RAW coloreada por densidad.
- `views/raw_contact_front.png`, `side`, `top`, `iso`.
- Histogramas: `density_histogram.png`, `kdist20_histogram.png`, `curvature_histogram.png`, `normal_consistency_histogram.png`.
