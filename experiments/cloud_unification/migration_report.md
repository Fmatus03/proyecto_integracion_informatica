# Cloud Unification Migration Report

## What Changed

- Added `backend/app/services/cloud_provider.py`.
- Productive preliminary volumetry now resolves the cloud through `load_pipeline_point_cloud`.
- Active PDI/volume benchmarks now obtain Set 1 and Set 2 clouds from `CloudProvider`.
- Added `experiments/cloud_unification/benchmark_after_unification.py` with pre-benchmark source validation.

## What Did Not Change

- PDI formula unchanged.
- DBSCAN unchanged.
- OpenSfM unchanged.
- NodeODM unchanged.
- Reconstruction parameters unchanged.
- Calibration and GCP unchanged.

## Validation Rule

Before a benchmark runs, it validates:

- SHA256
- point count
- bounding box extent
- centroid
- canonical path

Any mismatch aborts the benchmark.

## Result

The benchmark after unification consumed exactly the productive `point_cloud.ply` for both datasets.

- Set 1 SHA256: `99c67aeed8feb3ab06bfe0f74c932af67aabbe5ebb0c8736b879c042846af777`
- Set 2 SHA256: `4ede2ae47fd561c67a1de73afcb3adcfc20297164b2084c911ff3785dda6d88b`

The new benchmark volumes match the productive validation:

- Set 1: `69.8281 m3`
- Set 2: `39.0156 m3`

This confirms the old benchmark discrepancy was caused by divergent cloud sources, not by PDI.
