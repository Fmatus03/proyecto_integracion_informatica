# Project Profiles

Cada carpeta dentro de `projects/` representa un proyecto completo gobernado por el mismo harness core.

Estructura esperada:

```text
projects/<ProjectName>/
  <PROJECT_SPEC>.md
  prompts/
    harness_bootstrap.md
  harness/
    artifact_policy.json
    claim_policy.json
    evidence_policy.json
    injection_policy.json
    eval_contract.json
    prompt_contract.json
  evals/
    datasets/
    graders/
    outputs/
    prompts/
```

El archivo `.harness/runtime_contract.json` elige el proyecto activo con:

```json
{
  "project_id": "ForestVol",
  "project_root": "projects/ForestVol",
  "bootstrap_prompt": "projects/ForestVol/prompts/harness_bootstrap.md",
  "project_profile": {
    "artifact_policy": "projects/ForestVol/harness/artifact_policy.json",
    "claim_policy": "projects/ForestVol/harness/claim_policy.json",
    "evidence_policy": "projects/ForestVol/harness/evidence_policy.json",
    "injection_policy": "projects/ForestVol/harness/injection_policy.json",
    "eval_contract": "projects/ForestVol/harness/eval_contract.json",
    "prompt_contract": "projects/ForestVol/harness/prompt_contract.json",
    "dataset_manifest": "set_imagenes+guia/dataset_manifest.json"
  }
}
```

Para crear otro proyecto, por ejemplo `BreweryOps`, se crea `projects/BreweryOps/` con su propia especificacion, policies y evals. El runtime, CLI, stages, roles, logs, memoria de lecciones e integridad siguen viviendo en `.harness/`.
