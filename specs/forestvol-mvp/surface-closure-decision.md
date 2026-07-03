# Surface Closure Decision

Fecha: 2026-06-28
Run arnes: RUN-SURFACE-CLOSURE-01
Actor: orchestrator

## Alcance

Este documento define el criterio tecnico para estabilizar volumetria desde una malla Poisson abierta pero estructuralmente coherente. No usa ground truth para ajustar resultados, no modifica GCP/calibracion, no relanza segmentacion y no reintroduce Alpha Shape como solucion primaria.

## Objetivo

Construir una superficie cerrada, determinista y geometricamente consistente para calcular volumen de la pila/castillo a partir de entradas RGB, marcador ArUco y nube de puntos ya reconstruida, sin metadata, sin asumir EXIF, GPS ni metadata de dron.

## Requisitos

- Comparar Poisson crudo, Poisson recuperado, cierre controlado Poisson, `poisson_vertex_hull` legado y Alpha Shape baseline.
- Medir volumen, area superficial, bounding box, componentes, boundary edges, manifoldness y ratio area/volumen.
- Clasificar boundary edges/loops para distinguir huecos pequenos cerrables, bordes reales/cortes, errores de reconstruccion y discontinuidades estructurales.
- Mantener reproducibilidad con artefactos JSON, PLY y PNG generados por el instrumento diagnostico.
- Reportar ground truth, RF-09 y error solo como referencia externa si existen, nunca como optimizador de la superficie final.

## Restricciones

- No usar ground truth para ajustar resultados.
- No modificar GCP, calibracion ni escala.
- No volver a segmentacion.
- No reintroducir Alpha Shape como solucion primaria.
- No aceptar `watertight = true` como criterio unico.

## Riesgos

- `poisson_vertex_hull` puede sobrecerrar cavidades y producir volumen artificialmente alto.
- Alpha Shape puede variar por alpha y destruir concavidades o detalles de forma.
- Cerrar loops que corresponden a bordes reales del objeto puede sesgar volumen.
- Remeshing previo a diagnostico puede mover fronteras y ocultar discontinuidades estructurales.

## Superficies comparadas

El instrumento `projects/ForestVol/backend/instrument_meshing_diagnostics.py` compara:

- `poisson_raw`: Poisson crudo tras filtro de densidad.
- `poisson_recovered`: Poisson despues de limpieza determinista de componentes/topologia.
- `poisson_controlled_hole_fill`: Poisson recuperado con cierre controlado de loops de frontera.
- `poisson_vertex_hull_legacy_recovery`: envolvente convexa de vertices Poisson, solo diagnostica.
- `alpha_shape_baseline`: baseline historico, no superficie primaria.

Para cada superficie se exportan PLY, PNG de vistas XY/XZ/YZ y metricas JSON: volumen, area, bbox, ratio area/volumen, componentes, bordes frontera, manifoldness y aceptacion.

## Diagnostico estructural

El volumen alto asociado a `poisson_vertex_hull` no debe aceptarse solo porque sea watertight y tenga volumen calculable. La envolvente por hull puede cerrar cavidades, cortes y concavidades como masa solida artificial. Por eso queda degradada a diagnostico y debe rechazarse si cambia bbox o area superficial respecto de Poisson.

Alpha Shape queda como baseline de contraste: puede producir cierre volumetrico, pero su topologia y forma dependen de alpha y no deben gobernar la arquitectura primaria.

La causa de no-watertight en Poisson se diagnostica por loops de boundary edges, clasificados como:

- `hueco_pequeno_cerrable`
- `borde_real_del_objeto_o_corte_de_captura`
- `error_de_reconstruccion`
- `discontinuidad_estructural`

Solo los loops cerrados, pequenos y con bajo impacto de bbox/area pueden cerrarse sin cambiar forma global.

## Resultados Docker

Validacion ejecutada en Docker sobre `forestvol-backend` reconstruido el 2026-06-28. Reporte principal:

`projects/ForestVol/data/processed/b6b04af0-122f-4fcc-af8a-cc553ca5e28d/surface_closure_diagnostics_2/surface_closure_diagnostics.json`

Tabla de superficies:

- `poisson_raw`: no watertight, volumen no disponible, area 162.9823 m2, bbox 7.8197 x 10.0092 x 7.1076 m, 226 boundary edges, 39 componentes, componente dominante 99.6505%.
- `poisson_recovered`: no watertight, volumen no disponible, area 162.6627 m2, bbox estable, 326 boundary edges, 11 componentes, componente dominante 99.9724%.
- `poisson_controlled_hole_fill`: no watertight, volumen no disponible, area 297.3823 m2, bbox estable, 6 boundary edges, 6 componentes, componente dominante 99.9742%; rechazado por aumento de area superficial de 82.4629%.
- `poisson_vertex_hull_legacy_recovery`: watertight, volumen 180.3732 m3, area 196.7650 m2, bbox estable, 0 boundary edges, 1 componente; rechazado por drift de area superficial de 20.7278%.
- `alpha_shape_baseline`: watertight, volumen 46.7197 m3, area 124.3495 m2, bbox 6.7991 x 9.0992 x 6.2773 m; rechazado por cambio de bbox de 30.1904% y drift de area superficial de 23.7037%.

Clasificacion de fronteras:

- Poisson crudo: 1 loop clasificado como `borde_real_del_objeto_o_corte_de_captura`.
- Poisson recuperado: 25 `hueco_pequeno_cerrable`, 1 `borde_real_del_objeto_o_corte_de_captura`, 1 `discontinuidad_estructural`, 1 `error_de_reconstruccion`.
- Cierre controlado: quedan 4 loops, 2 `error_de_reconstruccion` y 2 `hueco_pequeno_cerrable`.

Conclusion empirica: el volumen 180.3732 m3 corresponde a una superficie watertight por envolvente global, pero no pasa conservacion de forma por area superficial. Alpha Shape tampoco es aceptable como primaria porque cambia bbox y area. Ninguna superficie actual cumple el criterio final; el pipeline debe bloquear publicacion de volumen y avanzar a superficie hibrida Poisson-derivada/constrained.

## Estrategias evaluadas

`hole filling controlado`: estrategia primaria si los loops son pequenos/cerrados y el cierre mantiene bbox y area superficial dentro del umbral.

`surface reconstruction constrained`: siguiente estrategia si hay discontinuidades estructurales, usando componente dominante Poisson como restriccion.

`smoothing + re-mesh con preservacion local`: cleanup posterior al cierre, no mecanismo de cierre por si solo.

`remeshing isotropico previo`: util para regular triangulos, pero riesgoso antes de clasificar fronteras porque puede mover bordes abiertos.

## Criterio de aceptacion

Una malla final no se acepta solo por `watertight = true`. Debe cumplir:

- volumen disponible;
- cero boundary edges;
- sin non-manifold edges;
- componente dominante estable, minimo 99% de triangulos;
- un unico componente o componente no computable por backend;
- delta maximo de bbox vs Poisson de referencia <= 2%;
- delta de area superficial vs Poisson de referencia <= 8%;
- ratio area/volumen reportado para comparar estabilidad entre metodos.

## Decision de arquitectura

El volumen debe calcularse desde una nueva superficie Poisson-derivada cerrada de forma controlada, no desde Alpha Shape y no desde `poisson_vertex_hull`.

Si `poisson_controlled_hole_fill` pasa los criterios anteriores, se vuelve la unica estrategia dominante. Si no pasa, el pipeline debe bloquear publicacion de volumen y pasar a reconstruccion constrained sobre componente dominante. Alpha Shape permanece como baseline y fallback no primario; `poisson_vertex_hull` permanece como evidencia de sobrecierre potencial, no como fuente de volumen.
