# Hallazgos

La aclaracion del Product Owner aporta la pieza faltante del dataset y manifest: existe una referencia fisica de escala en terreno, visible en las imagenes, y mide 100 cm. El detector ArUco ya existe en `calibration_service.py` y fue validado con exito en el hito anterior, asi que no debe reescribirse. Esto evita usar Ground Truth como actuador y permite operar sin metadatos obligatorios. La arquitectura elegida es Opcion A: conectar `_detect_marker`, `calibrate_image_paths` y `MarkerDetection` para generar un archivo `gcp_list.txt` que NodeODM pueda consumir antes de reconstruir.

Opcion A es mas robusta que corregir una malla ya reconstruida porque introduce la escala al proceso SfM/MVS desde puntos de control compartidos. Opcion B exigiria mapear pixeles de la imagen a vertices 3D o detectar el marcador en la nube, lo cual es menos estable con una nube ruidosa y texturas repetitivas.

El Ground Truth de `volumen_exacto.md` queda reservado para evaluar `error_percentage` y `rf09_compliance` al final. Si el GCP generado no es aceptado por NodeODM, o si la cobertura de detecciones ArUco es insuficiente, se debe bloquear con evidencia. Los claim, gate y trazabilidad deben registrar esa decision sin aprobar RF-09 artificialmente.

# Riesgos

El formato GCP de NodeODM puede requerir CRS/proyeccion y coordenadas especificas. Se usara un sistema local metrico documentado en el archivo GCP; si NodeODM no lo acepta, el bloqueo sera honesto. Tambien existe riesgo de que las capturas no cubran suficientemente el marcador en todas las vistas; se exige documentar cuantas detecciones reales se obtienen.

# Recomendacion

Implementar generacion GCP como preprocesamiento reutilizando el detector existente, integrarla en las opciones NodeODM y ejecutar pipeline. Si el resultado reconstruido con GCP mantiene error mayor al 15%, iterar parametros NodeODM, no Ground Truth. Solo cerrar si `rf09_compliance` pasa por CLI.
