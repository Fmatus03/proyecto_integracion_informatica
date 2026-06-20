# Ground Truth del dataset vigente

Estado actual: `Completado`

- Dataset source of truth: `projects/ForestVol/set_imagenes+guia/dataset_manifest.json`
- Volumen exacto certificado (m3): `119,74`
- Metodo de medicion fisica: `Calculo a traves de 3D print blender`
- Fecha de medicion: `16-06-2026`
- Responsable: `Fabian Matus`

Regla del harness:

- Este archivo declara Ground Truth certificado para Hito 0.5.
- Para este run, `ground_truth.volume_m3 = 119.74` y `error_percentage` debe calcularse desde el volumen real del sistema.
- No se debe afirmar cumplimiento si la malla no es watertight o si el volumen no fue calculado sobre evidencia real.
