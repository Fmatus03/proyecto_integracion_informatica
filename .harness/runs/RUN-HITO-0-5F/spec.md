# Objetivo

Recuperar escala fisica del Hito 0.5 usando el marcador ArUco visible en terreno, que mide exactamente 100 cm. El detector ArUco ya existe y fue validado en el hito anterior en `backend/app/services/calibration_service.py`; el problema actual es integrarlo arquitectonicamente con NodeODM. El Ground Truth de `volumen_exacto.md` se usa solo al final para evaluar `error_percentage` y `rf09_compliance`.

# Alcance

El pipeline debe trabajar con imagenes RGB, `dataset_manifest`, manifest y marcador ArUco DICT_4X4_50 ID 0 de 100 cm, sin metadatos obligatorios. La referencia fisica debe convertirse en escala fotogrametrica mediante GCP o medicion 3D derivada del marcador. En este run se prioriza la Opcion A: reutilizar `_detect_marker`, `calibrate_image_paths` y las estructuras `MarkerDetection` existentes para extraer esquinas ArUco en las imagenes originales, generar un `gcp_list.txt` en coordenadas locales metricas y pasarlo a NodeODM para que reconstruya con escala real desde el inicio.

El marcador no necesita estar en todas las fotos si la deteccion cubre suficientes vistas para que NodeODM use puntos de control compartidos; si la cobertura es insuficiente, el run debe indicarlo explicitamente y bloquear RF-09. Para el dataset vigente, la expectativa minima es detectar el marcador en la mayoria de imagenes visibles.

# Requisitos

- RF-09-F1: Prohibido usar el volumen exacto para generar factores de escala, calibrar malla o alterar el point cloud.
- RF-09-F2: Reutilizar el detector ArUco existente, sin reescribirlo, y usar su medida fisica de 1 metro para generar GCP metricos.
- RF-09-F3: Pasar el archivo GCP real a NodeODM mediante `nodeodm_client.py` y registrar la evidencia de escala.
- RF-09-F4: Calcular volumen desde la malla reconstruida a escala ArUco, y usar Ground Truth solo para `error_percentage`.
- RF-09-F5: Aprobar `rf09_compliance` solo si la malla es watertight, el volumen proviene de evidencia real y el error es menor o igual a 15%.

# Restricciones

No simular detecciones, no quemar factores, no usar el Ground Truth para escalar. No editar `state.json` a mano. Si el marcador no aparece en suficientes fotos o NodeODM no acepta los GCP, el run debe bloquearse con evidencia.

# Riesgos

OpenDroneMap puede requerir un formato GCP estricto y puede rechazar GCP con coordenadas locales si el CRS no es aceptado. El marcador ArUco define un plano de 1 m x 1 m; si todas las detecciones estan en un plano pequeño, puede escalar el modelo pero no resolver todos los defectos geometricos de una toma con screenshots.
