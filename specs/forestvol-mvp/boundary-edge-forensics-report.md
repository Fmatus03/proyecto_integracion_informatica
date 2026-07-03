# Boundary Edge Forensics Report

Fecha: 2026-06-28
Run arnes: RUN-SURFACE-CLOSURE-01
Actor: orchestrator

## Hallazgos

La investigacion se ejecuto sobre la malla congelada validada previamente:

`projects/ForestVol/data/processed/b6b04af0-122f-4fcc-af8a-cc553ca5e28d/surface_closure_diagnostics_2/poisson_controlled_hole_fill.ply`

Reporte forense:

`projects/ForestVol/data/processed/b6b04af0-122f-4fcc-af8a-cc553ca5e28d/boundary_edge_forensics_3/boundary_edge_forensics.json`

Este reporte usa dataset manifest, evidencia verificable, checksum calculable por archivo, validator del arnes, claim/gate de analisis y trazabilidad del run `RUN-SURFACE-CLOSURE-01`.

La investigacion mantiene entradas RGB sin metadata, sin metadatos, no usar EXIF y no asumir GPS.

Metricas de la malla objetivo:

- vertices: 83252
- triangulos: 166719
- componentes: 6
- componente dominante: 166676 triangulos
- watertight: false
- volumen: no disponible
- area superficial: 297.3823 m2
- bbox: 7.8197 x 10.0092 x 7.1076 m
- boundary edges: 6
- non-manifold edges Open3D: 20
- non-manifold vertices: 15
- orientable: false

Los 6 boundary edges no forman agujeros cerrados. Se agrupan en 3 caminos abiertos:

- BL-000: edges BE-000 y BE-001, perimetro 0.090126 m, diametro 0.049647 m, componente 0.
- BL-001: edges BE-002 y BE-003, perimetro 0.075413 m, diametro 0.040624 m, componente 0.
- BL-002: edges BE-004 y BE-005, perimetro 0.077370 m, diametro 0.040834 m, componente 3.

Cada camino tiene 2 aristas y 3 vertices, `closed = false`, area encerrada no computable y clasificacion `error_topologico`.

Evidencia estructural:

- BL-000 pertenece a la cara 69856. Dos aristas tienen incidencia 1, pero la tercera arista tiene incidencia 3.
- BL-001 pertenece a la cara 154265. Dos aristas tienen incidencia 1, pero la tercera arista tiene incidencia 3.
- BL-002 pertenece a la cara 154363. Dos aristas tienen incidencia 1, pero la tercera arista tiene incidencia 5.

Esto demuestra que no son huecos cerrados simples. Son caminos abiertos acoplados a aristas no-manifold.

Visualizaciones generadas:

- `orthographic_xy.png`
- `orthographic_xz.png`
- `orthographic_yz.png`
- `view_3d_isometric.png`

Todas viven en:

`projects/ForestVol/data/processed/b6b04af0-122f-4fcc-af8a-cc553ca5e28d/boundary_edge_forensics_3/`

## Riesgos

Cerrar estos caminos como si fueran loops de agujero requeriria duplicar o alterar triangulos ya existentes. Eso no es una reparacion local limpia: puede incrementar non-manifoldness o crear caras duplicadas.

El estado actual ya tiene 20 non-manifold edges, 15 non-manifold vertices y orientabilidad false. Por tanto, `watertight = false` no depende solo de 6 aristas frontera, sino de una topologia residual inconsistente.

## Recomendacion

Decision requerida por el objetivo:

B)

No. Los boundary edges representan una limitacion estructural de la reconstruccion y justifican desarrollar una nueva estrategia de superficie hibrida o constrained.

Justificacion objetiva:

- los 6 edges no son loops cerrados;
- ninguna simulacion individual pudo cerrar un loop valido;
- los caminos abiertos no reducen boundary edges mediante fan triangulation;
- la tercera arista de cada triangulo implicado es no-manifold con incidencia 3 o 5;
- la malla completa sigue con non-manifold edges y orientabilidad false.

No se uso ground truth, no se modifico GCP, no se modifico calibracion, no se modifico segmentacion y no se cambio el algoritmo Poisson.
