# Artifact Templates

These templates define the exact artifact headings used by the role prompts. Keep headings in order and replace instruction text with sourced, verifiable content.

## spec.md

# Objetivo

State the measurable project objective grounded in ForestVol context.

# Alcance

List included and excluded behavior using only trusted project context.

# Requisitos

Describe verifiable requirements for RGB image input, ArUco reference handling, metadata-free assumptions, reconstruction, volume estimation, evidence, and RF-09 when ground truth exists.

# Restricciones

Name runtime, evidence, dataset, and validation constraints that must not be bypassed.

# Riesgos

List unresolved evidence gaps, operational risks, and validation risks.

## plan.md

# Hitos

List ordered milestones that preserve the harness stages.

# Entregables

Map each milestone to concrete artifacts, code, tests, or evidence records.

# Dependencias

List data, runtime, NodeODM, calibration, evidence, and validation dependencies.

## tasks.md

# Tareas

Use stable task IDs and define one auditable task per item.

# Responsable

Assign each task to the appropriate role or project component.

# Estado

Use a clear status and name any blocking evidence gap.

## analyze-report.md

# Hallazgos

Record findings grounded in plan, spec, dataset, code, and runtime evidence.

# Riesgos

Record risks that could affect claims, gates, traceability, tests, or closure.

# Recomendacion

Name the next valid runtime-safe action.

## validation-report.md

# Validacion

State which runtime close conditions were checked.

# Pruebas

Summarize test execution and required evidence.

# Claims

State each claim status and supporting evidence.

## test-report.md

# Comando

Record the exact test command.

# Resultado

Record pass, fail, or blocked result with evidence.

# Cobertura

Describe the behavior, gates, claims, and eval risks covered.

## final-report.md

# Resumen

Summarize the run outcome.

# Evidencia

List evidence records, checksums, validators, and related artifacts.

# Decision

State whether closure is supported by runtime evidence.
