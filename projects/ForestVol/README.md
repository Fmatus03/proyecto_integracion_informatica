# ForestVol - Hito 0

Este directorio contiene el scaffold ejecutable del Hito 0 de ForestVol. El alcance de este hito es validar la base tecnica del proyecto con Docker Compose, una API FastAPI minima, integracion real con NodeODM y evidencia trazable del primer intento de generacion de nube de puntos `.ply`.

## Servicios

- `forestvol-backend`: FastAPI con `/health`, `/api/upload`, `/api/reconstruct/{session_id}` y `/api/results/{session_id}`.
- `forestvol-frontend`: placeholder operativo para la UI futura, sin adelantar Hito 3.
- `nodeodm`: motor SfM/MVS usado para la validacion tecnica real.

## Comandos

```bash
docker compose -f projects/ForestVol/docker-compose.yml up --build
docker compose -f projects/ForestVol/docker-compose.yml run --rm forestvol-backend pytest backend/tests -q
```

## Alcance de Hito 0

- Si NodeODM produce una nube de puntos `.ply`, Hito 0 puede marcarse como completado.
- Si Docker o NodeODM fallan con evidencia real, el hito debe quedar bloqueado exactamente en ese punto.
- No se afirma calibracion espacial, volumetria final ni RF-09 en este hito.
