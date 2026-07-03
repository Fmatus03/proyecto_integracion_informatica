# CloudProvider Design

## Goal

Remove data-source divergence between production, benchmarks, and validations.

## Public API

`load_pipeline_point_cloud(session_id, settings)`

This is the only public function exported by `backend/app/services/cloud_provider.py`.

## Contract

Given a `session_id`, the provider resolves exactly:

`settings.processed_path / session_id / "point_cloud.ply"`

It rejects non-canonical session paths and raises a clear error if the cloud is missing or empty.

## Fingerprint

The returned internal object provides:

- `path`
- `sha256`
- `size_bytes`
- `point_count`
- `bbox_min`
- `bbox_max`
- `bbox_extent`
- `centroid`

Benchmarks must record this fingerprint before executing. If the fingerprint changes or does not match production, the benchmark aborts.

## Non-goals

- No PDI formula change.
- No DBSCAN change.
- No NodeODM/OpenSfM parameter change.
- No reconstruction rerun.
- No mesh repair or new estimator.
