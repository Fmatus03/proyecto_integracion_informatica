# Local Bridge Validation

Nube auditada: `C:\Users\Fabian Matus\OneDrive\Escritorio\harness_con_separacion_de_proyectos\experiments\volume_input_audit\selected_volume_cloud.ply`

No se modifico pipeline productivo. Grafo offline con radio exacto `eps = 0.35 m`.

## Metodo

El corte global completo no es viable computacionalmente para 45,511 nodos y 3.8M aristas. Esta auditoria calcula cortes exactos de NetworkX en subgrafos inducidos locales alrededor del punto de contacto entre cada region externa low-support y el componente high-support/castillo. Cada subgrafo se obtiene por expansion de 2 saltos sobre el camino minimo de contacto, preservando la conectividad local responsable.

## Resumen

| Region | Puntos region externa | Nodos subgrafo | Aristas subgrafo | Min node cut | Min edge cut | Articulation | Bridges | Biconn comps | Separado tras corte |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | 5035 | 690 | 47205 | 0 | 119 | 0 | 0 | 1 | False |
| 1 | 1694 | 276 | 9789 | 0 | 61 | 0 | 0 | 1 | False |
| 2 | 134 | 689 | 50871 | 0 | 68 | 0 | 0 | 1 | False |
| 3 | 17 | 456 | 21157 | 1 | 2 | 1 | 0 | 2 | True |
| 4 | 17 | 834 | 72516 | 0 | 72 | 0 | 0 | 1 | False |
| 5 | 16 | 849 | 60434 | 0 | 171 | 0 | 0 | 1 | False |
| 6 | 14 | 744 | 52997 | 0 | 91 | 0 | 0 | 1 | False |
| 7 | 14 | 462 | 34235 | 0 | 44 | 0 | 0 | 1 | False |

## Union de cuellos locales

- Nodos unicos en cortes minimos: `1`
- Articulation points unicos: `1`
- Endpoints de bridge edges unicos: `0`
- Clasificacion: `puente extremadamente fino`

## Conclusiones obligatorias

1. La estructura que mantiene unida cada region esta dada por el camino minimo de contacto y su corte exacto local, reportados en `bridge_metrics.json` y `bridge_points.csv`.
2. Si `minimum_vertex_cut_size = 1`, el contacto local es un cuello puntual; valores mayores implican caminos redundantes.
3. Los puntos exactos a eliminar estan en `minimum_vertex_cut_nodes` y visualizados en amarillo en `minimum_cut_nodes.ply`.
4. Las coordenadas XYZ estan en `bridge_points.csv`; bbox de puente/corte por region en `bridge_metrics.json`.
5. La densidad y soporte del puente estan reportados por region.
6. Todos los resultados usan `eps = 0.35 m`; si el corte local es pequeno, la union es consecuencia directa de conectividad bajo ese eps. Si hay muchos bridges/cortes grandes, la reconstruccion local se comporta como superficie fusionada.

No se implemento ninguna solucion ni filtro.
