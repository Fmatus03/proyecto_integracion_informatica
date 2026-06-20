---
name: forestvol-traceability
description: >
  Hook para mapear el ciclo de 12 pasos y archivos de trazabilidad de ForestVol MVP
  (state.json, cycle_log.jsonl, usage_ledger.jsonl y trazabilidad/*.json)
  directamente en el flujo de ejecución SDD de Gentle-AI.
---

# ForestVol Traceability & State Hooks

Esta skill define las reglas obligatorias de sincronización entre el motor técnico **Gentle-AI (SDD)** y los requisitos de trazabilidad académica del proyecto **ForestVol MVP**.

---

## 1. Mapeo de Fases (Gentle-AI SDD <-> ForestVol MVP)

Cada fase del ciclo SDD de Gentle-AI tiene hooks obligatorios para el estado de ForestVol:

| Fase Gentle-AI | Acción / Etapa ForestVol | Archivos a Modificar / Crear |
|---|---|---|
| `/sdd-new` | **Paso 1–6:** Inicialización del ciclo y carga de caches. | `.factory/runs/<cycle_id>/state.json` [NEW]<br>`.factory/runs/<cycle_id>/cycle_log.jsonl` [NEW]<br>`.factory/runs/<cycle_id>/usage_ledger.jsonl` [NEW] |
| `/sdd-explore` | **Context Grounding / Analyze:** Estudio técnico de la solución. | No modifica archivos de trazabilidad. |
| `/sdd-ff` (Specs/Plan/Tasks) | **Specify, Clarify, Checklist, Plan, Tasks, Analyze.** | `specs/forestvol-mvp/spec.md`<br>`specs/forestvol-mvp/plan.md`<br>`specs/forestvol-mvp/tasks.md`<br>`specs/forestvol-mvp/analyze-report.md`<br>Crear plantillas vacías en `trazabilidad/*.json` |
| `/sdd-apply` (Implementación) | **DEV_PHASE_1 a DEV_PHASE_7:** Codificación paso a paso por hitos. | **Actualización etapa por etapa (atómica):**<br>`trazabilidad/{hito}.json`<br>`.factory/runs/<cycle_id>/state.json` (fase/hitos)<br>`.factory/runs/<cycle_id>/cycle_log.jsonl` (eventos) |
| `/sdd-verify` | **Validate & QA (Paso 8 y 9):** Ejecución de tests y chequeos de DoD. | `specs/forestvol-mvp/validation-report.md`<br>`.factory/runs/<cycle_id>/cycle_log.jsonl` (pass/fail) |
| `/sdd-archive` | **Close (Paso 10–12):** Cierre de logs, caché y reporte final. | `.factory/runs/<cycle_id>/final-report.md`<br>`.factory/runs/<cycle_id>/state.json` (status: complete)<br>Actualizar `.factory/memory/Aprendizaje.ForestVol.md` |

---

## 2. Protocolo de Ejecución en `sdd-apply` (Implementación)

Durante la escritura de código en la fase `/sdd-apply`, el implementador debe seguir este protocolo atómico por cada tarea/etapa del hito:

1. **Pre-requisito:** Verificar que existe `specs/forestvol-mvp/analyze-report.md` con `Proceed: yes`.
2. **Pre-task Hook:**
   - Registrar el inicio de la tarea en `.factory/runs/<cycle_id>/cycle_log.jsonl` con el evento `phase_started:DEV_PHASE_X`.
   - Modificar el campo `current_fase` y `status: running` en `.factory/runs/<cycle_id>/state.json`.
3. **Ejecución:** Implementar los archivos asociados a la tarea en orden estricto.
4. **Post-task Hook (DoD Check):**
   - Correr tests unitarios/locales de la tarea.
   - Si pasan y se cumple el Definition of Done de la etapa:
     - Actualizar el archivo `trazabilidad/{hito}.json` correspondiente. Cambiar el estado de la etapa a `"completada"`, detallar `justificacion`, `que_se_hizo`, `estado_resultante` y marcar items de su `checklist` como `true`.
     - Actualizar el porcentaje de avance en el `resumen_hito`.
     - Registrar evento `phase_completed:DEV_PHASE_X` o `gate_passed:X` en `cycle_log.jsonl`.
   - Si fallan:
     - Ejecutar reintento (máximo 1).
     - Si persiste el fallo, registrar causa en `cycle_log.jsonl` como `gate_failed:X` o `bloqueante_registrado`, actualizar `state.json` con `last_block_reason`, y pausar la ejecución solicitando input del usuario (`status: needs_user_input`).

---

## 3. Protocolo de Ejecución en `sdd-verify` y `sdd-archive`

Al finalizar la implementación, el validador y el orquestador deben:

1. **Verificar Cobertura:** Correr suite de tests completa (`pytest`). Validar cobertura de backend (≥80%) y servicios críticos (≥90%).
2. **Generar Validation Report:** Escribir en `specs/forestvol-mvp/validation-report.md` el resultado de las pruebas.
3. **Cierre de Hito en Trazabilidad:** Cambiar el estado del hito en `trazabilidad/{hito}.json` a `"completada"`.
4. **Generar Final Report:** Crear `.factory/runs/<cycle_id>/final-report.md`.
5. **Cierre de Ciclo:**
   - Actualizar el estado de `state.json` a `"complete"`.
   - Cerrar `cycle_log.jsonl` y calcular tokens y costo final en `usage_ledger.jsonl`.
