# ForestVol MVP Spec

## Objetivo

Entregar un MVP reproducible para estimar volumen de pilas de madera a partir de
imagenes RGB, con backend en Python, orquestacion del pipeline y evidencia
auditable bajo harness.

## Alcance operativo

- Carga de imagenes y validacion de contrato de entrada.
- Calibracion espacial con marcador ArUco.
- Reconstruccion fotogrametrica via NodeODM/OpenDroneMap.
- Generacion y evaluacion de malla preliminar.
- Reporte de volumen y evidencia trazable.

## Restricciones

- El control del ciclo se realiza con `orchestrator` via `.harness/cli.py`.
- No se aceptan claims sin evidencia JSON verificable.
- El cierre del run requiere reportes finales y confirmacion explicita.
