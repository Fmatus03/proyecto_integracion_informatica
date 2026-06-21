# Reusable Project Harness

Este directorio contiene el motor operativo reutilizable del harness. Es documentacion auxiliar: la autoridad normativa del core es `FV_05_Enmienda_Harness_2026_06_12.md`. La configuracion especifica del proyecto activo vive bajo `projects/<ProjectName>/`.

## Que contiene

- `runtime.py`: runtime ejecutable que aplica transiciones, gates, roles, claims, evidencia, trazabilidad e integridad de estado.
- `cli.py`: entrada de linea de comandos para operar el runtime.
- `eval_runner.py`: verificador ejecutable de los evals adversariales declarados en `evals/`.
- `validation.py`: validadores compartidos para schemas, referencias seguras y confirmacion terminal.
- `prompt_validation.py`: validacion de prompts, roles, marcadores, placeholders y presupuesto de tokens.
- `tokenization.py`: conteo real de tokens mediante `tiktoken`; no usa heuristicas por caracteres.
- `runtime_contract.json`: contrato principal del harness, comandos oficiales, roles, stages, gates y artefactos requeridos.
- `prompt_contract.json` del proyecto activo: contrato de prompts, bootstrap, prompts de rol y politica de confirmacion terminal.
- `state_machine.json`: ciclo permitido de trabajo desde `PLAN` hasta estados terminales.
- `artifact_policy.json`: fallback core para reglas de artefactos; el proyecto activo puede reemplazarlo.
- `claim_policy.json`: fallback core para claims; el proyecto activo puede reemplazarlo.
- `evidence_policy.json`: fallback core para evidencia; el proyecto activo puede reemplazarlo.
- `role_policy.json`: permisos por rol y artefactos que puede producir cada rol.
- `injection_policy.json`: patrones, terminos y marcadores protegidos contra prompt injection.
- `eval_contract.json`: fallback core de evals; el proyecto activo puede reemplazarlo.
- `schemas/`: JSON Schemas estrictos usados por el runtime.
- `runs/`: directorio local de ejecuciones del harness; cada run tiene estado, logs, trazabilidad y auditoria.
- `trazabilidad/LESSONS_LEARNED.jsonl`: memoria global de lecciones para evitar repetir intentos fallidos.

## Componentes externos relacionados

- `FV_05_Enmienda_Harness_2026_06_12.md`: autoridad normativa.
- `projects/ForestVol/FORESTVOL_MVP_SPEC.md`: especificacion del proyecto activo.
- `projects/ForestVol/prompts/harness_bootstrap.md`: bootstrap prompt del proyecto activo.
- `projects/ForestVol/harness/*.json`: policies, prompt contract y contrato de evals del proyecto activo.
- `projects/ForestVol/evals/`: datasets, graders, outputs y prompts de eval del proyecto activo.
- `tests/harness/`: tests de contrato, runtime y eval runner.
- `.github/workflows/ci.yml`: CI que ejecuta tests y evals del harness.
- `requirements-harness.txt`: dependencias minimas para tests, evals y tokenizacion real del harness.

## Roles y responsabilidades

- `orchestrator`: coordina runs, avanza etapas, aplica gates y termina ejecuciones; no escribe artefactos de dominio.
- `specifier`: produce `spec.md`.
- `architect`: produce `plan.md`.
- `analyzer`: produce `tasks.md` y `analyze-report.md`.
- `implementer`: implementa tareas aprobadas fuera del harness documental.
- `validator`: produce `validation-report.md`, `test-report.md` y `final-report.md`.

El runtime aplica permisos desde `role_policy.json`. Los roles no son solo documentales.

## Gates, evidencia e integridad

Los gates son `dataset_gate`, `authority_gate`, `analysis_gate`, `claim_gate`, `test_gate` y `traceability_gate`. Ningun gate debe pasar sin actor autorizado, justificacion y evidencia verificable cuando aplique.

La evidencia valida no es nominal. Debe ser JSON con `evidence_id`, `claim`, `artifact_path`, `checksum`, `validator`, `timestamp` y `result`.

Cada run mantiene `state.json`, `cycle_log.jsonl`, `decision_log.jsonl`, `traceability.json`, `audit_log.jsonl` y `lessons_log.jsonl`. El estado usa `sha256` con `previous_hash` y `current_hash`; `validate` detecta manipulacion manual.

## Prompt Budget

El contrato de prompts del proyecto activo declara `token_budget` con `tokenizer: "tiktoken"`, `model`, `max_single_prompt_tokens` y `max_static_prompt_tokens`.

Durante la carga de contratos, el runtime cuenta tokens reales de `harness_bootstrap.md`, el prompt de eval y cada prompt de rol. Si un archivo o el conjunto estatico excede el presupuesto, el authority gate falla con `prompt_token_budget_exceeded`. Esto reemplaza cualquier estimacion por caracteres.

## Memoria operativa

El harness registra lecciones reutilizables en `lessons_log.jsonl` por run y en `trazabilidad/LESSONS_LEARNED.jsonl` a nivel global. Una leccion documenta contexto, intento, resultado, razon del fallo, que no repetir y accion recomendada.

Cuando un claim queda bloqueado por evidencia faltante, el runtime crea una leccion automatica. Tambien se pueden registrar lecciones manuales con `lesson-add` y consultarlas con `lesson-list`.
