# Dataset de Prueba (Hito 0)

Este directorio ya no es la unica referencia operativa del dataset.

La fuente de verdad del set vigente es:

- `projects/ForestVol/set_imagenes+guia/dataset_manifest.json`
- `projects/ForestVol/set_imagenes+guia/set_fotos_castillo_de_madera/`
- `projects/ForestVol/set_imagenes+guia/guia100cm/aruco-marker-ID=0.png`

## Instruccion para el Agente

1. Si existe un dataset real con `min_images` cumplido en `dataset_manifest.json`, el harness debe tratarlo como dataset oficial de validacion local.
2. Los tests unitarios y de integracion estandar siguen usando mocks de NodeODM para evitar timeouts en CI.
3. Los tests dataset-driven y E2E reales pueden ejecutarse solo cuando el entorno tenga backend implementado, NodeODM disponible y recursos suficientes.
4. El agente no puede asumir EXIF, GPS, altura de vuelo ni metadata de dron. Las imagenes deben considerarse RGB comunes sin metadata confiable.
5. Si el set cambia en el futuro, se actualiza `dataset_manifest.json`; no se hardcodean nombres de archivos individuales en el harness.
