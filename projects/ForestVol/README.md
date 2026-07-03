# ForestVol - Hito 0

Este directorio contiene el scaffold ejecutable de ForestVol. El pipeline productivo usa NodeODM para reconstruir nube de puntos y Point Density Integration (PDI) como estimador volumetrico oficial.

## Servicios

- `forestvol-backend`: FastAPI con `/health`, `/api/upload`, `/api/reconstruct/{session_id}` y `/api/results/{session_id}`.
- `forestvol-frontend`: interfaz minima para consultar volumen PDI, confidence score, quality gates y diagnostico.
- `nodeodm`: motor SfM/MVS usado para la validacion tecnica real.

## Volumetria oficial

- El volumen oficial proviene exclusivamente de `point_density_integration`.
- La malla queda como capa legacy para visualizacion, exportacion, depuracion o comparacion manual.
- Poisson, Alpha Shape y mesh repair no participan en el calculo oficial del volumen.
- `GET /api/results/{session_id}` retorna `volume_method`, `confidence_score`, `confidence_level`, `quality_gates`, `diagnostic` y `pdi_metrics`.

## Comandos

```bash
docker compose -f projects/ForestVol/docker-compose.yml up --build
docker compose -f projects/ForestVol/docker-compose.yml run --rm forestvol-backend pytest backend/tests -q
```

## Validacion productiva PDI

- Run: `RUN-PDI-PRODUCTIVE-MIGRATION-01`.
- Backend unit tests en Docker: `32 passed`.
- Set 1 API end-to-end: `COMPLETED`, volumen PDI `69.8281 m3`, error `41.6836%`.
- Set 2 API end-to-end: `COMPLETED`, volumen PDI `39.0156 m3`, error `67.4164%`.
- Hito 0.5 queda bloqueado por criterio de error volumetrico, no por falla de ejecucion.
