# Root cause scale analysis

Fecha: 2026-07-01

Alcance: investigacion sobre artefactos existentes. No se modifico el pipeline, NodeODM, OpenSfM, DBSCAN, PDI ni parametros. No se generaron reconstrucciones nuevas.

## Decision final

**¿La causa principal de la sobreestimacion del volumen es el sistema de escalado basado en ArUco?**

**SÍ**

La evidencia sostiene que la causa principal no es PDI ni el algoritmo de segmentacion en si, sino la forma en que el pipeline certifica y propaga escala metrica desde ArUco/GCP. En la ultima corrida valida, la nube se trata como si 1 unidad = 1 metro, pero la geometria resultante queda aproximadamente 1.9x a 2.0x sobredimensionada en escala lineal. Ese error lineal se amplifica al cubo en volumen y explica naturalmente los 800-900 m3 observados.

La decision debe leerse con una precision importante: el problema no es solamente `scale_px_per_cm`; el problema productivo es el contrato completo `ArUco detectado -> GCP generado -> scale_certified=True -> point_cloud_scale_m_per_unit=1.0`.

## Artefactos analizados

| Artefacto | Uso |
|---|---|
| `projects/ForestVol/backend/app/services/calibration_service.py` | Deteccion ArUco 2D y `scale_px_per_cm`. |
| `projects/ForestVol/backend/app/services/gcp_service.py` | Generacion de `gcp_list.txt` desde esquinas ArUco. |
| `projects/ForestVol/backend/app/services/nodeodm_client.py` | Envio de imagenes y GCP a NodeODM. |
| `projects/ForestVol/backend/app/api/routes/reconstruction.py` | Propagacion de `scale_certified` a volumetria. |
| `projects/ForestVol/backend/app/services/mesh_service.py` | Aplicacion final de escala a la nube. |
| `experiments/hito_0_5_close/dataset_definitivo_run_1/result.json` | Corrida valida 1. |
| `experiments/hito_0_5_close/dataset_definitivo_run_2/result.json` | Ultima corrida valida. |
| `projects/ForestVol/data/uploads/*/session.json` | Calibracion, GCP y detecciones ArUco persistidas. |
| `projects/ForestVol/data/processed/ecd0f8b7-64f5-437b-9048-2ae83609e8e7/point_cloud.ply` | Nube cruda de la ultima corrida valida. |
| `experiments/hito_0_5_close/dataset_definitivo_run_2/selected_pdi_input.ply` | Nube final entregada a PDI. |
| `projects/ForestVol/set_imagenes+guia/modelo3D+objetos/source/log1_low.zip` | Referencia geometrica del asset de tronco. |

## Parte 1: como se calcula actualmente la escala

### Calibracion 2D por imagen

La deteccion ArUco vive en `calibration_service.py`.

- `_detect_marker()` lee cada imagen, prueba variantes de preprocesamiento y busca ArUco `DICT_4X4_50`, ID `0`.
- `_side_length_px()` calcula las cuatro aristas del marcador en pixeles y devuelve el promedio.
- `scale_px_per_cm = side_px / marker_size_cm`.
- `_homography_px_to_cm()` calcula una homografia 2D desde las esquinas detectadas hacia un cuadrado `[0, marker_size_cm]`.
- `calibrate_image_paths()` junta las detecciones visibles y calcula `scale_px_per_cm` como `np.mean(scale_values)`.

Respuestas puntuales:

| Pregunta | Respuesta |
|---|---|
| ¿Donde se calcula? | `calibration_service.py`, especialmente `_detect_marker()`, `_side_length_px()` y `calibrate_image_paths()`. |
| ¿Que informacion ArUco usa? | Esquinas 2D en pixeles, ID del marcador, tamano fisico configurado (`calibration_marker_size_cm`). |
| ¿Como obtiene el factor? | `side_px / marker_size_cm`, luego promedio aritmetico simple. |
| ¿Se calcula por imagen? | Si, una deteccion por imagen si se encuentra el ArUco. |
| ¿Se calcula por marcador? | Solo marcador ID 0; no hay multiples IDs. |
| ¿Se promedian distancias? | Si, se promedian las 4 aristas por deteccion; despues se promedian las detecciones. |
| ¿Se usan todas las detecciones? | Para calibracion 2D, todas las detecciones visibles aceptadas por `_detect_marker()`. Para GCP, se filtran por calidad. |
| ¿Se ponderan observaciones? | No. No hay ponderacion por oblicuidad, distancia, area, reproyeccion o estabilidad. |
| ¿Como transforma finalmente la nube? | No usa `scale_px_per_cm` para escalar 3D. La volumetria usa `point_cloud_scale_m_per_unit=1.0` si `scale_evidence.scale_certified=True`. |

### GCP ArUco para NodeODM

La generacion GCP vive en `gcp_service.py`.

- `_marker_world_corners(marker_size_m)` define cuatro puntos 3D: `(0,0,0)`, `(1,0,0)`, `(1,1,0)`, `(0,1,0)` para marcador de 100 cm.
- `generate_aruco_gcp_file()` detecta ArUco en imagenes, filtra detecciones por:
  - `min_side_px=60`
  - `max_side_cv=0.45`
  - `min_area_ratio=0.18`
- Escribe `gcp_list.txt` con cabecera `EPSG:3857`.
- Cada deteccion aceptada aporta 4 observaciones: coordenada mundo + pixel + nombre de imagen + nombre de punto.

En la corrida definitiva:

| Medida | Valor |
|---|---:|
| Imagenes | 95 |
| Detecciones ArUco 2D persistidas | 61 |
| Detecciones GCP aceptadas | 39 |
| Detecciones GCP rechazadas | 22 |
| Observaciones GCP escritas | 156 |
| Marcador fisico declarado | 1.0 m |

### Envio a NodeODM

`nodeodm_client.py` adjunta el `gcp_list.txt` como archivo adicional en el campo `images`.

Las opciones base de reconstruccion no incluyen un parametro explicito `gcp` agregado por el cliente; el GCP viaja como archivo. En trazas historicas de NodeODM si aparece `bundle_use_gcp: true` y mensajes como `GCP points will be used for georeferencing`, por lo que NodeODM puede procesarlo. Sin embargo, para la corrida definitiva local solo quedaron `point_cloud.ply` y `gcp_list.txt`; no quedo descargado el arbol OpenSfM completo para auditar errores GCP de esa corrida.

### Escala final aplicada a la nube

En `reconstruction.py`:

- `_metric_point_cloud_scale_from_session()` devuelve `(1.0, reason)` si `scale_evidence.scale_certified` es true.
- `scale_evidence.scale_certified` pasa a true si `generate_aruco_gcp_file()` no falla.

En `mesh_service.py`:

- `_resolve_metric_point_cloud_scale()` rechaza volumetria sin escala 3D certificada.
- Si recibe `point_cloud_scale_m_per_unit=1.0`, `generate_preliminary_volumetry()` ejecuta `point_cloud.scale(1.0, center=(0,0,0))`.

Conclusion de Parte 1: el pipeline no mide el ArUco reconstruido en 3D antes de declarar la nube metrica. Declara escala certificada por existencia de GCP generado y asume 1 unidad = 1 metro.

## Parte 2: verificacion geometrica sin usar volumen como criterio principal

### Nube final seleccionada para PDI

| Corrida | Session ID | Puntos PDI | BBox final XYZ tratado como m |
|---:|---|---:|---|
| 1 | `d78e0ca6-6259-47b1-89a7-2278acf95119` | 119692 | `[20.257236, 21.318060, 8.767439]` |
| 2 | `ecd0f8b7-64f5-437b-9048-2ae83609e8e7` | 141274 | `[23.552737, 22.492586, 8.354078]` |

Estas dimensiones son geometricamente excesivas para un castillo formado con el asset de tronco disponible. El asset `log1_low.obj` tiene bbox `[9.893066, 1.931237, 5.899400]` en sus unidades fuente. Al aplicar un factor lineal cercano a 0.5 sobre la ultima nube, la caja final queda aproximadamente `[11.826, 11.293, 4.194]`, que es mucho mas consistente con una pila construida a partir de troncos de longitud ~9.89 que una caja de 23.55 x 22.49 x 8.35.

### ArUco reconstruido en 3D

Se busco el marcador en la nube cruda `point_cloud.ply` mediante color blanco/negro de baja saturacion y proximidad al origen GCP.

| Medicion | Resultado |
|---|---:|
| Puntos crudos | 1786481 |
| BBox cruda | `[32.077810, 38.604008, 21.814888]` |
| Puntos blanco/negro candidatos | 269900 |
| Componente blanco/negro cerca de origen | 2037 puntos |
| Extension PCA del componente cerca de origen | `[3.1257, 1.8010, 0.6522]` |
| Centroide del componente | `[0.0280, 0.3970, 0.0774]` |

Esta no es una medicion limpia de lado ArUco, porque el componente esta contaminado por entorno/suelo o puntos vecinos. Aun asi, el resultado es compatible con sobredimensionamiento: alrededor del origen GCP aparece una estructura blanco/negro de escala mayor que 1 m y no un cuadrado 1 x 1 m limpio. La conclusion no depende solo de este punto porque la nube no preserva el ArUco como plano segmentable sin ambiguedad.

### Tronco y diametros

No hay en los artefactos existentes una anotacion manual de extremos de troncos o diametros reales por tronco. No se hizo intervencion manual ni reconstruccion nueva. La referencia disponible es el asset `log1_low.obj`:

| Referencia | Extension XYZ |
|---|---|
| `log1_low.obj` | `[9.893066, 1.931237, 5.899400]` |

La comparacion directa con la nube final indica que la nube seleccionada queda aproximadamente el doble de grande en planta. Esto es consistente con H1. No se puede afirmar una medicion individual automatica robusta de diametro de tronco con los artefactos actuales sin agregar un detector/segmentador nuevo, lo que excederia la restriccion de no modificar ni generar nuevos experimentos.

## Parte 3: estabilidad del escalado

### Escala ArUco 2D persistida

Las dos corridas usan el mismo set de imagenes, por eso la calibracion 2D es identica.

| Metrica `scale_px_per_cm` | Valor |
|---|---:|
| Detecciones | 61 |
| Promedio | 0.672392 |
| Mediana | 0.661100 |
| Desviacion estandar | 0.151947 |
| Minimo | 0.417200 |
| Maximo | 0.936700 |
| Rango max/min | 2.245 |

El promedio simple no es una metrica estable: mezcla observaciones cercanas y lejanas del marcador, con perspectiva y tamanos en pixel muy distintos. Tampoco corresponde a escala 3D de la nube; es una escala 2D imagen-centimetro.

### Detecciones GCP aceptadas

| Metrica GCP aceptado (`side_px/100`) | Valor |
|---|---:|
| Detecciones aceptadas | 39 |
| Observaciones GCP | 156 |
| Promedio | 0.764757 |
| Mediana | 0.768379 |
| Desviacion estandar | 0.103665 |
| Minimo | 0.608653 |
| Maximo | 0.936701 |
| Rechazadas | 22 |

Incluso tras filtro de calidad, la escala aparente del marcador varia 54% entre minimo y maximo. Eso no invalida GCP por si solo, pero demuestra que cualquier promedio 2D de ArUco es inadecuado para certificar unidades 3D.

### Estabilidad entre corridas

| Corrida | BBox final XYZ | Factor lineal implicito por volumen solo como chequeo | Inverso |
|---:|---|---:|---:|
| 1 | `[20.257236, 21.318060, 8.767439]` | 0.529635 | 1.888094 |
| 2 | `[23.552737, 22.492586, 8.354078]` | 0.502077 | 1.991724 |

El chequeo por volumen no se usa como medicion primaria de geometria, pero sirve como consistencia: ambas corridas apuntan a un error lineal cercano a 2x. Ese orden de magnitud coincide con la caja geometrica sobredimensionada.

## Parte 4: factibilidad de reconstruir ArUco directamente en 3D

Factible, pero no demostrado como automatico con el pipeline actual.

El ArUco tiene propiedades fuertes:

- cuadrado;
- plano;
- tamano conocido: 1.0 m;
- color blanco/negro de alto contraste;
- proximidad al castillo;
- coordenadas GCP esperadas cerca de un plano local.

La nube cruda conserva suficientes puntos de color para buscar candidatos, pero la deteccion directa necesita un metodo especifico:

1. Filtrar puntos por color blanco/negro y baja saturacion.
2. Buscar componentes conectados cerca de la region esperada.
3. Ajustar planos con RANSAC.
4. Proyectar puntos del plano a 2D local.
5. Ajustar un cuadrado robusto o detectar bordes del patron.
6. Medir lado reconstruido y calcular `factor = 1.0 / lado_reconstruido`.

El intento exploratorio encontro componentes candidatos, pero no un cuadrado 1 x 1 limpio. Eso no refuta H1; muestra que el pipeline actual no esta midiendo la escala 3D que necesita medir.

## Parte 5: nueva estrategia si H1 queda demostrada

La estrategia propuesta es tecnicamente correcta con ajustes:

1. Reconstruir la nube sin confiar aun en escala final.
2. Detectar en 3D el plano/candidato del ArUco.
3. Ajustar el cuadrado en el plano reconstruido.
4. Medir el lado reconstruido robustamente.
5. Calcular un unico factor `factor = lado_real_m / lado_reconstruido_unidades`.
6. Escalar toda la nube con ese factor.
7. Registrar evidencia: lado reconstruido, residual del plano, residual del cuadrado, numero de puntos, confianza y factor.

Recomendacion superior: no depender de una unica medicion si hay varias observaciones posibles. Usar estimador robusto:

- detectar multiples candidatos/patches del marcador si existen;
- rechazar outliers por residual planar y razon de lados;
- usar mediana o media recortada;
- reportar incertidumbre;
- bloquear volumetria si no se puede medir el marcador en 3D.

No se debe seguir usando `scale_px_per_cm` como escala metrica de la nube. Tampoco basta con que `gcp_list.txt` exista; la certificacion debe depender de evidencia 3D posterior o de errores GCP/OpenSfM auditables.

## Parte 6: hipotesis alternativa

H1 queda demostrada como causa principal probable y accionable. La siguiente hipotesis no desaparece: la reconstruccion/segmentacion todavia puede incluir entorno conectado. Pero esa hipotesis no explica por si sola que las dimensiones del objeto aceptado como "metros" queden cerca de 2x y que el volumen se dispare en un factor compatible con el cubo de ese error.

La siguiente investigacion, despues de corregir escala, debe reevaluar segmentacion en unidades corregidas. Voxel, DBSCAN y PDI usan parametros en metros; si la escala cambia, sus parametros efectivos tambien cambian.

## Evidencia clave resumida

| Evidencia | Interpretacion |
|---|---|
| `scale_px_per_cm` promedio 0.672392 con rango 0.4172-0.9367 | La escala 2D ArUco es inestable y no certifica 3D. |
| GCP aceptado promedio 0.764757 con rango 0.608653-0.936701 | Aun filtrado, el marcador observado varia mucho entre imagenes. |
| `scale_certified=True` se activa por GCP generado | Certifica por existencia de archivo, no por medicion 3D verificada. |
| Volumetria aplica `point_cloud_scale_m_per_unit=1.0` | La nube se consume como si ya estuviera en metros. |
| BBox final ultima corrida `[23.55, 22.49, 8.35]` | Geometria fisica sobredimensionada para el castillo esperado. |
| Factor lineal consistente entre corridas ~0.50-0.53 | Error lineal cercano a 2x explica el volumen al cubo. |
| ArUco 3D no aparece como cuadrado limpio 1 x 1 verificado | El sistema actual no valida la escala en la nube reconstruida. |

## Conclusion

**SÍ.** La causa principal de la sobreestimacion del volumen es el sistema de escalado basado en ArUco/GCP, especificamente la certificacion y propagacion de escala metrica sin verificar el tamano reconstruido en 3D. La segmentacion y PDI pueden tener problemas secundarios, pero la evidencia cuantitativa muestra un error lineal coherente con la sobreestimacion cubica del volumen.
