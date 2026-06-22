# Tareas

- T-001: Crear servicio GCP que reutilice `_detect_marker`, `calibrate_image_paths` y `MarkerDetection` de `calibration_service.py` sobre imagenes RGB del dataset_manifest, sin metadatos obligatorios.
- T-002: Generar `gcp_list.txt` con cuatro esquinas metricas del marcador de 100 cm y observaciones por imagen usando las esquinas detectadas por `MarkerDetection`.
- T-003: Integrar `gcp_list.txt` en `nodeodm_client.py` mediante `options_for_attempt` y `submit_task`.
- T-004: Agregar tests para deteccion/generacion GCP y para no usar Ground Truth como escala.
- T-005: Ejecutar pipeline con GCP, generar malla, mesh, volumen y evidencia con checksum.
- T-006: Calcular error_percentage contra Ground Truth al final y evaluar RF-09 por CLI.

# Responsable

- Analyzer: elegir arquitectura y justificar Opcion A.
- Implementer: OpenCV/GCP, NodeODM, tests y pipeline.
- Validator: evidencias, claims, gates, audit e integridad.
- Orchestrator: transiciones por CLI.

# Estado

Pendiente hasta `analyze-report.md`.
