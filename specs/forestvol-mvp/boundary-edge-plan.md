# Hitos

1. Congelar la malla objetivo desde `surface_closure_diagnostics_2`.
2. Ejecutar runtime Docker con evidencia reproducible.
3. Identificar boundary edges, loops, componentes, normales y caras adyacentes.
4. Generar visualizaciones y reporte con checksum/validator del arnes.
5. Mantener el contrato de entradas RGB sin metadata, sin metadatos, no usar EXIF y no asumir GPS.
6. No usar ground truth, RF-09 ni error como criterio de ajuste de los boundary edges.

# Entregables

- Reporte forense de boundary edges.
- JSON verificable con metricas de malla, loops, edges y simulaciones.
- Imagenes ortograficas e isometricas.
- Decision tecnica A/B.

# Dependencias

- Runtime Docker `forestvol-backend`.
- Evidencia en `dataset_manifest`.
- Marcador ArUco ya validado por dataset gate.
- Imagenes RGB ya reconstruidas por el pipeline.
- Malla Poisson controlada congelada como artefacto de diagnostico.
