# 01. Constitución y Especificación — ForestVol MVP

**Proyecto:** ForestVol  
**Versión:** 5.1  
**Fecha:** 2026-06-08  
**Estado:** `complete`  
**Idioma:** español neutro  
**Modo operativo:** Spec-Driven Development, controlado por orquestador, trazable, validado y reproducible.

---

## 0. Resumen Operativo

Para comportamiento del agente, leer primero:

1. `FV_05_Enmienda_Harness_2026_06_12.md`
2. este documento
3. `FV_02`

Reglas cortas:

- usar imagenes RGB provistas externamente
- no asumir EXIF, GPS ni metadata de dron
- usar `dataset_manifest.json` como fuente de verdad del dataset
- no afirmar error `<= 15%` sin Ground Truth certificado
- preferir reglas cortas y verificables sobre narrativa extensa

---

## 1. Fuentes y regla de evidencia

### 1.1 Fuentes usadas

| source_id | Tipo | Uso |
|---|---|---|
| `forestvol_planificacion_v5.1` | Planificación del proyecto | Fuente principal: hitos, pipeline, stack, hipótesis, criterios de éxito. |
| `forestvol_requisitos` | Documento de requisitos | RF-01 a RF-12, RNF-01 a RNF-05. |
| `forestvol_arquitectura` | Diagramas de arquitectura | Estructura de servicios, puertos, flujos Docker Compose. |
| `forestvol_casos_uso` | Casos de uso | Flujos del operador, interacciones con el sistema. |
| `base_sdd_v2` | Marco SDD | Reglas Spec-Driven, artefactos, gates, trazabilidad, no improvisación. |
| `base_fabrica_agentica` | Marco de fábrica | Orquestador, ciclo 12 pasos, cache, memoria, observabilidad. |

### 1.2 Política de no invención

El agente no inventa requisitos, métricas, dependencias, SLA, ambientes, credenciales ni reglas de negocio.  
Cuando una decisión no esté cubierta por evidencia del proyecto:

- Usar `TBD` si no bloquea el diseño.
- Usar `needs_user_input` si bloquea una decisión crítica.
- Usar `not_answerable` si se exige evidencia y no existe.
- **Bloquear implementación** si falta spec, plan, tasks, analyze o validación.

### 1.3 Supersesión de documentos de back_data/

> **REGLA DE AUTORIDAD:** Los documentos en `back_data/` son la fuente académica original del proyecto (entregables de curso). En caso de conflicto con esta Constitución (FV_01), la enmienda `FV_05`, o `FV_02`, **los documentos FV prevalecen siempre**.
>
> Diferencias conocidas y resueltas:
> - `back_data/Requisitos.md` define RF-01 a RF-12 con numeración distinta a la de esta Constitución (por ejemplo, su RF-09 es "reporte del resultado" y su RF-10 es "exportación JSON"). La numeración canonica es la de esta Constitución (RF-01 a RF-12 definidos en sección 9).
> - `back_data/Casos de uso.md` referenciaba RF-13 y RF-14 (inexistentes) en UC-05 — corregido: corresponden a RF-10 y RF-12.
> - `back_data/Casos de uso.md` indicaba NodeODM en puerto 3000 (UC-03) — corregido: el puerto oficial es **3001**.

---

## 2. Objetivo del proyecto

Implementar el MVP completo de ForestVol v5.1: un sistema que automatiza el cálculo del volumen de acopios de madera (castillos) utilizando fotogrametría 3D con imágenes RGB provistas externamente, sin requerir LiDAR ni coordenadas GPS absolutas.

### Hipótesis del MVP
*"Es posible calcular automáticamente el volumen aproximado de un castillo de madera utilizando únicamente imágenes fotogramétricas RGB, sin requerir sensores LiDAR ni coordenadas GPS absolutas. El error maximo de 15% solo puede afirmarse cuando exista Ground Truth certificado."*

### Transformación que produce la fábrica

```
imagen fotogramétrica RGB (provista externamente)
-> carga y validación de imágenes
-> calibración espacial con guía 50×50 cm
-> reconstrucción SfM/MVS (NodeODM)
-> generación de malla 3D watertight (Open3D)
-> cálculo de volumen en m³
-> exportación JSON/CSV + visualización 3D web
```

---

## 3. Alcance

### 3.1 Incluido en el MVP

- Pipeline de carga de imágenes JPG/PNG con validación de formato, MIME y cantidad.
- Calibración espacial automática mediante guía física de 50×50 cm detectada con OpenCV.
- Reconstrucción fotogramétrica SfM/MVS mediante NodeODM con API REST.
- Generación de malla 3D watertight con Open3D (Poisson Surface Reconstruction).
- Cálculo de volumen en m³ con `get_volume()` de Open3D.
- Exportación de reporte en formato JSON y CSV.
- Visualización 3D de la malla en el frontend con Three.js.
- Despliegue completo mediante `docker-compose up`.
- Trazabilidad completa por hito (archivos JSON en `trazabilidad/`).
- Ciclo SDD con artefactos en `specs/forestvol-mvp/`.

### 3.2 Excluido explícitamente del MVP

- Generación, simulación o captura de imágenes fotogramétricas. **Las imágenes son provistas externamente.**
- Uso de LiDAR, RTK, GCPs absolutos o sensores adicionales.
- GPU CUDA — procesamiento exclusivamente en CPU.
- Base de datos relacional o documental — persistencia en sistema de archivos local.
- Microservicios adicionales, colas de mensajes, Kubernetes.
- Deploy productivo automático sin gate humano.
- Implementación directa desde prompt libre o sin task aprobada.

### 3.3 Supuestos explícitos

| Supuesto | Estado | Acción |
|---|---|---|
| Las imágenes de entrada son provistas por el usuario (no generadas por el sistema). | Activo | No implementar captura ni generación de imágenes. |
| El Ground Truth para validar RF-09 es responsabilidad del operador. | Activo | Si no hay GT, `error_percentage = null`. No afirmar cumplimiento de RF-09 ni error `<= 15%`. |
| El hardware de referencia es CPU i5-10ª gen o equivalente, 16 GB RAM, SSD. | Activo | Todos los tiempos RNF se evalúan contra este hardware. |
| NodeODM se ejecuta en Docker como servicio local sin internet. | Activo | No depender de APIs externas durante el procesamiento. |
| Herramientas de test específicas: pytest para backend. | Activo | Usar pytest 8+. No requiere aprobación adicional. |

---

## 4. Stakeholders

| Stakeholder | Responsabilidad |
|---|---|
| Operador / Product Owner | Define objetivo, provee imágenes y Ground Truth, acepta o rechaza resultados. |
| Agente implementador (este agente) | Implementa el MVP siguiendo el ciclo SDD, stack aprobado y orden de fases. |
| Orquestador (rol interno del agente) | Controla ciclo de 12 pasos, gates, presupuesto, logs y cierre del ciclo. |

---

## 5. Principios no negociables

1. **La especificación manda.** El código es expresión de la spec. Este documento es la constitución del proyecto.
2. **Ciclo obligatorio.** El ciclo de etapas es el definido en `FV_05 §5` y `state_machine.json`. No se salta ninguna etapa. No se implementa código antes de spec → plan → tasks → analyze.
3. **Trazabilidad total.** Cada etapa produce artefactos con `cycle_id`, evidencia, justificación y estado.
4. **Stack gobernado.** Solo se usa el stack aprobado definido en el documento 02.
5. **No código sin spec.** Ningún módulo se escribe sin que exista una task aprobada que lo requiera.
6. **Tareas atómicas.** Cada task mapea a un RF-XX y a una prueba.
7. **Permisos mínimos.** Cada módulo hace solo lo que le corresponde.
8. **Dry-run primero.** Docker build, pruebas y acciones con side effects requieren verificación antes.
9. **No inventar.** Si falta un dato crítico, registrar `needs_user_input`. Nunca rellenar con suposiciones.
10. **Aprendizaje gobernado.** Bloqueos y fallos se registran en `Aprendizaje.ForestVol.md`.
11. **Bloqueo ante ambigüedad crítica.** Si falta evidencia para una decisión que afecta el pipeline, el estado es `needs_user_input`.
12. **Definition of Done obligatoria.** Una etapa no está completa hasta que código, pruebas, build Docker y trazabilidad estén listos.

---

## 6. Source of truth

Orden de autoridad para este proyecto:

```
1. FV_05_Enmienda_Harness_2026_06_12.md para reglas operativas del harness
2. Este documento (Constitución ForestVol)
3. Documento FV_02
4. Documentos back_data/ del proyecto como referencia historica no canonica en caso de conflicto
5. specs/forestvol-mvp/spec.md
6. specs/forestvol-mvp/plan.md
7. Contratos API (schemas.py + OpenAPI generado por FastAPI)
8. specs/forestvol-mvp/tasks.md
9. specs/forestvol-mvp/analyze-report.md
10. Código implementado
11. Pruebas y reportes de validación
12. Trazabilidad (trazabilidad/*.json)
13. Aprendizaje validado (.factory/memory/Aprendizaje.ForestVol.md)
```

**Regla de drift:** Si el código contradice la spec, se considera drift. Se debe actualizar la spec o corregir el código antes de cerrar el hito.

---

## 7. Stack aprobado por constitución

Ver documento **02 — Arquitectura, Stack y Flujos** para la tabla completa con versiones y justificaciones.

Resumen ejecutivo:

| Capa | Tecnología aprobada |
|---|---|
| Backend | Python 3.11 + FastAPI 0.111+ |
| Fotogrametría | OpenDroneMap / NodeODM (latest stable) |
| Calibración | OpenCV 4.9+ |
| Geometría 3D | Open3D 0.18+ |
| Frontend | Vue.js 3.4+ (Composition API) + Three.js r165+ |
| Infraestructura | Docker 24+ + Docker Compose 2.24+ |
| Validación | Pydantic v2 |
| Testing | pytest 8+ |

---

## 8. Definición de éxito del MVP

| Resultado | Clasificación | Acción |
|---|---|---|
| Error volumétrico ≤ 15% | **MVP EXITOSO** | Hipótesis validada. Documentar y entregar. |
| Error volumétrico > 15% y ≤ 20% | **MVP ACEPTABLE** | Documentar limitaciones. Justificar con literatura. Proponer sprint de ajuste. |
| Error volumétrico > 20% | **MVP FALLIDO** | Detener nuevas funcionalidades. Revisar pipeline de calibración. Reformular hipótesis. |

**El MVP está listo cuando:**
- Todo ciclo arranca con ciclo de 12 pasos.
- Todo cambio tiene task aprobada mapeada a un RF-XX.
- Toda ambigüedad crítica se aclara o bloquea.
- Todo plan usa solo stack aprobado.
- Todo RF funcional tiene prueba o validación.
- `docker-compose up --build` levanta el sistema sin errores.
- La trazabilidad de todos los hitos tiene estado `"completada"`.

---

## 9. Requisitos funcionales

| ID | Descripción | Fuente | Módulo de implementación |
|---|---|---|---|
| RF-01 | El sistema debe aceptar sets de imágenes en formato JPG y PNG. | Requisitos v5.1 | `image_validator.py` |
| RF-02 | El sistema debe rechazar archivos inválidos en <2 segundos. | Requisitos v5.1 | `image_validator.py` |
| RF-03 | El sistema debe detectar automáticamente la guía de calibración 50×50 cm. | Requisitos v5.1 | `calibration_service.py` |
| RF-04 | El sistema debe calcular la relación px/cm a partir de la guía detectada. | Requisitos v5.1 | `calibration_service.py` |
| RF-05 | Si la guía no se detecta, alertar al operador y permitir escala manual. | Requisitos v5.1 | `calibration_service.py` |
| RF-06 | El sistema debe reconstruir la nube de puntos 3D mediante NodeODM (SfM/MVS). | Requisitos v5.1 | `nodeodm_client.py` |
| RF-07 | El sistema debe generar una malla 3D cerrada (watertight) con Open3D. | Requisitos v5.1 | `mesh_service.py` |
| RF-08 | El sistema debe calcular el volumen en m³ sobre la malla escalada. | Requisitos v5.1 | `volume_service.py` |
| RF-09 | El error volumétrico debe ser ≤15% respecto al Ground Truth. | Requisitos v5.1 | `volume_service.py` |
| RF-10 | El sistema debe mostrar el modelo 3D en el frontend con Three.js. | Requisitos v5.1 | `Viewer3D.vue` |
| RF-11 | El sistema debe exportar el reporte en formato JSON. | Requisitos v5.1 | `volume.py` route |
| RF-12 | El sistema debe exportar el reporte en formato CSV. | Requisitos v5.1 | `volume.py` route |

---

## 10. Requisitos no funcionales

| ID | Descripción |
|---|---|
| RNF-01 | Tiempo de procesamiento total <30 minutos en hardware de referencia (CPU, i5-10ª gen, 16 GB RAM, SSD). |
| RNF-02 | Despliegue reproducible con `docker-compose up`. Sin configuración manual adicional. |
| RNF-03 | Sin dependencia de GPU CUDA. Procesamiento exclusivamente en CPU. |
| RNF-04 | Operación local. Sin dependencia de internet durante el procesamiento. |
| RNF-05 | El frontend debe ser una SPA accesible en el navegador sin instalación adicional. |
| RNF-06 | Arquitectura desacoplada: el frontend (SPA Vue.js) opera de manera completamente independiente del motor analítico de backend, comunicándose únicamente a través de la API REST. |
| RNF-07 | Seguridad laboral: el sistema debe permitir que el cálculo volumétrico completo se realice de forma remota, sin necesidad de que el personal ingrese al área de acopio durante el proceso de medición. |
| RNF-08 | Independencia de conectividad: el procesamiento debe ejecutarse basándose únicamente en métricas relativas provistas por la guía de calibración física. No se requiere RTK ni GCPs absolutos en terreno. |

---

## 11. Restricciones

### 11.1 Técnicas
- No usar stack fuera de la lista aprobada sin dependency request y aprobación.
- No usar base de datos — persistencia solo en sistema de archivos (`data/`).
- No crear microservicios adicionales.
- No introducir GPU CUDA, colas, Kubernetes ni herramientas enterprise.
- No ejecutar shell libre; solo operaciones de archivos, Docker y comandos de prueba.

### 11.2 Operativas
- Todo ciclo debe tener `cycle_id`.
- Todo ciclo debe pasar por los 12 pasos.
- Todo fallo crítico bloquea avance.
- Todo aprendizaje permanente requiere validación antes de escribirse.

### 11.3 De datos
- Minimizar PII — el sistema procesa imágenes de madera, no datos personales.
- Usar datos sintéticos o de prueba para tests (no imágenes reales del cliente).
- No guardar datos sensibles en logs.
- No cachear secretos ni outputs privilegiados.

---

## 12. Criterios de aceptación

| ID | Criterio | Evidencia requerida |
|---|---|---|
| AC-001 | `docker-compose up --build` levanta los 3 servicios sin errores. | Salida de terminal sin errores. |
| AC-002 | `GET /health` retorna `{"status": "ok", "nodeodm_reachable": true}`. | Log de prueba. |
| AC-003 | `POST /api/upload` acepta 10+ imágenes JPG/PNG y retorna `session_id`. | `test_image_validator.py` aprobado. |
| AC-004 | `POST /api/calibrate/{id}` detecta guía con confianza ≥0.90. | `test_calibration_service.py` aprobado. |
| AC-005 | NodeODM genera nube de puntos `.PLY` en <30 minutos. | Archivo `.PLY` en `data/processed/`. |
| AC-006 | Open3D genera malla watertight (`mesh.is_watertight() == True`). | `test_mesh_service.py` aprobado. |
| AC-007 | `GET /api/results/{id}` retorna `volume_m3` > 0 con 4 decimales. | `test_volume_service.py` aprobado. |
| AC-008 | Error volumétrico ≤15% sobre Ground Truth (si disponible). | Campo `error_percentage` en reporte. |
| AC-009 | Exportación JSON y CSV funcional y descargable. | `test_pipeline.py` aprobado. |
| AC-010 | Frontend Vue.js renderiza malla GLB con Three.js en el navegador. | `test_full_flow.py` aprobado. |
| AC-011 | Todos los hitos tienen estado `"completada"` en `trazabilidad/*.json`. | Revisión de archivos JSON. |
| AC-012 | Cobertura de pruebas ≥80% backend general, ≥90% servicios críticos. | Reporte de cobertura pytest. |

---

## 13. Matriz de trazabilidad inicial

| Requisito | Artefacto SDD | Gate | Prueba |
|---|---|---|---|
| RF-01 | `specs/forestvol-mvp/spec.md`, `tasks.md` | `spec_exists` | `test_image_validator.py` |
| RF-02 | `specs/forestvol-mvp/tasks.md` | `analyze_approved` | `test_image_validator.py` |
| RF-03 | `specs/forestvol-mvp/tasks.md` | `analyze_approved` | `test_calibration_service.py` |
| RF-04 | `specs/forestvol-mvp/tasks.md` | `analyze_approved` | `test_calibration_service.py` |
| RF-05 | `specs/forestvol-mvp/tasks.md` | `analyze_approved` | `test_calibration_service.py` |
| RF-06 | `specs/forestvol-mvp/tasks.md` | `analyze_approved` | `test_pipeline.py` |
| RF-07 | `specs/forestvol-mvp/tasks.md` | `analyze_approved` | `test_mesh_service.py` |
| RF-08 | `specs/forestvol-mvp/tasks.md` | `analyze_approved` | `test_volume_service.py` |
| RF-09 | `specs/forestvol-mvp/tasks.md` | `validation` | `test_volume_service.py` |
| RF-10 | `specs/forestvol-mvp/tasks.md` | `validation` | `test_full_flow.py` |
| RF-11 | `specs/forestvol-mvp/tasks.md` | `analyze_approved` | `test_pipeline.py` |
| RF-12 | `specs/forestvol-mvp/tasks.md` | `analyze_approved` | `test_pipeline.py` |

---

## 14. Especificación SDD que debe generarse al inicio del ciclo

Al iniciar el ciclo, el agente debe crear `specs/forestvol-mvp/spec.md` con esta estructura mínima:

```markdown
# Especificación SDD — ForestVol MVP

## 1. Nombre del sistema
- Nombre: ForestVol
- Versión: 5.1 MVP
- Dueño: TBD (operador del proyecto)
- Fecha: YYYY-MM-DD

## 2. Objetivo
- Qué resuelve: cálculo automatizado del volumen de castillos de madera mediante fotogrametría.
- Para quién: operadores forestales con dron.
- Resultado esperado: volumen en m³ con error ≤15% respecto al Ground Truth.

## 3. Usuarios y roles
| Rol | Qué puede hacer | Restricciones |
|---|---|---|
| Operador | Cargar imágenes, iniciar pipeline, visualizar y exportar resultados. | No accede al backend directamente. |

## 4. Flujos transaccionales
| Flujo | Actor | Entrada | Acción | Salida | Error esperado |
|---|---|---|---|---|---|
| Carga de imágenes | Operador | Set JPG/PNG | POST /api/upload | session_id + estado | INVALID_FORMAT, INSUFFICIENT_IMAGES |
| Calibración | Operador | session_id | POST /api/calibrate | scale_px_per_cm | CALIBRATION_FAILED |
| Reconstrucción | Operador | session_id | POST /api/reconstruct | RECONSTRUCTION_PENDING | NODEODM_TIMEOUT |
| Consulta resultado | Operador | session_id | GET /api/results | volume_m3 | RESULTS_NOT_READY |
| Exportación | Operador | session_id | GET /api/export | JSON / CSV | RESULTS_NOT_READY |

## 5. Requisitos funcionales
[Ver sección 9 de la Constitución: RF-01 a RF-12]

## 6. Requisitos no funcionales
[Ver sección 10 de la Constitución: RNF-01 a RNF-05]

## 7. Datos
| Entidad | Campos principales | Sensible | Retención | Validaciones |
|---|---|---|---|---|
| Sesión | session_id, image_count, pipeline_state | No | 30-90 días | UUID válido, estado en enum |
| Imagen | filename, size_bytes, mime_type | No | 30 días | MIME image/jpeg o image/png |
| Resultado | volume_m3, bounding_box, scale_px_per_cm | No | 90 días | volume_m3 > 0, 4 decimales |

## 8. Base de datos
- Tipo: Sistema de archivos local (sin base de datos en MVP)
- Justificación: MVP académico sin requerimiento de concurrencia ni consultas relacionales.
- Migraciones: no aplica.

## 9. API
[Ver documento 02 — sección Especificación API Completa]

## 10. Frontend
- Pantallas: Dashboard único con ImageUploader, PipelineStatus, Viewer3D, VolumeReport.
- Componentes: 4 componentes Vue.js con Composition API.
- Estados: loading, processing, completed, error por componente.
- Validaciones: formato de archivos en cliente antes de upload.

## 11. Criterios de aceptación
[Ver sección 12 de la Constitución: AC-001 a AC-012]

## 12. Pruebas esperadas
- Unitarias: test_image_validator, test_calibration_service, test_mesh_service, test_volume_service.
- Integración: test_pipeline (flujo completo upload→export).
- E2E: test_full_flow (perspectiva del operador).
- Seguridad básica: validación de MIME, sin secretos en logs.

## 13. Fuera de alcance
- OOS-001: Generación o captura de imágenes.
- OOS-002: GPU CUDA.
- OOS-003: Base de datos relacional o documental.
- OOS-004: Deploy productivo automático.
- OOS-005: Multi-usuario / autenticación.

## 14. Preguntas abiertas
- Q-001: ¿Se proveerá dataset oficial con Ground Truth para validar RF-09?
- Q-002: ¿Existe presupuesto de tokens/tiempo por ciclo?
```

---

## 15. Política de no improvisación

| Situación | Acción obligatoria |
|---|---|
| Falta Ground Truth para validar RF-09 | `ground_truth_disponible: false`, `error_percentage: null`. No afirmar cumplimiento. |
| NodeODM no disponible tras 3 intentos | Registrar `needs_user_input`. Proponer Meshroom. Esperar decisión. |
| Malla no watertight tras 2 ciclos | Bloquear cálculo de volumen. Registrar bloqueante. |
| Error volumétrico >25% en Hito 0.5 | Detener avance a Hito 2. Revisar calibración. Registrar bloqueante. |
| Librería no listada en stack aprobado | Crear `dependency_request`. Bloquear implementación hasta aprobación. |
| Cambio no trazado a task aprobada | Crear finding de scope creep. Volver a analyze. |
| Código contradice spec | Abrir drift finding. Corregir antes de cerrar hito. |

---

## 16. Estados terminales del ciclo

Ver `FV_05_Enmienda_Harness_2026_06_12.md` §5 y `.harness/state_machine.json` para la lista canónica de etapas y estados terminales.

Resumen operativo:
- `complete` → todos los gates críticos pasan, DoD cumplida
- `needs_user_input` → falta decisión del usuario para avanzar
- `not_answerable` → no hay evidencia suficiente para una decisión factual
- `error` → falló herramienta, validación o ejecución no recuperable
- `blocked` → claim o gate bloqueado sin posibilidad de avance

---

## 17. Checklist de constitución

- [x] Objetivo definido.
- [x] Alcance definido con exclusiones explícitas.
- [x] Stakeholders definidos.
- [x] Principios no negociables definidos (12).
- [x] Source-of-truth definido.
- [x] Clasificación de éxito del MVP definida.
- [x] Requisitos funcionales definidos (RF-01 a RF-12).
- [x] Requisitos no funcionales definidos (RNF-01 a RNF-08).
- [x] Restricciones técnicas y operativas definidas.
- [x] Criterios de aceptación definidos (AC-001 a AC-012).
- [x] Matriz de trazabilidad inicial definida.
- [x] Política de no improvisación definida.
- [x] Template de spec SDD a generar definido.
- [x] Regla de supersesión de documentos back_data/ definida.
