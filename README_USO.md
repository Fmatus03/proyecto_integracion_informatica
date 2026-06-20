# Manual de Uso del Harness ForestVol 🛠️

Este documento explica de forma práctica **cómo operar e interactuar** con el Harness. Si deseas entender la teoría, arquitectura y componentes internos, consulta el archivo `README_FUNCIONAMIENTO.md`.

## 1. Requisitos Previos

*   **Python:** Versión 3.11 o superior instalada.
*   **Directorio de trabajo:** Todos los comandos deben ejecutarse desde la raíz del repositorio (`harness_con_separacion_de_proyectos`).

El comando central para todas las interacciones es `cli.py`:
```bash
python .harness/cli.py
```

---

## 2. Ciclo de Vida de una Ejecución (Run)

Para que el modelo trabaje, siempre debe existir un "Run" (ejecución) activo.

### A. Iniciar un Run
Crea el contenedor seguro de estado para iniciar el ciclo:
```bash
python .harness/cli.py init RUN-001
```

### B. Revisar el Estado Actual
Muestra la etapa en la que te encuentras, los artefactos pendientes y el registro criptográfico:
```bash
python .harness/cli.py show RUN-001
```

### C. Avanzar de Etapa (Advance)
El `orchestrator` es el encargado de empujar el estado hacia adelante una vez que el rol correspondiente terminó su trabajo.

**Avance sin artefactos requeridos (Etapas tempranas):**
```bash
python .harness/cli.py advance RUN-001 CONTEXT --actor=orchestrator
python .harness/cli.py advance RUN-001 SPECIFY --actor=orchestrator
```

**Avance con artefactos obligatorios (Etapas avanzadas):**
Si la etapa requiere un archivo (ej. `spec.md`), este debe existir físicamente en `.harness/runs/RUN-001/` antes de poder avanzar:
```bash
python .harness/cli.py advance RUN-001 PLAN_VALIDATION --artifacts=spec.md --actor=orchestrator
python .harness/cli.py advance RUN-001 TASKS --artifacts=plan.md --actor=orchestrator
```

### D. Cierre Formal (Complete)
Llegar a la etapa final requiere un *token* de confirmación humana o de un sistema de integración autorizado, además de los reportes finales:
```bash
python .harness/cli.py complete RUN-001 --artifacts=test-report.md,final-report.md --actor=orchestrator --confirmation=USER-OK-2026
```

---

## 3. Sistema de Evidencia Inmutable

El Harness no confía en promesas. Confía en *Claims* (Afirmaciones) respaldadas por evidencia física en formato JSON.

### Crear un Claim
Cuando el agente evalúa que un requerimiento se ha cumplido, debe crear un claim vinculando los archivos JSON que lo demuestran:
```bash
python .harness/cli.py claim RUN-001 dataset_contract --evidence=evidence/dataset_manifest.json,evidence/dataset_images.json --actor=orchestrator
```
*Nota: Estos archivos JSON de evidencia deben incluir el SHA256 (checksum) válido de los artefactos que evalúan.*

### Pasar un *Gate* (Puerta de control)
Las etapas más críticas requieren pasar un *Gate* aportando evidencia concreta:
```bash
python .harness/cli.py gate RUN-001 analysis_gate passed --actor=orchestrator --justification="analysis report verified" --evidence=evidence/analyze_report.json
```

---

## 4. Auditoría y Validaciones Avanzadas

### Verificar la Integridad
Comprueba matemáticamente que ningún humano o IA ha modificado a mano los logs o estados del sistema saltándose el CLI:
```bash
python .harness/cli.py validate RUN-001
```

### Ejecutar Evaluaciones Adversariales
Verifica que el Harness es resistente a "jailbreaks" e inyección de comandos simulando ataques:
```bash
python .harness/eval_runner.py --mode offline
# O a través del CLI:
python .harness/cli.py eval
```

### Ejecutar Suite de Tests
Para los desarrolladores del sistema:
```bash
python -m pytest tests/harness -v
```

---

## 5. Gestión de Errores Comunes

Si recibes bloqueos del CLI, revisa lo siguiente:
*   `missing_exit_artifacts`: Intentaste avanzar sin haber generado el archivo requerido por el rol (ej. falta `plan.md`).
*   `checksum`: Alteraste el archivo después de haber generado su evidencia. Tienes que regenerar el claim.
*   `state_integrity_failed`: Alguien editó `state.json` manualmente y el hash se rompió. Es necesario revertir o revisar los logs.
*   `role_not_authorized`: Un actor equivocado (ej. `implementer`) intentó ejecutar un comando de avance (solo `orchestrator` puede hacerlo).

---

## 6. Las Lecciones Aprendidas (Lessons Learned)

Si cometes errores, puedes registrar qué no hacer en el futuro para entrenar la memoria de próximos runs.

**Añadir una lección:**
```bash
python .harness/cli.py lesson-add RUN-001 \
  --context="Se intento aceptar código sin tests unitarios" \
  --attempted-action="advance_qa" \
  --outcome="blocked" \
  --failure-reason="Falta test-report.md" \
  --do-not-repeat="Avanzar a QA sin revisar cobertura de test" \
  --recommended-action="Asegurar ejecución de pytest antes del claim" \
  --severity=high
```

**Consultar lecciones de un run o globales:**
```bash
python .harness/cli.py lesson-list RUN-001
python .harness/cli.py lesson-list --global
```

---

## 7. Prompt de Operación para la IA

Si estás utilizando un agente de IA (como un LLM en tu editor o chat) para interactuar con este proyecto, puedes copiar y pegar este *prompt* genérico para darle instrucciones claras y evitar que se equivoque. Solo modifica los campos entre corchetes:

***

> **Rol Asignado:** Eres un agente que opera bajo las reglas estrictas del Harness de este repositorio. Tu comportamiento está gobernado por el `cli.py` interno.
> 
> **Tu Tarea Actual:** Necesito que [DESCRIBE AQUÍ LO QUE DEBE HACER LA IA, ej: "revises el código fuente de X y avances el RUN-001 a la etapa TASKS creando el archivo plan.md"].
> 
> **Reglas Críticas que debes seguir:**
> 1. **Solo Comandos CLI Oficiales:** No inventes scripts ni edites `state.json` manualmente. Todo paso de estado o validación debe hacerse exclusivamente ejecutando `python .harness/cli.py`.
> 2. **Evidencia y Artefactos:** Si la etapa exige un artefacto, créalo físicamente en `.harness/runs/[RUN_ID]/` antes de solicitar avanzar la etapa.
> 3. **Actor Correcto:** Para comandos de CLI, incluye el flag `--actor=[orchestrator / specifier / etc.]` según corresponda a la tarea. Generalmente para avanzar etapas usarás `--actor=orchestrator`.
> 4. **Manejo de Bloqueos:** Si el Harness rechaza un comando tuyo, **detente y lee el error**. Puede faltar una confirmación, un *checksum* (SHA256) en la evidencia, o un artefacto previo. Resuelve la causa raíz, no repitas ciegamente el comando.
> 5. **Directo al Punto:** Omite explicaciones innecesarias, céntrate en crear los archivos o ejecutar los comandos CLI requeridos.
