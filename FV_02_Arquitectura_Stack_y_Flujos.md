# 02. Arquitectura, Stack y Flujos — ForestVol MVP

**Proyecto:** ForestVol  
**Versión:** 5.1  
**Fecha:** 2026-06-08  
**Estado:** `complete`  
**Propósito:** definir la arquitectura objetivo, stack gobernado, estructura de repositorio, ambientes, seguridad, datos, APIs, flujo SDD del pipeline fotogramétrico, anti-patrones y checklist de arquitectura.

---

## 1. Principio arquitectónico

ForestVol MVP es **simple primero**:

```
backend FastAPI (Python 3.11)
+ motor fotogramétrico NodeODM (Docker)
+ frontend Vue.js 3 + Three.js
+ persistencia en sistema de archivos local
+ pipeline de 7 etapas bien definidas
+ specs versionadas en specs/forestvol-mvp/
+ orquestador por ciclo de 12 pasos
+ pruebas obligatorias
+ trazabilidad completa por hito
```

No se parte con microservicios, colas, Kubernetes, bases de datos, multi-cloud ni herramientas enterprise. El MVP prioriza funcionalidad verificable sobre elegancia de código.

---

## 2. Vista de arquitectura objetivo

```
Operador / Product Owner
        |
        v
Frontend Vue.js 3 (puerto 3000)
        |
        v [REST / polling]
Backend FastAPI (puerto 8000)
        |
        +-- POST /api/upload          → image_validator.py → data/uploads/{session_id}/
        +-- POST /api/calibrate/{id}  → calibration_service.py (OpenCV)
        +-- POST /api/reconstruct/{id} → nodeodm_client.py → NodeODM (puerto 3001)
        +-- GET  /api/results/{id}    → mesh_service.py + volume_service.py
        +-- GET  /api/export/{id}/json → volume.py route
        +-- GET  /api/export/{id}/csv  → volume.py route
        |
        v
NodeODM (puerto 3001) — reconstrucción SfM/MVS
        |
        v
data/processed/{session_id}/
        +-- nube_de_puntos.ply
        +-- malla.glb   (visualización Three.js)
        +-- malla.ply   (procesamiento Open3D)
        |
        v
data/exports/{session_id}/
        +-- forestvol_{id}.json
        +-- forestvol_{id}.csv
```

---

## 3. Componentes del sistema

| Componente | Responsabilidad | No debe hacer |
|---|---|---|
| Backend FastAPI | Orquestar el pipeline, exponer la API REST, gestionar sesiones. | Procesar geometría directamente sin Open3D. |
| `image_validator.py` | Validar formato, MIME, tamaño y cantidad de imágenes. | Almacenar archivos inválidos. |
| `calibration_service.py` | Detectar guía 50×50 cm con OpenCV, calcular px/cm, gestionar fallback manual. | Inventar escala si la detección falla y no hay escala manual. |
| `nodeodm_client.py` | Llamar API REST de NodeODM, hacer polling de estado, aplicar fallback de 3 intentos. | Procesar fotogrametría localmente. |
| `mesh_service.py` | Generar malla 3D con Poisson, reparar, verificar watertight, aplicar escala, exportar GLB. | Calcular volumen. |
| `volume_service.py` | Calcular volumen con `get_volume()`, bounding box, generar metadata y reporte. | Llamar a NodeODM o manipular malla. |
| Frontend Vue.js 3 | Interfaz del operador: carga, estado del pipeline, visualización 3D, exportación. | Implementar lógica de procesamiento. |
| NodeODM (Docker) | Reconstrucción fotogramétrica SfM/MVS a partir del set de imágenes. | Ser modificado o configurado por el agente. |

---

## 4. Stack aprobado y prohibido

### 4.1 Stack aprobado

| Capa | Tecnología | Versión mínima | Justificación |
|---|---|---|---|
| Lenguaje backend | Python | 3.11 | Ecosistema científico maduro (Open3D, OpenCV) |
| Framework REST | FastAPI | 0.111+ | Async nativo, validación Pydantic, OpenAPI automático |
| Motor fotogramétrico | OpenDroneMap / NodeODM | Latest stable | SfM/MVS open source con API REST |
| Detección calibración | OpenCV (cv2) | 4.9+ | Detección de contornos, homografía, calibración espacial |
| Procesamiento 3D | Open3D | 0.18+ | Construcción de malla, reparación, cálculo volumétrico |
| Frontend SPA | Vue.js | 3.4+ (Composition API) | SPA reactiva, ecosistema maduro |
| Visualización 3D web | Three.js | r165+ | Render WebGL del modelo 3D en navegador |
| HTTP client (frontend) | Axios | Latest stable | Comunicación frontend → backend |
| Build tool frontend | Vite | Latest stable | Scaffolding Vue.js 3 |
| Infraestructura | Docker + Docker Compose | 24+ / 2.24+ | Contenerización reproducible |
| Validación de datos | Pydantic | v2 | Schemas de request/response del API |
| Testing backend | pytest | 8+ | Suite de pruebas del backend |

### 4.2 Stack prohibido (sin excepción en MVP)

| Elemento | Estado |
|---|---|
| LiDAR, RTK, GCPs absolutos | Prohibido |
| YOLOv8 / modelos de deep learning | Prohibido en MVP |
| GPU CUDA | Prohibido — procesamiento solo en CPU |
| PostgreSQL, MySQL, SQLite, MongoDB | Prohibido — persistencia en sistema de archivos |
| Microservicios adicionales, colas (RabbitMQ, Kafka) | Prohibido |
| Kubernetes, Helm, Terraform | Prohibido |
| Framework backend distinto de FastAPI | Prohibido sin aprobación explícita |
| Frontend distinto de Vue.js 3 | Prohibido sin aprobación explícita |
| Librerías no listadas en stack aprobado | Requieren dependency request aprobado |
| Implementación directa desde prompt libre | Prohibido |
| Código sin task aprobada | Prohibido |
| Secretos en logs o cache | Prohibido |

### 4.3 Dependency request (para librerías no listadas)

Si se identifica la necesidad de una librería no listada:
```yaml
dependency_request:
  package: ""
  version: ""
  reason: ""
  license: ""
  alternatives: []
  approved_by: "needs_user_input"
  approval_status: "pending"
```
Bloquear implementación hasta recibir aprobación.

---

## 5. Estructura del repositorio

```
forestvol/
├── back_data/                    # Documentación del proyecto (solo lectura)
│   ├── Casos de uso
│   ├── Diagramas de arquitectura
│   ├── Dominios problemática
│   ├── Estado del arte fotogrametría
│   ├── ForestVol_v5.1_Planificacion_Completa
│   ├── Objetivos y Alcance
│   ├── Problematica Central
│   └── Requisitos
├── trazabilidad/                 # Archivos de trazabilidad JSON (un archivo por hito)
│   ├── hito_0_validacion_tecnica.json
│   ├── hito_0_5_volumetria_preliminar.json  # ⚠️ Se crea en Sprint 3, DESPUÉS de hito_1
│   ├── hito_1_calibracion_espacial.json
│   ├── hito_2_volumetria_funcional.json
│   └── hito_3_mvp_completo.json
├── .factory/                     # Control operacional del ciclo SDD
│   ├── runs/
│   │   └── <cycle_id>/
│   │       ├── state.json
│   │       ├── cycle_log.jsonl
│   │       ├── usage_ledger.jsonl
│   │       ├── index-update-report.md
│   │       └── final-report.md
│   └── memory/
│       └── Aprendizaje.ForestVol.md
├── specs/
│   └── forestvol-mvp/
│       ├── spec.md
│       ├── plan.md
│       ├── tasks.md
│       ├── analyze-report.md
│       ├── traceability-matrix.md
│       ├── test-plan.md
│       ├── validation-report.md
│       └── final-report.md
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── upload.py         # RF-01, RF-02
│   │   │       ├── calibration.py    # RF-03, RF-04, RF-05
│   │   │       ├── reconstruction.py # RF-06
│   │   │       ├── mesh.py           # RF-07
│   │   │       └── volume.py         # RF-08, RF-09, RF-10, RF-11, RF-12
│   │   ├── services/
│   │   │   ├── image_validator.py
│   │   │   ├── calibration_service.py
│   │   │   ├── nodeodm_client.py
│   │   │   ├── mesh_service.py
│   │   │   └── volume_service.py
│   │   ├── models/
│   │   │   └── schemas.py
│   │   └── main.py
│   ├── tests/
│   │   ├── unit/
│   │   │   ├── test_image_validator.py
│   │   │   ├── test_calibration_service.py
│   │   │   ├── test_mesh_service.py
│   │   │   └── test_volume_service.py
│   │   ├── integration/
│   │   │   └── test_pipeline.py
│   │   └── e2e/
│   │       └── test_full_flow.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ImageUploader.vue
│   │   │   ├── PipelineStatus.vue
│   │   │   ├── Viewer3D.vue
│   │   │   └── VolumeReport.vue
│   │   ├── views/
│   │   │   └── Dashboard.vue
│   │   ├── services/
│   │   │   └── api.js
│   │   └── App.vue
│   ├── Dockerfile
│   └── package.json
├── data/
│   ├── uploads/       # Imágenes originales — retención 30 días
│   ├── processed/     # Nubes de puntos y mallas — retención 60 días
│   └── exports/       # JSON y CSV exportados — retención 90 días
├── .env.example
├── docker-compose.yml
└── README.md
```

---

## 6. Ambientes

| Ambiente | Uso | Reglas |
|---|---|---|
| `local` | Desarrollo y pruebas del agente. | Sin secretos reales. Sin internet durante procesamiento. |
| `agent-sandbox` | Implementación y pruebas por el agente autónomo. | FS limitado a estructura del proyecto, comandos de build y test. |
| `staging` | Validación previa a release del MVP. | Dataset de prueba sintético o controlado. |
| `production` | No aplica al MVP. | Deploy solo con gate humano explícito. |

---

## 7. Configuración centralizada — `.env.example`

```env
# ── Puertos de servicio ──────────────────────────────────────────────────────
BACKEND_PORT=8000
FRONTEND_PORT=3000
NODEODM_PORT=3001

# ── Restricciones de carga ───────────────────────────────────────────────────
MIN_IMAGES=10
MAX_IMAGES=50
MAX_IMAGE_SIZE_MB=20
MAX_SESSION_SIZE_GB=1

# ── Rutas de datos ───────────────────────────────────────────────────────────
UPLOAD_PATH=data/uploads
PROCESSED_PATH=data/processed
EXPORT_PATH=data/exports

# ── Timeouts ─────────────────────────────────────────────────────────────────
NODEODM_TIMEOUT_SECONDS=1800

# ── Calibración ──────────────────────────────────────────────────────────────
CALIBRATION_CONFIDENCE_THRESHOLD=0.90

# ── Retención de datos ───────────────────────────────────────────────────────
UPLOAD_RETENTION_DAYS=30
PROCESSED_RETENTION_DAYS=60
EXPORT_RETENTION_DAYS=90
```

Toda configuración debe leerse de estas variables. No se permiten valores hardcodeados en el código fuente.

---

## 8. Seguridad

### 8.1 Controles mínimos

- Validación de **extensión y tipo MIME** simultánea en toda imagen recibida.
- Rechazo inmediato (<2 s) de archivos inválidos sin almacenarlos en disco.
- No registrar secretos, tokens ni PII en logs.
- No exponer stack traces al cliente — solo `error_code` y `message`.
- Allowlist de tipos MIME: `image/jpeg`, `image/png`.
- Limpieza automática de sesiones expiradas según política de retención.

### 8.2 Política de secretos
```
Agentes no leen secretos.
Logs redaccionan valores sensibles.
Pruebas usan datasets sintéticos o controlados.
Producción requiere gate humano explícito.
```

### 8.3 Amenazas básicas del proyecto

| Riesgo | Control |
|---|---|
| Archivos maliciosos disfrazados de imágenes | Validación de MIME + extensión + límite de tamaño. |
| Sesiones huérfanas acumulando espacio | Política de retención con limpieza automática. |
| NodeODM sin respuesta | Timeout + 3 intentos fallback + estado `FAILED`. |
| Malla incorrecta usada para volumetría | `is_watertight()` obligatorio antes de `get_volume()`. |

---

## 9. Datos y política de almacenamiento

### 9.1 Reglas del modelo de datos (sistema de archivos)

- Toda sesión tiene un `session_id` (UUID) como directorio raíz.
- Todo campo del reporte JSON tiene tipo definido y validación Pydantic.
- Todo dato de prueba es sintético (no imágenes reales del cliente en tests).
- La retención de datos queda definida en `.env.example`.

### 9.2 Formatos 3D oficiales (sin ambigüedad)

| Formato | Rol | Generado por | Consumido por |
|---|---|---|---|
| `.PLY` | Procesamiento interno | NodeODM / Open3D | Open3D |
| `.GLB` | Visualización web oficial | Open3D / conversión | Three.js |
| `.OBJ` | Depuración opcional | Open3D | Inspección manual |

### 9.3 Estructura del JSON de reporte exportable

```json
{
  "forestvol_version": "5.1",
  "session_id": "uuid",
  "timestamp": "ISO-8601",
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

**Regla de nulidad:** si `ground_truth.volume_m3` es `null`, entonces `error_percentage` **debe ser** `null`. No se puede afirmar cumplimiento de RF-09 sin Ground Truth certificado.

---

## 10. APIs — especificación completa

### Contratos de endpoints

Todos los endpoints retornan `Content-Type: application/json`. Los errores siempre incluyen `error_code` y `message`.

---

#### `GET /health`

**Response 200:**
```json
{ "status": "ok", "version": "5.1", "nodeodm_reachable": true }
```
**Response 503:**
```json
{ "error_code": "DEPENDENCY_UNAVAILABLE", "message": "NodeODM service is not reachable" }
```

---

#### `POST /api/upload`
**Request:** `multipart/form-data`, campo `files: List[UploadFile]`

**Response 200:**
```json
{ "session_id": "uuid", "image_count": 20, "valid": true, "errors": [], "pipeline_state": "VALIDATED" }
```
**Response 400 (formato):**
```json
{ "error_code": "INVALID_IMAGE_FORMAT", "message": "Only JPG and PNG are supported. Rejected: [archivo.bmp]" }
```
**Response 400 (cantidad):**
```json
{ "error_code": "INSUFFICIENT_IMAGES", "message": "Minimum 10 images required. Received: 7" }
```
**Response 413:**
```json
{ "error_code": "SESSION_SIZE_EXCEEDED", "message": "Total upload size exceeds 1 GB limit" }
```
**Códigos HTTP:** `200`, `400`, `413`, `500`

---

#### `POST /api/calibrate/{session_id}`
**Request body (opcional):**
```json
{ "manual_scale_px_per_cm": null }
```
**Response 200 (automático):**
```json
{
  "session_id": "uuid", "calibration_mode": "automatic",
  "guide_detected_in_n_images": 18, "detection_confidence": 0.92,
  "scale_px_per_cm": 12.34, "scale_error_percentage": 3.1,
  "pipeline_state": "CALIBRATED"
}
```
**Response 200 (fallback manual):**
```json
{
  "calibration_mode": "manual",
  "warning": "Automatic detection confidence below threshold. Manual scale applied.",
  "pipeline_state": "CALIBRATED"
}
```
**Response 422:**
```json
{ "error_code": "CALIBRATION_FAILED", "message": "Guide not detected and no manual scale provided." }
```
**Códigos HTTP:** `200`, `404`, `422`, `500`

---

#### `POST /api/reconstruct/{session_id}`
**Response 202:**
```json
{ "session_id": "uuid", "pipeline_state": "RECONSTRUCTION_PENDING", "message": "Poll /api/results/{session_id} for status." }
```
**Response 409:**
```json
{ "error_code": "RECONSTRUCTION_IN_PROGRESS", "message": "A reconstruction task is already running." }
```
**Response 424:**
```json
{ "error_code": "CALIBRATION_REQUIRED", "message": "Session must be CALIBRATED before reconstruction." }
```
**Códigos HTTP:** `202`, `404`, `409`, `424`, `500`

---

#### `GET /api/results/{session_id}`
**Response 200 (completado):**
```json
{
  "session_id": "uuid",
  "pipeline_state": "COMPLETED",
  "input": { "image_count": 20, "calibration_confidence": 0.92 },
  "processing": { "sfm_duration_seconds": 480, "mesh_watertight": true, "mesh_holes_percentage": 2.1 },
  "results": {
    "volume_m3": 12.3456,
    "bounding_box_m": { "length": 4.2, "width": 2.1, "height": 1.8 },
    "scale_px_per_cm": 12.34, "scale_error_percentage": 3.1
  },
  "ground_truth": { "volume_m3": null, "error_percentage": null },
  "model_url": "/api/model/uuid/mesh.glb"
}
```
**Response 200 (en progreso):**
```json
{ "session_id": "uuid", "pipeline_state": "RECONSTRUCTING", "progress_percentage": 45, "results": null }
```
**Response 200 (fallido):**
```json
{ "session_id": "uuid", "pipeline_state": "FAILED", "error_code": "NODEODM_TIMEOUT", "results": null }
```
**Códigos HTTP:** `200`, `404`, `500`

---

#### `GET /api/export/{session_id}/json`
**Response 200:** Archivo JSON con `Content-Disposition: attachment; filename="forestvol_{session_id}.json"`
**Response 424:**
```json
{ "error_code": "RESULTS_NOT_READY", "message": "Pipeline must be COMPLETED to export." }
```

---

#### `GET /api/export/{session_id}/csv`
**Response 200:** Archivo CSV.
**Columnas:** `session_id, timestamp, image_count, volume_m3, length_m, width_m, height_m, scale_px_per_cm, scale_error_pct, mesh_watertight, mesh_holes_pct, sfm_duration_s, gt_volume_m3, gt_error_pct`

---

#### `GET /api/model/{session_id}/mesh.glb`

**Descripción:** Sirve el archivo de malla 3D en formato GLB para renderizado web con Three.js. La URL de este endpoint se retorna en el campo `model_url` de `GET /api/results/{session_id}`.

**Path params:** `session_id` (UUID)

**Response 200:**  
Archivo binario GLB con headers:
```
Content-Type: model/gltf-binary
Content-Disposition: inline; filename="mesh.glb"
Cache-Control: public, max-age=3600
```

**Response 404:**
```json
{ "error_code": "SESSION_NOT_FOUND", "message": "Session not found or mesh not yet generated" }
```

**Response 424:**
```json
{ "error_code": "MESH_NOT_READY", "message": "Mesh file not available. Pipeline must reach MESH_READY state." }
```

**Códigos HTTP:** `200`, `404`, `424`, `500`

## 11. Estados operacionales del pipeline

| Estado | Descripción |
|---|---|
| `UPLOADED` | Imágenes recibidas, pendientes de validación. |
| `VALIDATED` | Todas las imágenes pasaron validación de formato, MIME y cantidad. |
| `CALIBRATION_PENDING` | Validación completada. Esperando `/api/calibrate`. |
| `CALIBRATED` | Escala métrica calculada (automática o manual). |
| `RECONSTRUCTION_PENDING` | Tarea enviada a NodeODM. En cola. |
| `RECONSTRUCTING` | NodeODM procesando activamente. |
| `POINT_CLOUD_READY` | Nube de puntos `.PLY` generada y almacenada. |
| `MESH_PENDING` | Nube disponible. Iniciando generación de malla. |
| `MESH_READY` | Malla 3D `.GLB` cerrada (watertight) generada y escalada. |
| `VOLUME_READY` | Volumen calculado en m³. Metadata completa. |
| `COMPLETED` | Pipeline finalizado. Exportación habilitada. |
| `FAILED` | Error irrecuperable. Ver campo `error_code`. |

### Tabla de transiciones

| Estado actual | Evento | Nuevo estado |
|---|---|---|
| *(inicial)* | `POST /api/upload` exitoso | `UPLOADED` → `VALIDATED` → `CALIBRATION_PENDING` |
| `UPLOADED` | Archivo inválido o cantidad insuficiente | `FAILED` |
| `CALIBRATION_PENDING` | `/api/calibrate` exitoso | `CALIBRATED` |
| `CALIBRATION_PENDING` | Detección fallida + sin escala manual | `FAILED` |
| `CALIBRATED` | `/api/reconstruct` exitoso | `RECONSTRUCTION_PENDING` → `RECONSTRUCTING` |
| `RECONSTRUCTING` | NodeODM completa | `POINT_CLOUD_READY` → `MESH_PENDING` → `MESH_READY` → `VOLUME_READY` → `COMPLETED` |
| `RECONSTRUCTING` | Timeout o error | `FAILED` |
| `MESH_PENDING` | Reparación fallida tras 2 ciclos | `FAILED` |
| `FAILED` | *(terminal)* | — |

---

## 12. Pipeline técnico — 7 etapas

| Etapa | Nombre | RF | Servicio | Transición de estado |
|---|---|---|---|---|
| 1 | Carga y Validación | RF-01, RF-02 | `image_validator.py` | → `VALIDATED` |
| 2 | Calibración Espacial | RF-03, RF-04, RF-05 | `calibration_service.py` | → `CALIBRATED` |
| 3 | Reconstrucción SfM/MVS | RF-06 | `nodeodm_client.py` | → `POINT_CLOUD_READY` |
| 4 | Generación de Malla 3D | RF-07 | `mesh_service.py` | → `MESH_READY` |
| 5 | Cálculo Volumétrico | RF-08, RF-09 | `volume_service.py` | → `COMPLETED` |
| 6 | Visualización | RF-10 | `Viewer3D.vue` + GLB endpoint | — |
| 7 | Exportación | RF-11, RF-12 | `volume.py` routes | — |

### Patrón de calibración oficial

| Atributo | Valor |
|---|---|
| Dimensiones | **50 cm × 50 cm** (exacto) |
| Material | PVC rígido |
| Color | Blanco y negro de alto contraste |
| Patrón | Tablero ajedrez **o** marcador ArUco 4×4 (ID 0) |
| Colocación | Plana sobre el castillo o en cara lateral visible desde el dron |

### Fallback NodeODM

| Intento | `feature-quality` | `pc-quality` | `min-num-features` |
|---|---|---|---|
| 1 (estándar) | `high` | `medium` | 8000 |
| 2 (degradado) | `medium` | `low` | 4000 |
| 3 (mínimo) | `low` | `low` | 2000 |
| Si falla | — | — | Estado `FAILED` + proponer Meshroom + `needs_user_input` |

### Estrategia de reparación de malla

Si `mesh.is_watertight() == False`:

**Ciclo 1:** `remove_degenerate_triangles()` → `remove_duplicated_vertices()` → `remove_unreferenced_vertices()` → `remove_duplicated_triangles()` → reevaluar.

**Ciclo 2:** reducir densidad de nube → regenerar malla → reevaluar.

**Si persiste:** registrar bloqueante. **Nunca llamar `get_volume()` sobre malla no watertight.**

---

## 13. Flujo SDD completo del proyecto

```
[Constitución ForestVol]
  -> [Specify] → specs/forestvol-mvp/spec.md
  -> [Clarify] → (preguntas abiertas de la spec)
  -> [Checklist] → requisitos claros, testables, con criterios de aceptación
  -> [Context Grounding] → indexar back_data/, código existente, aprendizajes
  -> [Plan] → specs/forestvol-mvp/plan.md
  -> [Plan Validation] → stack aprobado, dependencias verificadas
  -> [Tasks] → specs/forestvol-mvp/tasks.md (tareas atómicas por RF-XX)
  -> [Analyze] → specs/forestvol-mvp/analyze-report.md (Proceed: yes/no)
  -> [Implement] → 8 fases en orden estricto
  -> [Validate] → specs/forestvol-mvp/validation-report.md
  -> [Close] → final-report.md + usage_ledger actualizado
```

Sub-reglas:
- No pasar a `Plan` con preguntas críticas abiertas.
- No pasar a `Implement` sin `analyze-report.md` con `Proceed: yes`.
- No pasar a `Close` sin `validation-report.md` aprobado.

---

## 14. Hardware de referencia

| Componente | Especificación mínima |
|---|---|
| CPU | Intel Core i5 generación 10 o superior / AMD Ryzen 5 equivalente |
| RAM | 16 GB mínimo |
| Almacenamiento | SSD obligatorio |
| GPU | **No requerida** |
| Conectividad | Local — sin internet durante el procesamiento |

---

## 15. Anti-patrones — evitar siempre

1. Implementar desde prompt libre sin task aprobada.
2. Saltarse alguno de los 12 pasos del ciclo.
3. Escribir código antes de `analyze-report.md` con `Proceed: yes`.
4. Aceptar "implementar el backend" como una sola tarea — deben ser tasks atómicas por RF-XX.
5. Usar dependencias no listadas sin dependency request aprobado.
6. Usar base de datos cuando la spec dice sistema de archivos.
7. Llamar `get_volume()` sobre malla no watertight.
8. Hardcodear valores de configuración en lugar de leer de `.env`.
9. Calcular error volumétrico sin Ground Truth y reportarlo como válido.
10. Cerrar un hito sin actualizar el JSON de trazabilidad.
11. Guardar secretos en logs, cache o código fuente.
12. Hacer avanzar el pipeline en estado `FAILED` sin resolución documentada.
13. Ejecutar deploy productivo sin gate humano.

---

## 16. Checklist de arquitectura

- [x] Arquitectura objetivo definida.
- [x] Stack aprobado y prohibido definido con versiones.
- [x] Estructura de repositorio definida.
- [x] Ambientes definidos.
- [x] Configuración centralizada `.env.example` definida.
- [x] Seguridad mínima definida.
- [x] Política de almacenamiento y retención definida.
- [x] Formatos 3D oficiales definidos sin ambigüedad.
- [x] API REST completa con contratos definida (8 endpoints, incluyendo modelo GLB).
- [x] Estados operacionales del pipeline definidos (12 estados).
- [x] Tabla de transiciones definida.
- [x] Pipeline técnico de 7 etapas definido.
- [x] Flujo SDD completo definido.
- [x] Hardware de referencia definido.
- [x] Anti-patrones definidos.
- [x] Nota aclaratoria de orden de hitos en trazabilidad definida.
