# PDI Productive Migration Validation

Run ID: `RUN-PDI-PRODUCTIVE-MIGRATION-01`

## Scope

- Productive backend and frontend were rebuilt with PDI as official volume estimator.
- Validation used the official API flow: upload, calibrate, reconstruct, poll results.
- No experimental benchmark script was used for the final API validation.
- Ground Truth was used only for final error calculation.

## Results

| Dataset | State | Volume | Method | Confidence | FAIL gates | Error % | Runtime |
|---|---|---:|---|---:|---:|---:|---:|
| Set 1 | COMPLETED | 69.8281 m3 | point_density_integration | 100.0% HIGH | 0 | 41.6836 | 292.533 s |
| Set 2 | COMPLETED | 39.0156 m3 | point_density_integration | 25.0% CRITICAL | 5 | 67.4164 | 335.804 s |

## Evidence

- `projects/ForestVol/data/pdi_productive_migration_hito05_set1.json`
- `projects/ForestVol/data/pdi_productive_migration_hito05_set2.json`
- `projects/ForestVol/data/pdi_productive_migration_summary.csv`

## Integration Status

PDI is integrated as the official estimator:

- API returns `volume_method = point_density_integration`.
- API returns `confidence_score`, `confidence_level`, `quality_gates`, `diagnostic`, and `pdi_metrics`.
- Mesh fields remain available for compatibility, but are null by default because legacy mesh is disabled.
- Poisson/Alpha/repair no longer provide official volume.

## Acceptance Status

Hito 0.5 acceptance is blocked by volumetric error:

- Set 1 error: `41.6836%`.
- Set 2 error: `67.4164%`.
- Both exceed the Hito 0.5 criterion (`<= 25%`).

## Blocking Module

The blocking condition is not a code exception. It is an acceptance failure in:

- `backend/app/services/mesh_service.py`

Responsible stage:

- PDI on the freshly reconstructed and segmented point cloud.

Why it blocks closure:

- The productive pipeline completes, but the official Hito 0.5 criterion requires volumetric error within threshold.
- The current official end-to-end point clouds produce PDI estimates far below Ground Truth.
- Per project restriction, no parameter tuning, algorithm replacement, Poisson fallback, or new research path was introduced.

Minimum next action:

- Review capture/segmentation quality and scale evidence as a product-quality issue before declaring Hito 0.5 successful.
- Do not change PDI parameters using Ground Truth.
