# Funcionamiento del Harness ForestVol ⚙️

Este documento explica **qué es, qué hace y cómo funciona internamente** el Harness de ForestVol. Si buscas instrucciones de comandos, consulta el archivo `README_USO.md`.

## ¿Qué es el Harness?

El Harness es un **motor operativo y marco de seguridad (sandbox)** diseñado para controlar, auditar y gobernar la ejecución de agentes de Inteligencia Artificial. Su propósito principal es evitar que los agentes (LLMs) tomen decisiones arbitrarias, alucinen evidencia o se salten etapas críticas del desarrollo. 

Funciona como un "juez implacable": el modelo de IA propone acciones, y el Harness decide si las acepta o las bloquea basándose en contratos y evidencias estrictas comprobables (JSON, Checksums).

## ¿Qué hace exactamente?

1. **Gestión Estricta de Estado:** Fuerza a los agentes a seguir una máquina de estados predefinida (Ej: `PLAN_VALIDATION` -> `TASKS` -> `ANALYZE` -> `IMPLEMENT` -> `QA`). No se puede avanzar sin los artefactos requeridos.
2. **Validación de Evidencia Criptográfica:** No acepta afirmaciones verbales del modelo (ej. *"los tests pasaron"*). Exige un objeto JSON con un checksum (SHA256) que enlace con un archivo físico de reporte.
3. **Control de Acceso por Roles:** Define qué agente (ej. `orchestrator`, `architect`, `validator`) tiene permiso para realizar qué acciones y producir qué artefactos.
4. **Trazabilidad Inmutable:** Cada decisión, intento bloqueado o avance de etapa queda registrado en logs (`decision_log.jsonl`, `cycle_log.jsonl`), permitiendo auditorías perfectas.
5. **Memoria Automática (Lessons Learned):** Cuando el agente comete un error y el Harness lo bloquea, el sistema registra una "lección aprendida" para que el modelo no repita el fallo en iteraciones futuras.

---

## Componentes y Arquitectura Base

El núcleo operativo se encuentra en el directorio `.harness/` y se compone de:

### Motores Ejecutables
*   `runtime.py`: Es el "cerebro" del Harness. Valida las reglas de transición, procesa los claims (afirmaciones) y evalúa si la evidencia cumple con los requisitos criptográficos.
*   `cli.py`: La interfaz de línea de comandos. Los agentes (o los humanos) interactúan con el runtime exclusivamente enviando comandos a este CLI.
*   `eval_runner.py`: Motor de evaluaciones adversariales que ejecuta pruebas automatizadas contra el Harness para garantizar que no puede ser hackeado mediante "prompt injection".

### Contratos y Políticas (Reglas del Juego)
El comportamiento del runtime se rige por archivos de configuración estáticos, evitando el uso de lenguaje natural ambiguo:
*   `runtime_contract.json`: Define los comandos disponibles, roles y etapas del ciclo de vida.
*   `state_machine.json`: Define las transiciones legales (de qué etapa se puede pasar a qué otra).
*   `role_policy.json`: Mapeo de permisos (quién puede hacer qué).
*   `injection_policy.json`: Lista negra de patrones y palabras para detectar intentos de evasión por parte de la IA.
*   `*_policy.json` (artifacts, claims, evidence): Reglas de contingencia y validación estructural.

### El Estado del Run (`.harness/runs/`)
Cada ejecución ocurre en un contenedor lógico llamado `run` (ej. `RUN-001`). Dentro de este directorio, el Harness mantiene:
*   `state.json`: El estado actual. Protegido con hashing encadenado (`previous_hash`, `current_hash`) para que nadie (ni el modelo ni el usuario) pueda modificarlo manualmente con un editor de texto sin romper la firma.
*   `*log.jsonl`: Archivos de trazabilidad absoluta de cada milisegundo de ejecución.

---

## Roles Principales del Ecosistema

Para separar las responsabilidades, el Harness divide el trabajo cognitivo del modelo en "Actores":

1.  **Orchestrator (Orquestador):** El único rol autorizado para hablar con el CLI y pedir transiciones de estado. No programa ni diseña, solo coordina.
2.  **Specifier / Architect:** Crean especificaciones y planes arquitectónicos (`spec.md`, `plan.md`).
3.  **Analyzer:** Desglosa el plan en tareas discretas (`tasks.md`).
4.  **Implementer:** Escribe el código o contenido real (fuera del control documental directo del harness, pero sujeto a sus métricas).
5.  **Validator:** Ejecuta tests, analiza resultados y emite reportes formales (`validation-report.md`) que el Orchestrator usará como evidencia para cerrar el ciclo.
