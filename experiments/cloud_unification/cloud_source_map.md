# Cloud Source Map

## Canonical Source

All production and MVP benchmark consumers must obtain the dense NodeODM cloud through:

`backend.app.services.cloud_provider.load_pipeline_point_cloud(session_id, settings)`

Canonical file:

`data/processed/<session_id>/point_cloud.ply`

The provider validates and exposes:

- absolute path
- SHA256
- file size
- point count
- bounding box
- centroid

## Migrated Consumers

| Consumer | Previous source | New source |
|---|---|---|
| Productive preliminary volumetry | `session["point_cloud_path"]` passed directly | `CloudProvider -> data/processed/<session>/point_cloud.ply` |
| `pdi_mvp_readiness_benchmark.py` | `surface_closure_diagnostics*/poisson_input_cloud.ply` | `CloudProvider` |
| `benchmark_pdi_robustness.py` | `surface_closure_diagnostics*/poisson_input_cloud.ply` | `CloudProvider` |
| `final_statistical_validation.py` | `surface_closure_diagnostics*/poisson_input_cloud.ply` | `CloudProvider` |
| `benchmark_volume_estimators.py` | `surface_closure_diagnostics*/poisson_input_cloud.ply` | `CloudProvider` |
| Volumetric prototypes cloud input | `poisson_input_cloud.ply` | `CloudProvider` |

## Remaining Historical/Forensic References

These files intentionally retain historical references because they document the divergence or operate on frozen legacy artifacts:

- `experiments/nodeodm_trace/nodeodm_trace.py`
- `experiments/pipeline_diagnostics/pipeline_diagnostics.py`
- `projects/ForestVol/backend/instrument_meshing_diagnostics.py`
- `projects/ForestVol/backend/instrument_boundary_edge_forensics.py`
- `experiments/repair_benchmark/repair_benchmark.py`

They are not permitted as MVP benchmark input sources.

## Direct Point Cloud Readers

`Open3D read_point_cloud` remains allowed only after the source path has been supplied by `CloudProvider` or inside low-level mesh/diagnostic readers. Benchmarks must not construct cloud paths directly.
