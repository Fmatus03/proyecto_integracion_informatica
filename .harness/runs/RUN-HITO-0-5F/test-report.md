# Comando

Comando ejecutado: `python -m pytest projects\ForestVol\backend\tests -q`.

# Resultado

Resultado: `27 passed in 2.86s`. El registro `test_runner.json` valida el `test_gate` con validator `test_runner`, checksum SHA-256 y resultado `pass`.

# Cobertura

La cobertura ejercita la integracion de runtime y contratos de claims relevantes para el hito: generacion de GCP desde el detector ArUco existente, sanitizacion de nombres para NodeODM, ausencia de escala basada en Ground Truth, mallado watertight, calculo de volumen, `error_percentage` y RF-09.

Tambien quedan cubiertos gates y audit mediante evidencias versionadas en el RUN. No se incorporo hardcoding del volumen exacto; `volumen_exacto.md` se usa solo como evidencia certificada para evaluar el error final.
