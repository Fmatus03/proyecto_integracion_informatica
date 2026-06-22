# Hitos

- H-001: Implementar Opcion A conectando el detector existente de `calibration_service.py` para generar `gcp_list.txt` desde detecciones reales de ArUco 100 cm.
- H-002: Integrar el archivo GCP en `nodeodm_client.py` para que NodeODM reconstruya con escala fisica.
- H-003: Procesar el dataset con imagenes RGB, marcador ArUco, dataset_manifest y GCP generado, sin metadatos obligatorios.
- H-004: Calcular volumen y error_percentage contra Ground Truth solo al final.
- H-005: Pasar claims `volume_estimate`, `ground_truth_certified`, `error_percentage` y `rf09_compliance` si el error cumple; bloquear si no cumple.

# Entregables

- Servicio de GCP basado en las funciones existentes `_detect_marker`, `calibrate_image_paths` y `MarkerDetection`.
- `gcp_list.txt` generado para RUN-HITO-0-5F con checksum.
- Ajuste de NodeODM para incluir `gcp`.
- Tests unitarios de generacion GCP y opciones NodeODM.
- Evidencia JSON para escala, malla, Ground Truth, error y RF-09.

# Dependencias

- `cv2.aruco`, OpenCV y las imagenes RGB originales.
- `dataset_manifest` y marcador ArUco de 100 cm.
- Runtime/cli del harness para claims, gates, trazabilidad e integridad.
- Ground Truth oficial usado exclusivamente como evaluador final.
