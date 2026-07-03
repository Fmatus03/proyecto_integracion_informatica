# Implementacion de escalado 3D basado en ArUco reconstruido

Fecha: 2026-07-01

## Resumen

Se implemento el nuevo contrato productivo de escala:

1. El `gcp_list.txt` puede seguir generandose y enviandose a NodeODM como ayuda de reconstruccion.
2. La existencia del GCP ya no certifica que la nube este en metros.
3. Despues de descargar `point_cloud.ply`, el pipeline intenta medir el ArUco reconstruido en 3D.
4. Solo si esa medicion entrega un candidato valido, `scale_certified=True`.
5. El factor oficial pasa a ser `scale_factor_m_per_unit = lado_real_m / lado_reconstruido_units`.
6. `mesh_service.generate_preliminary_volumetry()` aplica ese factor a toda la nube antes de limpieza, DBSCAN y PDI.

No se modifico NodeODM, OpenSfM, DBSCAN, PDI ni parametros de reconstruccion.

## Archivos modificados

| Archivo | Cambio |
|---|---|
| `projects/ForestVol/backend/app/services/reconstructed_scale_service.py` | Nuevo servicio de deteccion y medicion del ArUco reconstruido. |
| `projects/ForestVol/backend/app/api/routes/reconstruction.py` | Integracion productiva: GCP queda pendiente de validacion 3D; la escala final viene del ArUco reconstruido. |
| `projects/ForestVol/backend/tests/unit/test_reconstructed_scale_service.py` | Pruebas unitarias del detector 3D con nube sintetica. |
| `projects/ForestVol/backend/tests/unit/test_reconstruction_scale_contract.py` | Pruebas del contrato: GCP existente no basta para escala metrica. |

## Algoritmo implementado

El servicio `estimate_reconstructed_aruco_scale()` ejecuta:

1. Carga PLY ASCII o `binary_little_endian`.
2. Requiere coordenadas XYZ y color RGB.
3. Filtra puntos blanco/negro de baja saturacion:
   - brillo bajo o alto;
   - diferencia RGB pequena.
4. Agrupa candidatos mediante componentes conectados en grilla voxel.
5. Para cada componente:
   - ajusta plano por PCA;
   - proyecta puntos al plano local;
   - mide una caja minima 2D robusta por percentiles;
   - calcula razon cuadrada, espesor del plano, lado reconstruido y distancia al centro esperado del GCP;
   - calcula confianza.
6. Selecciona el candidato de mayor confianza.
7. Devuelve `scale_factor_m_per_unit`.

La medicion de caja minima 2D evita el error de usar directamente PCA como lado, porque un cuadrado simetrico puede quedar alineado con diagonales.

## Nuevo contrato de escala

Antes:

```text
gcp_list.txt existe
-> scale_certified=True
-> point_cloud_scale_m_per_unit=1.0
```

Ahora:

```text
gcp_list.txt existe
-> scale_certified=False
-> reason=aruco_gcp_generated_pending_3d_validation
-> NodeODM reconstruye
-> point_cloud.ply descargado
-> detectar y medir ArUco reconstruido
-> scale_certified=True solo si hay candidato 3D valido
-> point_cloud_scale_m_per_unit=factor medido
```

Si la deteccion 3D falla, la volumetria queda bloqueada porque `mesh_service` ya exige evidencia metrica 3D.

## Evidencia sobre nube sintetica

Smoke test manual:

- ArUco sintetico reconstruido con lado de `2.0` unidades.
- Lado real configurado: `1.0 m`.
- Factor esperado: `0.5`.
- Factor medido: `0.5015460862`.
- Resultado: PASS.

## Evidencia sobre ultima nube real existente

Artefacto usado:

`projects/ForestVol/data/processed/ecd0f8b7-64f5-437b-9048-2ae83609e8e7/point_cloud.ply`

Resultado del detector:

| Metrica | Valor |
|---|---:|
| Puntos totales | 1786481 |
| Puntos blanco/negro candidatos evaluados | 250000 |
| Candidatos validos | 4 |
| Lado reconstruido seleccionado | 2.104863 unidades |
| Lado real | 1.0 m |
| Factor calculado | 0.47509019 |
| Puntos del candidato | 1849 |
| Centroide candidato | `[-0.014863, 0.294128, 0.039227]` |
| Extension PCA/caja local | `[2.284617, 1.925110, 0.448560]` |
| Square ratio | 0.842640 |
| Flatness ratio | 0.196339 |
| Confianza | 0.435249 |

Interpretacion: el factor medido en geometria reconstruida queda cerca del orden esperado por el analisis de causa raiz (~0.5). Esta medicion no usa ground truth de volumen.

## Validacion ejecutada

Comandos/validaciones realizadas:

| Validacion | Resultado |
|---|---|
| Smoke test del detector sobre nube sintetica | PASS |
| Compilacion sintactica de archivos modificados usando `py_compile` con salida temporal | PASS |
| Detector sobre nube real existente | PASS |
| `pytest` unitario | No ejecutado: el Python disponible no tiene `pytest`. |
| E2E desde imagenes con NodeODM | No ejecutado: NodeODM local no responde en `http://localhost:3000/info`. |

## Bloqueo de E2E

La validacion completa desde cero requiere NodeODM activo y accesible. En este entorno:

```text
NODEODM_LOCAL_UNREACHABLE: No es posible conectar con el servidor remoto
```

Por lo tanto, la implementacion queda integrada y validada a nivel de servicio/contrato, pero la corrida completa imagenes -> NodeODM -> ArUco 3D -> PDI queda pendiente de infraestructura.

## Decision tecnica

La estrategia es tecnicamente viable y quedo integrada como fuente oficial de escala. La decision operativa recomendada es ejecutar una corrida E2E apenas NodeODM este disponible y aceptar volumetria solo si el payload `scale_evidence.reconstructed_aruco_scale` existe y `scale_certified=True`.
