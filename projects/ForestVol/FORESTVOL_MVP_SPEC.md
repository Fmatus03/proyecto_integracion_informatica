# ForestVol MVP — Especificaciones Técnicas

**Versión**: 5.1 | **Modalidad**: Docker Compose, CPU-only, operación local

---

## 1. Descripción General

ForestVol es un sistema que automatiza el cálculo del volumen de acopios de madera (castillos) mediante fotogrametría 3D. El operador carga un set de imágenes RGB capturadas por dron; el sistema las procesa en un pipeline de 7 etapas y entrega el volumen en m³.

**Hipótesis del MVP**: Es posible calcular automáticamente el volumen aproximado de un castillo de madera usando únicamente imágenes fotogramétricas RGB, sin LiDAR ni coordenadas GPS absolutas, con un error máximo del 15%.

**Alcance estricto**: El sistema recibe imágenes ya capturadas. No genera, simula ni captura imágenes.

---

## 2. Criterios de Éxito

### Clasificación de resultado

| Error volumétrico | Clasificación |
|---|---|
| ≤ 15% | MVP EXITOSO — Hipótesis validada |
| > 15% y ≤ 20% | MVP ACEPTABLE — Documentar limitaciones y proponer sprint de ajuste |
| > 20% | MVP FALLIDO — Revisar pipeline de calibración, reformular hipótesis |

### Criterios formales

- Procesamiento de al menos 10 imágenes fotogramétricas JPG/PNG.
- Reconstrucción de geometría 3D válida y cerrada (agujeros < 5%).
- Volumen expresado en m³.
- Error volumétrico ≤ 15% respecto al Ground Truth.
- Flujo completo sin intervención técnica manual.
- Despliegue reproducible con `docker-compose up` en hardware de referencia (CPU, sin GPU CUDA).

---

## 3. Hardware de Referencia

| Componente | Especificación mínima |
|---|---|
| CPU | Intel Core i5 gen. 10 / AMD Ryzen 5 equivalente |
| RAM | 16 GB |
| Almacenamiento | SSD (no HDD) |
| GPU | No requerida — procesamiento exclusivo en CPU |
| Conectividad | Local — sin internet durante el procesamiento |

---

## 4. Stack Tecnológico

| Componente | Tecnología | Versión mínima |
|---|---|---|
| Lenguaje backend | Python | 3.11 |
| Framework REST | FastAPI | 0.111+ |
| Motor fotogramétrico | OpenDroneMap / NodeODM | Latest stable |
| Detección y calibración | OpenCV (cv2) | 4.9+ |
| Procesamiento 3D | Open3D | 0.18+ |
| Frontend SPA | Vue.js | 3.4+ (Composition API) |
| Visualización 3D web | Three.js | r165+ |
| Infraestructura | Docker + Docker Compose | 24+ / 2.24+ |
| Validación de datos | Pydantic | v2 |
| Testing | pytest | 8+ |

**Exclusiones explícitas del MVP**: LiDAR, RTK, GCPs, YOLOv8, GPU CUDA, bases de datos relacionales, sistemas de mensajería.

---

## 5. Arquitectura

### Servicios Docker Compose

| Servicio | Base | Puerto | Rol |
|---|---|---|---|
| `forestvol-backend` | Python 3.11-slim | 8000 | API FastAPI — orquestador del pipeline |
| `forestvol-frontend` | Node 20-alpine | 3000 | SPA Vue.js — interfaz del operador |
| `nodeodm` | opendronemap/nodeodm | 3001 | Motor SfM/MVS |

### Patrones

- **Backend**: Clean Architecture — separación de rutas, servicios y modelos.
- **Frontend**: SPA Vue.js 3 (Composition API) + Three.js + Axios.
- **Comunicación**: REST síncrono para carga/consultas. Polling del frontend para estado NodeODM (long-running task).
- **Persistencia**: Sistema de archivos local. Sin base de datos en MVP.
- **Configuración**: Todo desde variables de entorno. Sin valores hardcodeados.

### Estructura de Directorios

```
forestvol/
├── back_data/                  # Documentación del proyecto (solo lectura)
├── trazabilidad/               # Archivos de trazabilidad JSON (un archivo por hito)
│   ├── hito_0_validacion_tecnica.json
│   ├── hito_0_5_volumetria_preliminar.json
│   ├── hito_1_calibracion_espacial.json
│   ├── hito_2_volumetria_funcional.json
│   └── hito_3_mvp_completo.json
├── backend/
│   ├── app/
│   │   ├── api/routes/
│   │   │   ├── upload.py         # RF-01, RF-02
│   │   │   ├── calibration.py    # RF-03, RF-04, RF-05
│   │   │   ├── reconstruction.py # RF-06
│   │   │   ├── mesh.py           # RF-07
│   │   │   └── volume.py         # RF-08, RF-09, RF-10, RF-11, RF-12
│   │   ├── services/
│   │   │   ├── image_validator.py
│   │   │   ├── calibration_service.py
│   │   │   ├── nodeodm_client.py
│   │   │   ├── mesh_service.py
│   │   │   └── volume_service.py
│   │   ├── models/schemas.py
│   │   └── main.py
│   ├── tests/
│   │   ├── unit/
│   │   │   ├── test_image_validator.py
│   │   │   ├── test_calibration_service.py
│   │   │   ├── test_mesh_service.py
│   │   │   └── test_volume_service.py
│   │   ├── integration/test_pipeline.py
│   │   └── e2e/test_full_flow.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ImageUploader.vue
│   │   │   ├── PipelineStatus.vue
│   │   │   ├── Viewer3D.vue
│   │   │   └── VolumeReport.vue
│   │   ├── views/Dashboard.vue
│   │   ├── services/api.js
│   │   └── App.vue
│   ├── Dockerfile
│   └── package.json
├── nodeodm/
├── data/
│   ├── uploads/       # Imágenes del operador (retención: 30 días)
│   ├── processed/     # Outputs del pipeline (retención: 60 días)
│   └── exports/       # JSON/CSV exportados (retención: 90 días)
├── .github/
│   └── workflows/
│       └── ci.yml     # GitHub Actions — ejecución de tests
├── .env.example
├── docker-compose.yml
└── README.md
```

---

## 6. Control de Versiones y CI/CD

### Git

- El repositorio se gestiona con Git desde el inicio del proyecto.
- Cada hito debe tener al menos un commit con mensaje descriptivo que lo identifique.
- El `.gitignore` debe excluir `data/`, `__pycache__/`, `.env`, y artefactos de build.
- Bootstrap obligatorio del repositorio remoto para este MVP:

```bash
echo "# proyecto_integracion_informatica" >> README.md
git init
git add README.md
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/Fmatus03/proyecto_integracion_informatica.git
git push -u origin main
```

- Si ya existe repositorio inicializado, estas instrucciones se usan como referencia normativa del origen remoto y del branch principal esperado.

### CI/CD — GitHub Actions

El archivo `.github/workflows/ci.yml` debe ejecutarse en cada `push` y `pull_request` a `main`. El workflow debe:

1. Levantar el entorno con Python 3.11.
2. Instalar dependencias del backend (`pip install -r requirements.txt`).
3. Ejecutar la suite completa de tests: `pytest backend/tests/`.
4. Reportar cobertura (`pytest --cov`).
5. Fallar el pipeline si la cobertura del backend es inferior al 80% o si algún test crítico falla.

**Ejecución local obligatoria**: los tests deben poder ejecutarse localmente con `pytest backend/tests/` antes de cada commit, para verificar funcionamiento antes del push. El `README.md` debe documentar este flujo.

---

## 7. Configuración — `.env.example`

```env
# Puertos de servicio
BACKEND_PORT=8000
FRONTEND_PORT=3000
NODEODM_PORT=3001

# Restricciones de carga
MIN_IMAGES=10
MAX_IMAGES=50
MAX_IMAGE_SIZE_MB=20
MAX_SESSION_SIZE_GB=1

# Rutas de datos
UPLOAD_PATH=data/uploads
PROCESSED_PATH=data/processed
EXPORT_PATH=data/exports

# Timeouts
NODEODM_TIMEOUT_SECONDS=1800

# Calibración
CALIBRATION_CONFIDENCE_THRESHOLD=0.90

# Retención de datos
UPLOAD_RETENTION_DAYS=30
PROCESSED_RETENTION_DAYS=60
EXPORT_RETENTION_DAYS=90
```

---

## 8. Seguridad Operacional — Límites de Validación

El backend rechaza con HTTP 400/413 cualquier solicitud que supere estos límites:

| Límite | Valor |
|---|---|
| Máximo imágenes por sesión | 50 |
| Mínimo imágenes por sesión | 10 |
| Tamaño máximo por imagen | 20 MB |
| Tamaño máximo total por sesión | 1 GB |
| Tipos MIME permitidos | `image/jpeg`, `image/png` |
| Extensiones permitidas | `.jpg`, `.jpeg`, `.png` |

**Reglas**:
- Validar extensión **y** tipo MIME simultáneamente.
- Rechazar archivos inválidos en < 2 segundos (RF-02).
- Un archivo `.jpg` con MIME `application/octet-stream` se rechaza.
- Nunca almacenar archivos inválidos en disco.

---

## 9. Almacenamiento y Retención

| Carpeta | Contenido | Retención | Formatos |
|---|---|---|---|
| `data/uploads/` | Imágenes originales | 30 días | JPG, PNG |
| `data/processed/` | Nubes de puntos, mallas, outputs intermedios | 60 días | PLY (interno), GLB (visualización), OBJ (debug) |
| `data/exports/` | Reportes descargables | 90 días | JSON, CSV |

**Formatos 3D**:
- **PLY** — formato interno. Generado por NodeODM. Consumido por Open3D.
- **GLB** — formato de visualización web. Consumido por Three.js.
- **OBJ** — solo para depuración manual.

La limpieza automática se ejecuta al inicio de cada nueva sesión (borrar sesiones expiradas). No se requiere scheduler.

---

## 10. Patrón de Calibración Oficial

### Especificación física

| Atributo | Valor |
|---|---|
| Dimensiones | 100 cm × 100 cm (exacto) |
| Material recomendado | PVC rígido |
| Patrón | **Marcador ArUco — DICT_4X4_50, ID 0** (método oficial y preferido) |
| Colocación | Plana sobre el castillo o apoyada en cara lateral visible desde el dron |

### Detección con ArUco (método principal)

El marcador ArUco es la referencia oficial de calibración. OpenCV lo detecta con precisión sub-pixel incluso con rotación, perspectiva y oclusión parcial mediante una única llamada:

```python
corners, ids, rejected = cv2.aruco.detectMarkers(
    image, cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
)
```

Esta detección es robusta a sombras y condiciones de campo. Se prefiere sobre detección de contornos genéricos.

### Flujo de `calibration_service.py`

1. Convertir imagen a escala de grises.
2. Intentar detección ArUco con `cv2.aruco.detectMarkers` (DICT_4X4_50, ID 0).
3. Si ArUco detectado: calcular lado del marcador en píxeles → dividir entre 100 cm → obtener px/cm.
4. Calcular homografía para corrección de perspectiva.
5. Si la confianza es < `CALIBRATION_CONFIDENCE_THRESHOLD` (0.90): activar fallback de escala manual.
6. Si no hay guía y no hay escala manual: retornar HTTP 422, estado `FAILED`.

**Resultado esperado**: relación `px/cm` con error ≤ 5% respecto al valor real.
**Confianza**: `imágenes_con_detección_exitosa / imágenes_donde_guía_es_visible`. La guía debe detectarse en ≥ 90% de las imágenes donde es visible.

---

## 11. Pipeline Técnico — 7 Etapas

### Etapa 1 — Carga y Validación (RF-01, RF-02)
- `POST /api/upload` recibe imágenes JPG/PNG.
- Validar extensión + MIME + cantidad (10–50) + tamaño (20 MB/img, 1 GB/sesión).
- Guardar en `data/uploads/{session_id}/`.
- Transición: `UPLOADED` → `VALIDATED`.

### Etapa 2 — Calibración Espacial (RF-03, RF-04, RF-05)
- Detectar marcador ArUco DICT_4X4_50 ID 0 en las imágenes.
- Calcular relación px/cm y matriz de escala.
- Fallback: escala manual si confianza < 0.90.
- Error de escala objetivo: ≤ 5%.
- Transición: `CALIBRATION_PENDING` → `CALIBRATED`.

### Etapa 3 — Reconstrucción SfM/MVS (RF-06)
- Llamada REST a NodeODM con las imágenes.
- Polling de estado hasta completar (timeout: `NODEODM_TIMEOUT_SECONDS`).
- Artefacto de salida: nube de puntos densa `.PLY`. Cobertura objetivo ≥ 90%.
- 3 intentos con parámetros degradados antes de declarar `FAILED` (ver sección 12).
- Transición: `CALIBRATED` → `RECONSTRUCTION_PENDING` → `RECONSTRUCTING` → `POINT_CLOUD_READY`.

### Etapa 4 — Generación de Malla 3D (RF-07)
- Open3D carga la nube `.PLY`.
- Algoritmo preferido: **Poisson Surface Reconstruction**. Fallback: Ball Pivoting.
- Aplicar estrategia de reparación si no es watertight (ver sección 13).
- Aplicar escala métrica (px/cm de Etapa 2).
- Verificar `mesh.is_watertight()`.
- Exportar en GLB (visualización) y PLY (interno).
- Transición: `POINT_CLOUD_READY` → `MESH_PENDING` → `MESH_READY`.

### Etapa 5 — Cálculo Volumétrico (RF-08, RF-09)
- Verificar `mesh.is_watertight() == True` antes de calcular. **Nunca calcular sobre malla no watertight.**
- Calcular volumen con `open3d.geometry.TriangleMesh.get_volume()`.
- Resultado en m³ con 4 decimales.
- Calcular bounding box (largo, ancho, alto en metros).
- Transición: `MESH_READY` → `VOLUME_READY` → `COMPLETED`.

### Etapa 6 — Visualización (RF-10)
- Backend expone el `.GLB` para consumo del frontend.
- Frontend renderiza con Three.js (OrbitControls, iluminación básica, fondo neutro).
- Panel de métricas: volumen m³, dimensiones bounding box, n° imágenes, tiempo total.

### Etapa 7 — Exportación (RF-11, RF-12)
- `GET /api/export/{session_id}/json` descarga JSON estructurado.
- `GET /api/export/{session_id}/csv` descarga CSV con columnas definidas.
- Solo disponible cuando `pipeline_state == "COMPLETED"`.

---

## 12. Fallback NodeODM

Intentos en orden estricto:

| Intento | `feature-quality` | `pc-quality` | Parámetro adicional |
|---|---|---|---|
| 1 | `high` | `medium` | `min-num-features: 8000` |
| 2 | `medium` | `low` | `min-num-features: 4000` |
| 3 | `low` | `low` | `min-num-features: 2000` |
| Fallo tras 3 intentos | — | — | `pipeline_state = FAILED`. Registrar en trazabilidad. Proponer Meshroom como alternativa manual. |

Registrar en trazabilidad: qué intento falló, mensaje de error, parámetros utilizados.

---

## 13. Estrategia de Reparación de Malla

Si `mesh.is_watertight() == False`:

**Ciclo 1**:
```python
mesh.remove_degenerate_triangles()
mesh.remove_duplicated_vertices()
mesh.remove_unreferenced_vertices()
mesh.remove_duplicated_triangles()
```
→ Reevaluar `mesh.is_watertight()`.

**Ciclo 2** (si persiste):
- Reducir densidad de la nube (`high` → `medium`).
- Regenerar malla.
- Reevaluar `mesh.is_watertight()`.

**Si persiste tras ciclo 2**: registrar como `bloqueada`. No calcular volumen. Registrar porcentaje de agujeros y métodos aplicados en trazabilidad.

---

## 14. Estados del Pipeline

| Estado | Descripción |
|---|---|
| `UPLOADED` | Imágenes recibidas |
| `VALIDATED` | Imágenes validadas (formato, MIME, cantidad) |
| `CALIBRATION_PENDING` | Esperando llamada a `/api/calibrate` |
| `CALIBRATED` | Escala métrica calculada |
| `RECONSTRUCTION_PENDING` | Tarea enviada a NodeODM, en cola |
| `RECONSTRUCTING` | NodeODM procesando |
| `POINT_CLOUD_READY` | Nube de puntos `.PLY` generada |
| `MESH_PENDING` | Iniciando generación de malla |
| `MESH_READY` | Malla watertight generada y escalada |
| `VOLUME_READY` | Volumen calculado, metadata completa |
| `COMPLETED` | Pipeline finalizado, exportación habilitada |
| `FAILED` | Error irrecuperable (terminal) |

### Condiciones de entrada en `FAILED`

- Archivo con extensión permitida pero MIME inválido.
- Menos de 10 imágenes.
- Confianza de detección < umbral y sin escala manual.
- NodeODM no disponible tras 3 intentos.
- Timeout de NodeODM superado.
- Malla no watertight tras 2 ciclos de reparación.
- Sesión no encontrada o expirada.

---

## 15. API — Contratos de Endpoints

Todos los endpoints retornan `Content-Type: application/json`. Los errores siempre incluyen `error_code` y `message`. Nunca se exponen stack traces al cliente.

---

### `GET /health`

**Response 200**:
```json
{
  "status": "ok",
  "version": "5.1",
  "nodeodm_reachable": true
}
```

**Response 503**:
```json
{
  "error_code": "DEPENDENCY_UNAVAILABLE",
  "message": "NodeODM service is not reachable at configured host"
}
```

---

### `POST /api/upload`

**Request**: `multipart/form-data` — campo `files: List[UploadFile]`

**Response 200**:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "image_count": 20,
  "valid": true,
  "errors": [],
  "pipeline_state": "VALIDATED"
}
```

**Errores**: `400 INVALID_IMAGE_FORMAT`, `400 INSUFFICIENT_IMAGES`, `413 SESSION_SIZE_EXCEEDED`, `500`

---

### `POST /api/calibrate/{session_id}`

**Request Body** (opcional):
```json
{ "manual_scale_px_per_cm": null }
```

**Response 200** (detección automática exitosa):
```json
{
  "session_id": "...",
  "calibration_mode": "automatic",
  "guide_detected_in_n_images": 18,
  "detection_confidence": 0.92,
  "scale_px_per_cm": 12.34,
  "scale_error_percentage": 3.1,
  "pipeline_state": "CALIBRATED"
}
```

**Response 200** (fallback manual):
```json
{
  "session_id": "...",
  "calibration_mode": "manual",
  "guide_detected_in_n_images": 4,
  "detection_confidence": 0.41,
  "scale_px_per_cm": 11.80,
  "scale_error_percentage": null,
  "warning": "Automatic detection confidence below threshold (0.90). Manual scale applied.",
  "pipeline_state": "CALIBRATED"
}
```

**Errores**: `404 SESSION_NOT_FOUND`, `422 CALIBRATION_FAILED`, `500`

---

### `POST /api/reconstruct/{session_id}`

**Response 202**:
```json
{
  "session_id": "...",
  "pipeline_state": "RECONSTRUCTION_PENDING",
  "message": "Reconstruction task submitted to NodeODM. Poll /api/results/{session_id} for status."
}
```

**Errores**: `404 SESSION_NOT_FOUND`, `409 RECONSTRUCTION_IN_PROGRESS`, `424 CALIBRATION_REQUIRED`, `500`

---

### `GET /api/results/{session_id}`

**Response 200** (completado):
```json
{
  "session_id": "...",
  "pipeline_state": "COMPLETED",
  "input": {
    "image_count": 20,
    "image_format": "JPG",
    "calibration_guide_detected": true,
    "calibration_confidence": 0.92
  },
  "processing": {
    "sfm_duration_seconds": 480,
    "point_cloud_density": "medium",
    "mesh_watertight": true,
    "mesh_holes_percentage": 2.1,
    "mesh_repair_applied": false
  },
  "results": {
    "volume_m3": 12.3456,
    "bounding_box_m": { "length": 4.2, "width": 2.1, "height": 1.8 },
    "scale_factor_px_per_cm": 12.34,
    "scale_error_percentage": 3.1
  },
  "ground_truth": {
    "volume_m3": null,
    "error_percentage": null
  },
  "model_url": "/api/model/{session_id}/mesh.glb"
}
```

**Response 200** (en progreso):
```json
{
  "session_id": "...",
  "pipeline_state": "RECONSTRUCTING",
  "progress_percentage": 45,
  "results": null
}
```

**Response 200** (fallido):
```json
{
  "session_id": "...",
  "pipeline_state": "FAILED",
  "error_code": "NODEODM_TIMEOUT",
  "message": "NodeODM did not complete within 1800 seconds",
  "results": null
}
```

**Errores**: `404 SESSION_NOT_FOUND`, `500`

---

### `GET /api/export/{session_id}/json`

**Response 200**: archivo JSON con `Content-Disposition: attachment; filename="forestvol_{session_id}.json"`

**Errores**: `404 SESSION_NOT_FOUND`, `424 RESULTS_NOT_READY`, `500`

---

### `GET /api/export/{session_id}/csv`

**Response 200**: archivo CSV con `Content-Disposition: attachment; filename="forestvol_{session_id}.csv"`

**Columnas**: `session_id`, `timestamp`, `image_count`, `volume_m3`, `length_m`, `width_m`, `height_m`, `scale_px_per_cm`, `scale_error_pct`, `mesh_watertight`, `mesh_holes_pct`, `sfm_duration_s`, `gt_volume_m3`, `gt_error_pct`

**Errores**: `404 SESSION_NOT_FOUND`, `424 RESULTS_NOT_READY`, `500`

---

## 16. Estructura del Reporte JSON

```json
{
  "forestvol_version": "5.1",
  "session_id": "...",
  "timestamp": "2025-06-09T14:30:00Z",
  "input": {
    "image_count": 20,
    "image_format": "JPG",
    "calibration_guide_detected": true,
    "calibration_confidence": 0.92
  },
  "processing": {
    "sfm_duration_seconds": 480,
    "point_cloud_density": "medium",
    "mesh_watertight": true,
    "mesh_holes_percentage": 2.1,
    "mesh_repair_applied": false
  },
  "results": {
    "volume_m3": 12.3456,
    "bounding_box_m": { "length": 4.2, "width": 2.1, "height": 1.8 },
    "scale_factor_px_per_cm": 12.34,
    "scale_error_percentage": 3.1
  },
  "ground_truth": {
    "volume_m3": null,
    "error_percentage": null
  }
}
```

**Regla**: si `ground_truth.volume_m3` es `null`, entonces `ground_truth.error_percentage` **debe ser** `null`. No se puede afirmar cumplimiento de RF-09 sin Ground Truth certificado.

---

## 17. Ground Truth

### Métodos aceptados

| Método | Descripción |
|---|---|
| Medición manual | Cinta métrica o distanciómetro. Fórmula: largo × ancho × altura promedio. |
| Objeto de medidas conocidas | Volumen calculado a partir de dimensiones exactas de un objeto controlado (recomendado para pruebas). |
| Escaneo de referencia | Escáner 3D o LiDAR de alta precisión (si disponible). |

### Fórmula de error

```
error_percentage = (|volumen_sistema - ground_truth_volume_m3|) / ground_truth_volume_m3 × 100
```

### Regla de nulidad

Si no existe Ground Truth certificado:
- `ground_truth.volume_m3 = null`
- `ground_truth.error_percentage = null`
- No se puede afirmar cumplimiento de RF-09.
- Registrar explícitamente `"ground_truth_disponible": false` en trazabilidad.

---

## 18. Dataset del MVP

### Requerimientos mínimos

| Parámetro | Mínimo | Ideal |
|---|---|---|
| Castillos distintos | 3 | 5 |
| Imágenes por castillo | 10 | 20–30 |
| Máximo imágenes por castillo | 50 | — |

### Registro por castillo en trazabilidad

Campos obligatorios: `castillo_id`, `imagen_count`, `altura_vuelo_m`, `distancia_castillo_m`, `condiciones_iluminacion`, `guia_visible`, `ground_truth_volume_m3`, `ground_truth_metodo`.

---

## 19. Hitos y Definition of Done

### Hitos

| Hito | Criterio | Entregable clave |
|---|---|---|
| 0 — Validación Técnica (Sprint 1) | Docker + NodeODM operativos. Primera nube de puntos generada. | `data/processed/*.PLY` |
| 1 — Calibración Espacial (Sprint 2) | Detección ≥ 90%, error de escala ≤ 5%. | `calibration_service.py` con tests aprobados |
| 0.5 — Volumetría Preliminar (Sprint 3) | Error ≤ 25% sobre GT. Si > 25%: plan de contingencia. | Malla watertight en `data/processed/` |
| 2 — Volumetría Funcional (Sprint 4) | Error ≤ 15%. Pipeline end-to-end sin intervención manual. | `GET /api/results/{session_id}` funcional |
| 3 — MVP Completo (Sprint 5) | Todos los criterios anteriores. Despliegue funcional. Frontend operativo. | `docker-compose up --build` funcional |

### Definition of Done por etapa

Una etapa se considera **completada** solo cuando cumple todos estos criterios:

| Criterio | Descripción |
|---|---|
| Código implementado | El módulo o endpoint cumple su contrato de API. |
| Pruebas ejecutadas | Tests unitarios y/o de integración pasan sin errores, tanto en local como en CI. |
| Build exitoso | `docker-compose build` del servicio afectado termina sin errores. |
| Docker funcional | El servicio levanta y el endpoint responde. |
| Trazabilidad actualizada | El JSON del hito fue actualizado con estado, justificación y checklist. |
| Sin errores críticos abiertos | Sin excepciones no manejadas ni comportamientos no deterministas conocidos. |

---

## 20. Gestión de Riesgos

| Riesgo | Respuesta |
|---|---|
| NodeODM falla | Ejecutar los 3 intentos de fallback. Si todos fallan: `FAILED` en trazabilidad, proponer Meshroom, requerir decisión humana. |
| Guía no detectada (confianza < 0.90) | Activar fallback de escala manual. Registrar confianza. Sin escala manual: HTTP 422, `FAILED`. |
| Malla inválida o no cerrada | Ejecutar 2 ciclos de reparación. Si falla: registrar bloqueante, no calcular volumen. |
| Error volumétrico > 25% en Hito 0.5 | Detener avance a Hito 2. Revisar calibración. Registrar bloqueante. |
| Error volumétrico > 15% en Hito 2 | Clasificar como ACEPTABLE (15–20%) o FALLIDO (> 20%). Documentar con justificación técnica. |
| Dataset insuficiente | Validar en Hito 0 (densidad, cobertura ≥ 90%). Si no cumple: documentar y solicitar dataset adicional. |

---

## 21. Plan Maestro de Tests

### Tests Unitarios

#### `test_image_validator.py`

| Caso | Entrada | Esperado |
|---|---|---|
| JPG válido | `.jpg` + MIME `image/jpeg` | Aceptado |
| PNG válido | `.png` + MIME `image/png` | Aceptado |
| Extensión inválida | `.bmp` | HTTP 400, `INVALID_IMAGE_FORMAT` |
| MIME inválido | `.jpg` + MIME `application/octet-stream` | HTTP 400, `INVALID_IMAGE_FORMAT` |
| Archivo corrupto | Bytes aleatorios con `.jpg` | HTTP 400, `INVALID_IMAGE_FORMAT` |
| Menos de 10 imágenes | 7 archivos válidos | HTTP 400, `INSUFFICIENT_IMAGES` |
| Más de 50 imágenes | 51 archivos válidos | HTTP 400 |
| Imagen > 20 MB | Imagen de 25 MB | HTTP 413 |
| Sesión > 1 GB | N imágenes que suman > 1 GB | HTTP 413, `SESSION_SIZE_EXCEEDED` |

#### `test_calibration_service.py`

| Caso | Entrada | Esperado |
|---|---|---|
| Detección exitosa | Imagen con marcador ArUco visible y bien iluminado | Confianza ≥ 0.90, `scale_px_per_cm` correcto |
| Detección fallida | Imagen sin marcador | Confianza < 0.90, advertencia |
| Fallback manual | `manual_scale_px_per_cm: 12.0` | `calibration_mode: "manual"`, escala aplicada |
| Sin guía y sin fallback | Sin marcador, `manual_scale_px_per_cm: null` | HTTP 422, `CALIBRATION_FAILED` |
| Error de escala dentro del umbral | Marcador en imagen conocida | `scale_error_percentage ≤ 5.0` |

#### `test_mesh_service.py`

| Caso | Esperado |
|---|---|
| Nube de puntos válida | Malla generada, `is_watertight() == True` |
| Malla con agujeros < 5% | Reparación exitosa, watertight |
| Malla con agujeros > 5% | 2 ciclos intentados, `FAILED` si persiste |
| Escala aplicada | Dimensiones del bounding box correctas |

#### `test_volume_service.py`

| Caso | Esperado |
|---|---|
| Malla watertight | `volume_m3` con 4 decimales, > 0 |
| Bounding box | `length`, `width`, `height` en metros dentro de ± 5% del real |
| Malla no watertight | Excepción levantada, no retorna volumen |
| Ground Truth nulo | `error_percentage: null` |

### Tests de Integración — `test_pipeline.py`

```
POST /api/upload (10+ imágenes)         → HTTP 200, session_id
POST /api/calibrate/{session_id}        → HTTP 200, calibration_mode
POST /api/reconstruct/{session_id}      → HTTP 202
polling GET /api/results/{session_id}   → hasta COMPLETED o FAILED
GET /api/export/{session_id}/json       → HTTP 200, archivo JSON
GET /api/export/{session_id}/csv        → HTTP 200, archivo CSV con columnas correctas
```

Validaciones adicionales: existencia de `.PLY` y `.GLB` en `data/processed/{session_id}/`, existencia de JSON y CSV en `data/exports/{session_id}/`, persistencia de archivos tras completar el flujo.

### Tests E2E — `test_full_flow.py`

Simula el flujo completo del operador: carga → calibración → reconstrucción → polling → visualización → exportación JSON/CSV. Estado final esperado: `COMPLETED`, archivos descargables, sin intervención técnica.

### Cobertura Mínima

| Alcance | Cobertura mínima |
|---|---|
| Backend general | 80% |
| `calibration_service`, `mesh_service`, `volume_service` | 90% |
| `volume_service.py` (RF-08) | 100% |
| Cálculo de error (RF-09) | 100% |

### Criterio de Release (Hito 3)

No puede cerrarse si: algún test crítico falla, cobertura backend < 80%, error volumétrico > 20% sobre dataset oficial, NodeODM no ejecuta con ninguna de las 3 configuraciones de fallback.

---

## 22. Matriz de Trazabilidad RF → Implementación → Tests

| RF | Descripción | Módulo | Endpoint | Test |
|---|---|---|---|---|
| RF-01 | Aceptar JPG y PNG | `image_validator.py` | `POST /api/upload` | `test_image_validator.py` |
| RF-02 | Rechazar inválidos en < 2 s | `image_validator.py` | `POST /api/upload` | `test_image_validator.py` |
| RF-03 | Detectar guía 100×100 cm (ArUco) | `calibration_service.py` | `POST /api/calibrate/{id}` | `test_calibration_service.py` |
| RF-04 | Calcular px/cm | `calibration_service.py` | `POST /api/calibrate/{id}` | `test_calibration_service.py` |
| RF-05 | Fallback de escala manual | `calibration_service.py` | `POST /api/calibrate/{id}` | `test_calibration_service.py` |
| RF-06 | Reconstrucción SfM/MVS | `nodeodm_client.py` | `POST /api/reconstruct/{id}` | `test_pipeline.py` |
| RF-07 | Malla watertight | `mesh_service.py` | `POST /api/reconstruct/{id}` | `test_mesh_service.py` |
| RF-08 | Calcular volumen en m³ | `volume_service.py` | `GET /api/results/{id}` | `test_volume_service.py` |
| RF-09 | Error ≤ 15% | `volume_service.py` | `GET /api/results/{id}` | `test_volume_service.py` |
| RF-10 | Visualización 3D | `Viewer3D.vue` + `/api/model/{id}` | — | `test_full_flow.py` |
| RF-11 | Exportar JSON | `volume.py` route | `GET /api/export/{id}/json` | `test_pipeline.py` |
| RF-12 | Exportar CSV | `volume.py` route | `GET /api/export/{id}/csv` | `test_pipeline.py` |

### Requisitos No Funcionales Clave

| ID | Descripción |
|---|---|
| RNF-01 | Tiempo de procesamiento total < 30 minutos en hardware de referencia. |
| RNF-02 | Despliegue reproducible con `docker-compose up`. Sin configuración manual adicional. |
| RNF-03 | Sin dependencia de GPU CUDA. Procesamiento exclusivamente en CPU. |
| RNF-04 | Operación local. Sin dependencia de internet durante el procesamiento. |
| RNF-05 | Frontend SPA accesible en el navegador sin instalación adicional. |

---

## 23. Sistema de Trazabilidad

### Estructura JSON por hito

```json
{
  "hito": {
    "id": "hito_0",
    "nombre": "Validación Técnica Inicial",
    "sprint": "Sprint 1",
    "fecha_objetivo": "YYYY-MM-DD",
    "criterio_exito": "...",
    "estado": "en_progreso"
  },
  "etapas": [
    {
      "etapa_id": "hito_0_etapa_1",
      "nombre": "...",
      "estado": "completada",
      "fecha_completado": "YYYY-MM-DDTHH:MM:SSZ",
      "partes_proyecto_utilizadas": ["ruta/relativa/archivo.py"],
      "justificacion": "...",
      "que_se_hizo": "...",
      "estado_resultante": "...",
      "ground_truth_disponible": false,
      "metricas": {
        "tiempo_implementacion_min": 0,
        "tests_pasados": 0,
        "errores_encontrados": 0,
        "cobertura_pct": null
      },
      "checklist": [
        { "item": "...", "completado": true }
      ]
    }
  ],
  "resumen_hito": {
    "etapas_totales": 0,
    "etapas_completadas": 0,
    "porcentaje_avance": 0,
    "bloqueantes": [],
    "proxima_etapa": "..."
  }
}
```

### Estados válidos de etapa

`"pendiente"` | `"en_progreso"` | `"completada"` | `"bloqueada"` | `"con_contingencia"`

### Campos obligatorios por etapa

| Campo | Descripción |
|---|---|
| `partes_proyecto_utilizadas` | Rutas relativas de archivos creados o modificados. |
| `justificacion` | Decisiones de diseño, referenciando RF-XX o RNF-XX cuando aplique. |
| `que_se_hizo` | Descripción técnica precisa, suficientemente detallada para reproducir el trabajo. |
| `estado_resultante` | Estado concreto y verificable del sistema. Incluir métricas si existen. |
| `ground_truth_disponible` | `true` o `false`. Si `false`, todos los campos de error volumétrico deben ser `null`. |

### Reglas de trazabilidad

- Actualizar el JSON del hito correspondiente al completar cada etapa, antes de avanzar a la siguiente.
- Si una métrica no puede verificarse (ej. error volumétrico sin GT), dejar el campo como `null` y registrar `"ground_truth_disponible": false`.
- Si hay un bloqueante: registrar como `"bloqueada"` con descripción, alternativas evaluadas y acción propuesta.
- No marcar ninguna etapa como `"completada"` si no cumple todos los criterios de la Definition of Done.

---

## 24. Orden de Implementación

```
FASE 1 — INFRAESTRUCTURA BASE
  1.1  Inicializar repositorio Git y configurar .gitignore
       - bootstrap esperado del remoto:
         `echo "# proyecto_integracion_informatica" >> README.md`
         `git init`
         `git add README.md`
         `git commit -m "first commit"`
         `git branch -M main`
         `git remote add origin https://github.com/Fmatus03/proyecto_integracion_informatica.git`
         `git push -u origin main`
  1.2  Crear estructura de directorios completa
  1.3  Crear .env.example
  1.4  Crear docker-compose.yml con los 3 servicios
  1.5  Crear Dockerfile del backend (Python 3.11)
  1.6  Crear Dockerfile del frontend (Node 20)
  1.7  Crear main.py de FastAPI con /health y schemas base
  1.8  Crear .github/workflows/ci.yml
  1.9  Verificar docker-compose up sin errores
  → Actualizar trazabilidad/hito_0_validacion_tecnica.json (etapa 1)

FASE 2 — PIPELINE DE CARGA
  2.1  Implementar image_validator.py
  2.2  Implementar schemas.py (Pydantic v2)
  2.3  Implementar POST /api/upload
  2.4  Implementar gestión de session_id y almacenamiento en data/uploads/
  2.5  Tests unitarios test_image_validator.py — verificar local y CI
  → Actualizar trazabilidad/hito_0_validacion_tecnica.json (etapa 2)

FASE 3 — INTEGRACIÓN NODEODM
  3.1  Implementar nodeodm_client.py (REST, polling, 3 fallbacks)
  3.2  Implementar POST /api/reconstruct/{session_id}
  3.3  Probar con dataset mínimo (10+ imágenes)
  3.4  Verificar nube de puntos .PLY en data/processed/
  → Actualizar trazabilidad/hito_0_validacion_tecnica.json (etapa 3 — CIERRE HITO 0)

FASE 4 — CALIBRACIÓN ESPACIAL
  4.1  Implementar calibration_service.py con detección ArUco (DICT_4X4_50, ID 0)
  4.2  Calcular px/cm y matriz homográfica
  4.3  Implementar fallback de escala manual
  4.4  Implementar POST /api/calibrate/{session_id}
  4.5  Tests unitarios test_calibration_service.py — verificar local y CI
  → Actualizar trazabilidad/hito_1_calibracion_espacial.json (CIERRE HITO 1)

FASE 5 — MALLA 3D Y VOLUMETRÍA PRELIMINAR
  5.1  Implementar mesh_service.py (Poisson Surface Reconstruction)
  5.2  Implementar ciclos de reparación automática
  5.3  Verificación watertightness obligatoria
  5.4  Aplicar escala métrica a la malla
  5.5  Exportar GLB y PLY
  5.6  Tests unitarios test_mesh_service.py — verificar local y CI
  5.7  Cálculo volumétrico preliminar sobre dataset de prueba
  5.8  Verificar error ≤ 25% (o registrar bloqueante)
  → Actualizar trazabilidad/hito_0_5_volumetria_preliminar.json (CIERRE HITO 0.5)

FASE 6 — VOLUMETRÍA FUNCIONAL Y EXPORTACIÓN
  6.1  Implementar volume_service.py con get_volume()
  6.2  Calcular bounding box en metros
  6.3  Generar metadata completa + JSON de reporte
  6.4  Implementar GET /api/results/{session_id}
  6.5  Implementar GET /api/export/{session_id}/json
  6.6  Implementar GET /api/export/{session_id}/csv
  6.7  Tests unitarios test_volume_service.py — verificar local y CI
  6.8  Tests de integración test_pipeline.py — verificar local y CI
  6.9  Verificar pipeline end-to-end sin intervención manual
  6.10 Verificar error ≤ 15% (o clasificar MVP ACEPTABLE/FALLIDO)
  → Actualizar trazabilidad/hito_2_volumetria_funcional.json (CIERRE HITO 2)

FASE 7 — FRONTEND
  7.1  Scaffolding Vue.js 3 + Vite + Composition API
  7.2  Configurar axios en services/api.js (base URL desde env)
  7.3  ImageUploader.vue (drag & drop, validación visual)
  7.4  PipelineStatus.vue con polling de estado
  7.5  Viewer3D.vue con Three.js (GLB, OrbitControls)
  7.6  VolumeReport.vue (métricas + botones exportación)
  7.7  Dashboard.vue integrando todos los componentes
  → Actualizar trazabilidad/hito_3_mvp_completo.json (etapas frontend)

FASE 8 — ESTABILIZACIÓN Y CIERRE
  8.1  Tests e2e test_full_flow.py — verificar local y CI
  8.2  Verificar cobertura ≥ 80% backend, ≥ 90% servicios críticos
  8.3  Verificar docker-compose up --build sin errores
  8.4  README.md con instrucciones de despliegue, variables de entorno, ejecución de tests y uso
  8.5  Revisión final de todos los archivos de trazabilidad
  → Actualizar trazabilidad/hito_3_mvp_completo.json (CIERRE HITO 3)
```

---

## 25. Estándares de Código

- **Type hints** en todas las funciones públicas de Python.
- **Docstrings** en módulos y funciones públicas.
- **Comentarios** donde la lógica no sea evidente.
- **Errores explícitos**: todas las excepciones del backend retornan HTTP 4xx/5xx con `error_code` y `message`. Sin errores silenciosos. Sin stack traces expuestos al cliente.
- **Variables de entorno**: toda configuración desde `.env.example`. Sin valores hardcodeados.
- **Sin over-engineering**: priorizar funcionalidad y legibilidad sobre elegancia.
