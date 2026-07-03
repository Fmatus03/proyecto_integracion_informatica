# Promocion productiva obb_plus_curvature - 2026-07-02

## Cambio integrado

Se integro el filtro oficial validado `obb_plus_curvature` en `projects/ForestVol/backend/app/services/mesh_service.py`, inmediatamente despues de la segmentacion DBSCAN y antes de PDI.

Configuracion fija:

```json
{
  "obb_percentile": 80,
  "curvature_percentile": 80
}
```

Secuencia productiva resultante:

```text
Imagenes -> NodeODM -> Escalado ArUco reconstruido -> Limpieza -> Segmentacion/DBSCAN -> obb_plus_curvature -> PDI -> Volumen final
```

No se modificaron artefactos dentro de `experiments/`.

## Validaciones ejecutadas

### Unit tests backend

Comando:

```text
python -m pytest projects/ForestVol/backend/tests/unit
```

Resultado: 36 passed, 1 warning.

### RUN oficial via API/harness ForestVol

Dataset:

```text
projects/ForestVol/set_imagenes+guia/set_fotos_ultimo
```

Salida:

```text
projects/ForestVol/data/e2e_reconstructed_scale_validation/api_promoted_obb_curvature_set_fotos_ultimo
```

Session/run id:

```text
422bae01-50e4-40a6-8425-2a96f84d8cf6
```

NodeODM task:

```text
133e014e-2961-4655-9342-3cfff4fadce5
```

Estado del pipeline: `COMPLETED`.

Volumen obtenido: `181.2031 m3`.

Error respecto al volumen real `119.74 m3`: `51.3305 %`.

Comparacion contra validacion E2E experimental:

| Referencia | Volumen m3 |
|---|---:|
| Real | 119.74 |
| Benchmark | 121.2031 |
| E2E experimental previo | 123.9844 |
| RUN oficial promovido | 181.2031 |

Diferencia RUN oficial vs E2E experimental: `57.2187 m3`.

### Evidencia de aplicacion del filtro

El RUN oficial reporto:

```json
{
  "applied": true,
  "method": "obb_plus_curvature",
  "insertion_point": "after_dbscan_before_pdi",
  "obb_percentile": 80.0,
  "curvature_percentile": 80.0,
  "input_point_count": 71655,
  "after_obb_point_count": 34612,
  "after_curvature_point_count": 27689,
  "removed_point_count": 43966,
  "removed_percentage": 61.357895
}
```

La segmentacion previa selecciono el cluster dominante:

```json
{
  "selection_reason": "dominant_components_fallback",
  "selected_labels": [0],
  "selected_point_count": 71655
}
```

### Escalado ArUco del RUN oficial

El escalado 3D reconstruido fue aplicado con:

```json
{
  "marker_size_m": 1.0,
  "scale_factor_m_per_unit": 0.65003574,
  "selected_candidate_point_count": 4388,
  "selected_candidate_confidence": 0.369572
}
```

### Harness Hito 0.5

Comando:

```text
python -m pytest tests/harness
```

Resultado: 80 passed, 14 errors.

Los 14 errores no fueron fallas de validacion funcional, sino errores de entorno por falta de espacio en disco al copiar el repo/datasets a `%TEMP%`:

```text
OSError: [Errno 28] No space left on device
WinError 112: Espacio en disco insuficiente
```

## Estado final

El proyecto NO fue marcado como `Completed`.

Motivos:

1. El RUN oficial completo termino sin errores, pero el volumen obtenido (`181.2031 m3`) no es consistente con la validacion E2E esperada de aproximadamente `123.9844 m3`.
2. Las validaciones del harness Hito 0.5 no pudieron completarse por falta de espacio en disco en `%TEMP%`.

No se modificaron parametros para forzar el resultado.
