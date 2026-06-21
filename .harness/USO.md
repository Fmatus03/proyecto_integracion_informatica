# Uso Del Harness ForestVol

Este documento explica como operar el harness. Es documentacion auxiliar: la unica autoridad normativa es `FV_05_Enmienda_Harness_2026_06_12.md`. Si este documento contradice `FV_05`, gana `FV_05`.

## Requisitos

- Python 3.11 o superior.
- Dependencias del harness instaladas con `pip install -r requirements-harness.txt`.
- Ejecutar comandos desde la raiz del repositorio.
- Dataset y marcador definidos por `set_imagenes+guia/dataset_manifest.json`.

Comando oficial:

```bash
python .harness/cli.py
```

Alternativas cuando `python` no existe como alias:

```bash
python3 .harness/cli.py
py -3 .harness/cli.py
```

## Flujo basico

Inicializar un run:

```bash
python .harness/cli.py init RUN-001
```

Ver estado:

```bash
python .harness/cli.py show RUN-001
```

Avanzar etapas sin artefactos de salida:

```bash
python .harness/cli.py advance RUN-001 CONTEXT --actor=orchestrator
python .harness/cli.py advance RUN-001 SPECIFY --actor=orchestrator
```

Cuando una etapa exige artefactos, el archivo debe existir en `.harness/runs/<run_id>/` y pasar validacion:

```bash
python .harness/cli.py advance RUN-001 PLAN_VALIDATION --artifacts=spec.md --actor=orchestrator
python .harness/cli.py advance RUN-001 TASKS --artifacts=plan.md --actor=orchestrator
python .harness/cli.py advance RUN-001 ANALYZE --artifacts=tasks.md --actor=orchestrator
python .harness/cli.py advance RUN-001 IMPLEMENT --artifacts=analyze-report.md --actor=orchestrator
python .harness/cli.py advance RUN-001 VALIDATE --actor=orchestrator
python .harness/cli.py advance RUN-001 QA --artifacts=validation-report.md --actor=orchestrator
```

Cerrar desde `QA`:

```bash
python .harness/cli.py complete RUN-001 --artifacts=test-report.md,final-report.md --actor=orchestrator --confirmation=USER-OK-2026
```

## Evidencia verificable

No usar evidencia nominal como `valid_mesh` o `dataset_manifest` sin archivo JSON. Cada evidencia debe vivir dentro del run y apuntar a un artefacto con checksum valido.

Forma requerida:

```json
{
  "evidence_id": "dataset-manifest",
  "claim": "dataset_manifest",
  "artifact_path": "set_imagenes+guia/dataset_manifest.json",
  "checksum": "<sha256>",
  "validator": "dataset_gate",
  "timestamp": "2026-06-14T00:00:00Z",
  "result": "pass"
}
```

Evaluar un claim:

```bash
python .harness/cli.py claim RUN-001 dataset_contract --evidence=evidence/dataset_manifest.json,evidence/dataset_images.json --actor=orchestrator
```

Pasar un gate con justificacion y evidencia:

```bash
python .harness/cli.py gate RUN-001 analysis_gate passed --actor=orchestrator --justification="analysis report verified" --evidence=evidence/analyze_report.json
```

## Validacion, tests y evals

Validar integridad de un run:

```bash
python .harness/cli.py validate RUN-001
```

Ejecutar tests del harness:

```bash
python -m pytest tests/harness -v
python3 -m pytest tests/harness -v
py -3 -m pytest tests/harness -v
```

Ejecutar evals adversariales:

```bash
python .harness/eval_runner.py --mode offline
python .harness/eval_runner.py --mode live
python .harness/cli.py eval
```

El runner devuelve JSON con `total_cases`, `passed`, `failed`, `metrics`, `failures` y `overall_result`.

## Tokenizacion real

El harness usa `tiktoken` desde `requirements-harness.txt` para contar tokens reales de bootstrap, eval prompt y prompts de rol. El presupuesto vive en `projects/ForestVol/harness/prompt_contract.json` bajo `token_budget`.

Si un prompt excede el limite por archivo o el conjunto estatico excede el limite total, el runtime bloquea la carga de contratos con `prompt_token_budget_exceeded`.

## Errores comunes

- `invalid_run_id_format`: usar solo letras, numeros, guion y guion bajo.
- `missing_exit_artifacts`: falta un artefacto obligatorio para salir de la etapa actual.
- `artifact_invalid`: el artefacto existe pero no cumple estructura, contenido minimo o reglas semanticas.
- `nominal_evidence`: se intento usar evidencia nominal en vez de un JSON verificable.
- `checksum`: el checksum registrado no coincide con el artefacto.
- `guardrail_input_invalid`: una ruta, referencia o entrada intenta escapar del scope permitido.
- `role_not_authorized`: el actor no tiene permiso para esa accion.
- `state_integrity_failed`: `state.json` fue alterado o quedo inconsistente.

## Memoria de lecciones

Cada run mantiene `lessons_log.jsonl`. Ademas, el proyecto mantiene una memoria global en `trazabilidad/LESSONS_LEARNED.jsonl`.

Registrar una leccion manual:

```bash
python .harness/cli.py lesson-add RUN-001 \
  --context="Se intento aceptar RF-09 sin ground truth certificado" \
  --attempted-action="evaluate_claim:rf09_compliance" \
  --outcome="blocked" \
  --failure-reason="Faltan ground_truth_certified y error_percentage" \
  --do-not-repeat="evaluate rf09_compliance without ground_truth_certified,error_percentage" \
  --recommended-action="Crear evidencia verificable antes de evaluar RF-09" \
  --applies-when=rf09_compliance,ground_truth_certified,error_percentage \
  --severity=high
```

Listar lecciones del run:

```bash
python .harness/cli.py lesson-list RUN-001
```

Listar memoria global:

```bash
python .harness/cli.py lesson-list --global
```
