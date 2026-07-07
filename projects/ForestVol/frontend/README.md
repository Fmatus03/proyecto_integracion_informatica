# ForestVol Frontend

SPA Vue 3 para la consola operativa ForestVol.

## Stack

- Vue 3 con Composition API.
- Vite como bundler.
- Vue Router para navegacion.
- Axios para comunicacion con FastAPI.
- Three.js para visualizacion RF-10 de modelos GLB/PLY.
- Element Plus para controles de interfaz, tablas, estados y formularios. Se eligio porque el proyecto no tenia libreria UI previa y la migracion solicitaba incorporar una libreria profesional.

## Arquitectura

```text
src/
  assets/          estilos globales
  components/
    common/        estados visuales reutilizables
    layout/        shell principal y navegacion
    domain/        flujo ForestVol, tablas, visor y resumenes
  composables/     estado del pipeline y polling
  router/          rutas SPA
  services/        cliente API y servicios por dominio
  stores/          sesiones recientes en localStorage
  utils/           etiquetas y formateadores
  views/           Dashboard, Upload, ProcessDetail, Visualization
```

## Configuracion

En desarrollo se usa `VITE_API_URL`. En Docker, `server.js` sirve `/config.js` y lee `API_BASE_URL`, configurado por `FRONTEND_API_BASE_URL` en `docker-compose.yml`.

```env
VITE_API_URL=http://localhost:8000
FRONTEND_API_BASE_URL=http://localhost:8000
```

## Comandos

```bash
npm install
npm run build
npm run dev
```
