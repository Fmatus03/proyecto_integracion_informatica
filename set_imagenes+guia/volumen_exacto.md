# Ground Truth del dataset vigente

Estado actual: `pendiente`

- Dataset source of truth: `set_imagenes+guia/dataset_manifest.json`
- Volumen exacto certificado (m3): `null`
- Metodo de medicion fisica: `pendiente`
- Fecha de medicion: `pendiente`
- Responsable: `pendiente`

Regla del harness:

- Mientras este archivo no tenga un volumen exacto certificado, el sistema puede calcular volumen y generar malla, pero no puede afirmar cumplimiento de RF-09.
- En ese estado, `ground_truth.volume_m3 = null` y `error_percentage = null`.
