# Traceability

- Timestamp: 2026-07-02 17:11:59.
- Se leyo el pedido del usuario y se definio una auditoria offline encapsulada.
- Se uso nube RAW: `C:\Users\Fabian Matus\OneDrive\Escritorio\harness_con_separacion_de_proyectos\projects\ForestVol\data\processed\971d6e25-8ff0-41d2-8784-c981dec7ccbf\point_cloud.ply`.
- Se uso nube final de volumen para regiones/contexto: `C:\Users\Fabian Matus\OneDrive\Escritorio\harness_con_separacion_de_proyectos\experiments\volume_input_audit\selected_volume_cloud.ply`.
- Se reutilizaron contactos de: `C:\Users\Fabian Matus\OneDrive\Escritorio\harness_con_separacion_de_proyectos\experiments\local_bridge_validation\bridge_metrics.json` y `C:\Users\Fabian Matus\OneDrive\Escritorio\harness_con_separacion_de_proyectos\experiments\raw_vs_voxel_connectivity_validation\voxel_sweep_metrics.json`.
- Decision: no ejecutar NodeODM ni funciones del pipeline productivo; solo lecturas y calculos geometricos independientes.
- Decision: clasificar soporte por camara como bloqueado si no existen tracks/depth/reconstruction de la ultima sesion.
- Evidencia primaria: point_cloud RAW escalada, regiones de contacto localizadas, continuidad previa raw-vs-voxel, metricas de densidad/normales/curvatura/espesor.
- Parametros registrados en `mechanism_metrics.json`.
- Comando reproducible: `python experiments/photogrammetry_mechanism_audit/run_photogrammetry_mechanism_audit.py`.
