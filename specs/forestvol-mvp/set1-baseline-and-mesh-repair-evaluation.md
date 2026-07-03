# Set 1 Baseline and Mesh Repair Evaluation

Fecha: 2026-06-28
Run arnes: RUN-SET1-BASELINE-01
Actor: orchestrator

## Fase 1: Linea Base Set 1

La ejecucion del set 1 se realizo exactamente una vez contra el estado actual del proyecto, sin modificar servicios, parametros, GCP, calibracion, segmentacion ni algoritmos. El cliente local agoto timeout durante polling, pero la sesion ya creada continuo y termino en `COMPLETED`; no se relanzo.

Sesion set 1:

`a3c36266-f866-402f-8bc8-1c2b59b4a4ce`

Artefactos principales:

- Resultado crudo: `.harness/runs/RUN-SET1-BASELINE-01/e2e-set1-baseline-result.json`
- Diagnostico comparable: `projects/ForestVol/data/processed/a3c36266-f866-402f-8bc8-1c2b59b4a4ce/surface_closure_diagnostics/surface_closure_diagnostics.json`
- Comparacion cruda: `.harness/runs/RUN-SET1-BASELINE-01/set1-vs-set2-comparison-raw.json`

Metricas finales del pipeline set 1:

- volumen final: 156.9277 m3
- error vs Ground Truth: 31.057% solo referencia, no usado para optimizar
- bounding box final: 8.9842 x 14.9807 x 5.0882 m
- puntos reconstruidos/segmentados usados: 19879 / 19879
- vertices/triangulos malla final: 112 / 220
- watertight final: true
- estrategia final: Poisson recovery fallo como superficie aceptable; Alpha Shape fallback no entrego superficie aceptada; el pipeline termino en `cycle_4_convex_hull_fallback`

Metricas Poisson set 1:

- Poisson crudo: 58975 triangulos, 10 componentes, componente dominante 99.4676%, 191 boundary edges, 195 non-manifold edges Open3D, orientable false.
- Poisson recuperado: 58653 triangulos, 1 componente, 203 boundary edges, 203 non-manifold edges Open3D, orientable true.
- Poisson con cierre controlado: 1 boundary edge restante, no watertight, area superficial 547.8935 m2, drift de area +107.1189% vs Poisson crudo.
- `poisson_vertex_hull`: watertight, volumen 489.2606 m3, drift de bbox 3.2338% y drift de area +108.5435%; rechazado por criterio de forma.
- Alpha Shape baseline: no watertight, 2 componentes, dominante 75.6127%, bbox drift 59.3517%, area drift 54.5986%; rechazado.

## Comparacion Set 1 vs Set 2

Set 2 de referencia:

- sesion: `b6b04af0-122f-4fcc-af8a-cc553ca5e28d`
- volumen final pipeline: 46.7197 m3
- error vs Ground Truth: 60.9824%
- bounding box final: 6.7991 x 9.0992 x 6.2773 m
- puntos reconstruidos/segmentados usados: 26113 / 26113
- vertices/triangulos malla final: 716 / 1428
- estrategia final historica: Alpha Shape fallback

Comparacion Poisson:

- Set 1 Poisson crudo: componente dominante 99.4676%, 191 boundary edges, 195 non-manifold edges, 10 componentes.
- Set 2 Poisson crudo: componente dominante 99.6505%, 226 boundary edges, 195+ non-manifold behavior observado, 39 componentes.
- Set 1 Poisson recuperado: 203 boundary edges y 203 non-manifold edges.
- Set 2 Poisson recuperado: 326 boundary edges y topologia no aceptable.
- Set 1 cierre controlado: reduce a 1 boundary edge pero produce drift de area +107.1189%.
- Set 2 cierre controlado: reduce a 6 boundary edges pero produce drift de area +82.4629%.

Respuestas objetivas:

- El problema no aparece unicamente en set 2.
- Set 1 presenta topologia defectuosa: Poisson no watertight, non-manifold edges, boundary edges y volumen no disponible sin fallback.
- Poisson no produce una superficie significativamente mejor en set 1: mejora hasta 1 boundary edge tras cierre, pero con drift de area mayor que set 2.
- Los boundary edges no son identicos, pero ambos datasets convergen a Poisson abierto y no aceptable.
- Non-manifold edges aparecen tambien en set 1.
- El problema parece depender de la reconstruccion/meshing sobre capturas RGB sin metadata, no solo de una captura especifica.
- La arquitectura actual no es suficiente para set 1 si se exige superficie Poisson valida; solo obtiene volumen mediante fallback de envolvente.
- Las conclusiones de set 2 se generalizan: la falla es inherente al pipeline actual para estos datasets, aunque la forma exacta del defecto topologico cambia por dataset.

## Fase 2: Evaluacion Tecnologica

Esta fase es documental y tecnica. No se integro ningun motor ni se modifico el pipeline.

### CGAL Polygon Mesh Processing

Capacidades relevantes: hole filling con `triangulate_hole`, `triangulate_and_refine_hole` y `triangulate_refine_and_fair_hole`; CGAL declara que el patch generado no introduce non-manifold edges ni triangulos degenerados, pero exige precondiciones como bordes de agujero validos y ausencia de vertices non-manifold en ciertos casos. Licencia: CGAL combina componentes GPL/LGPL y licencia comercial segun modulo.

Evaluacion:

- Integracion: media/alta complejidad por C++ y bindings.
- Licencia: revisar modulo exacto; posible friccion GPL/comercial.
- Non-manifold edges: fuerte como reparador si se preprocesa correctamente.
- Cierre de superficies abiertas: fuerte en agujeros con border halfedge valido.
- Preservacion de bbox/area/volumen: potencialmente buena para agujeros locales; no garantizada para defectos estructurales abiertos.
- Riesgo: nuestros ultimos defectos set 2 eran caminos abiertos/no-manifold, no loops cerrados; CGAL requeriria una etapa previa de saneamiento.

### MeshFix

Capacidades relevantes: disenado para convertir mallas RAW digitizadas en un unico triangulo watertight, corrigiendo agujeros, self-intersections, degenerados y elementos non-manifold. Su README advierte que asume un unico objeto solido cerrado y puede producir resultados gruesos o fallar en otros inputs. Licencia: GPLv3 o contrato comercial.

Evaluacion:

- Integracion: media, CLI externo o binario C++.
- Licencia: GPLv3/comercial, riesgo alto si ForestVol requiere distribucion cerrada.
- Non-manifold edges: fuerte.
- Cierre de superficies abiertas: fuerte, pero orientado a producir solido watertight unico.
- Preservacion de bbox/area/volumen: incierta; puede reconstruir regiones defectuosas y simplificar.
- Riesgo: podria resolver watertight pero alterar la geometria volumetrica, parecido a una envolvente inteligente.

### PyMeshLab

Capacidades relevantes: expone filtros MeshLab como `meshing_close_holes`, reparacion de non-manifold edges/vertices, remocion de duplicados y reconstrucciones VCG/APSS/RIMLS. `meshing_close_holes` cierra agujeros bajo un umbral de cantidad de edges y tiene opcion para evitar self-intersections de forma heuristica.

Evaluacion:

- Integracion: buena por Python.
- Licencia: revisar stack MeshLab/VCG/PyMeshLab antes de producto.
- Non-manifold edges: buena capacidad operativa.
- Cierre de superficies abiertas: buena para holes, menos clara para caminos abiertos no-manifold.
- Preservacion de bbox/area/volumen: medible y controlable con filtros locales, pero no garantizada.
- Riesgo: muchas operaciones son heuristicas; requiere harness experimental por malla.

### VTK

Capacidades relevantes: `vtkFillHolesFilter` identifica boundary edges, los enlaza en loops y triangula los loops; permite limitar tamano de hole por `HoleSize`. VTK tiene licencia BSD-style.

Evaluacion:

- Integracion: buena por Python.
- Licencia: baja friccion.
- Non-manifold edges: limitada; `vtkFillHolesFilter` no es reparador general non-manifold.
- Cierre de superficies abiertas: bueno para loops de boundary edges.
- Preservacion de bbox/area/volumen: buena si los holes son locales y se limita `HoleSize`.
- Riesgo: no soluciona caminos abiertos/no-manifold como los 6 edges del set 2 sin preprocesamiento.

### trimesh.repair

Capacidades relevantes: `broken_faces`, `fill_holes`, `fix_normals`, `fix_inversion`. La documentacion indica que `fill_holes` rellena boundary holes in-place y puede dar respuestas malas si los agujeros no son convexos.

Evaluacion:

- Integracion: excelente por Python.
- Licencia: permisiva segun proyecto, baja friccion tecnica.
- Non-manifold edges: limitada para reparacion compleja.
- Cierre de superficies abiertas: util para agujeros simples.
- Preservacion de bbox/area/volumen: buena solo para agujeros pequenos y convexos.
- Riesgo: insuficiente para defectos estructurales no-manifold; ya estamos cerca del limite de Open3D/trimesh-style repair.

## Decision Tecnologica

Ninguna alternativa debe reemplazar inmediatamente el pipeline sin prueba experimental. La opcion mas prometedora para una fase de prueba controlada es PyMeshLab o CGAL:

- PyMeshLab por integracion rapida y filtros amplios.
- CGAL por robustez geometrica, si la licencia y bindings son aceptables.

MeshFix es atractivo para repair fuerte, pero su objetivo de producir un unico solido watertight puede alterar geometria y volumen. VTK y trimesh son buenos para agujeros simples, pero no parecen suficientes para los defectos non-manifold estructurales observados.

Recomendacion: crear un harness experimental que aplique PyMeshLab y CGAL sobre la misma malla Poisson congelada de set 1 y set 2, midiendo bbox, area, volumen, boundary edges, non-manifold edges, orientabilidad y distancia Hausdorff aproximada contra Poisson. Si ambas fallan o alteran forma, avanzar a arquitectura hibrida/constrained.

## Fuentes

- CGAL hole filling: https://doc.cgal.org/latest/Polygon_mesh_processing/group__PMP__hole__filling__grp.html
- CGAL license: https://www.cgal.org/license.html
- MeshFix README/licencia: https://github.com/MarcoAttene/MeshFix-V2.1
- PyMeshLab filters: https://pymeshlab.readthedocs.io/en/latest/filter_list.html
- VTK FillHolesFilter: https://vtk.org/doc/nightly/html/classvtkFillHolesFilter.html
- VTK license: https://vtk.org/about/#license
- trimesh repair: https://trimesh.org/trimesh.repair.html
