# ForestVol Harness Profile

Este directorio contiene las reglas especificas de ForestVol para el harness reusable:

- `artifact_policy.json`: valida artefactos con conceptos del dominio ForestVol.
- `claim_policy.json`: define claims como dataset, marcador, malla, ground truth y RF-09.
- `evidence_policy.json`: define evidencia aceptada y claims permitidos por gate.
- `injection_policy.json`: define patrones de prompt injection relevantes para este proyecto.
- `eval_contract.json`: conecta los evals de `projects/ForestVol/evals/`.

El motor reusable esta en `.harness/`. Para otro proyecto, se crea otro profile con la misma estructura y se actualiza `.harness/runtime_contract.json`.
