# Bottleneck Report

## set1

- Diagnostico: `DBSCAN`.
- Mayor perdida puntual: `after_dbscan` con ratio `0.96036`.
- Puntos RAW -> PDI: `401873` -> `15799`; eliminado `0.960687`.
- BBox RAW -> PDI: `34178.953655` -> `438.24735` m3; retenido `0.012822`.
- Volumen PDI: `69.8281` m3; error `41.6836%`.
- Chamfer RAW -> PDI: `0.513978` m; Hausdorff `28.723695` m.

## set2

- Diagnostico: `DBSCAN`.
- Mayor perdida puntual: `after_dbscan` con ratio `0.990999`.
- Puntos RAW -> PDI: `371766` -> `3278`; eliminado `0.991183`.
- BBox RAW -> PDI: `1266.406363` -> `538.042284` m3; retenido `0.424858`.
- Volumen PDI: `39.0156` m3; error `67.4164%`.
- Chamfer RAW -> PDI: `0.077851` m; Hausdorff `10.000928` m.

Conclusion: el cuello de botella cuantitativo es DBSCAN/seleccion de componentes, no PDI. NodeODM RAW contiene mucha mas geometria, pero tambien ruido y componentes ajenas; la mayor perdida de informacion ocurre al reducir esa nube a los componentes seleccionados antes de PDI.
