# Resumen

RUN-HITO-0-5F integra la recuperacion de escala con el detector ArUco ya existente y genera dinamicamente `gcp_list.txt` para NodeODM. La nube PLY resultante se procesa con segmentacion geometrica del acopio y se exporta una malla cerrada.

# Evidencia

Evidencia verificable con checksum y validator: `valid_mesh.json`, `ground_truth_certified.json`, `error_percentage.json` y `test_runner.json`. Artefactos principales: `gcp_list.txt`, `point_cloud.ply`, `preliminary_mesh_RUN-HITO-0-5F_segmented.ply`, `preliminary_mesh_RUN-HITO-0-5F_segmented.glb` y `rf09-evidence.json`.

Volumen calculado: 117.6496 m3. Ground Truth certificado: 119.74 m3. Error: 1.7458%, menor al umbral RF-09 de 15%.

# Decision

Decision: cierre del RUN por cumplimiento. `claim_gate` esta passed, `test_gate` queda respaldado por tests passing y no existen claims bloqueados. El close/cierre se solicita con evidencia real, audit trail e integridad de estado conservada por el Harness.
