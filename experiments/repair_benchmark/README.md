# RUN-SET1-BASELINE-01 Repair Benchmark

This directory is an isolated experiment. It does not modify the ForestVol pipeline,
services, calibration, GCP, segmentation, reconstruction, or mesh parameters.

## Baseline Status

Set 1 was not relaunched from this harness. A prior `RUN-SET1-BASELINE-01`
baseline already exists and records session `a3c36266-f866-402f-8bc8-1c2b59b4a4ce`
as completed. Relaunching would violate the one-run constraint.

Primary baseline evidence:

- `.harness/runs/RUN-SET1-BASELINE-01/e2e-set1-baseline-result.json`
- `.harness/runs/RUN-SET1-BASELINE-01/set1-vs-set2-comparison-raw.json`
- `projects/ForestVol/data/processed/a3c36266-f866-402f-8bc8-1c2b59b4a4ce/surface_closure_diagnostics/surface_closure_diagnostics.json`
- `specs/forestvol-mvp/set1-baseline-and-mesh-repair-evaluation.md`

## Benchmark Execution

The benchmark was executed inside the existing `forestvol-backend` container with:

```sh
BENCHMARK_ROOT=/app BENCHMARK_OUT=/app/data/repair_benchmark_outputs python /tmp/repair_benchmark.py
```

The generated outputs were copied back to:

- `experiments/repair_benchmark/outputs/`
- `projects/ForestVol/data/repair_benchmark_outputs/`

## Engine Availability

Only Open3D was available in the backend runtime. Requested external engines were
recorded as unavailable rather than simulated:

- CGAL Polygon Mesh Processing: unavailable, `cgal_pmp_repair` not found on PATH
- MeshFix: unavailable, `meshfix` not found on PATH
- PyMeshLab: unavailable, Python module not installed
- VTK: unavailable, Python module not installed
- trimesh.repair extendido: unavailable, Python module not installed

An Open3D cleanup control was executed only as a local control, not as a replacement
candidate.

## Metric Summary

Set 1 Poisson frozen baseline:

- boundary edges: 191
- non-manifold edges: 4
- orientable: false
- watertight: false
- connected components: 10

Set 1 Open3D cleanup control:

- boundary edges: 203
- non-manifold edges: 0
- orientable: true
- watertight: false
- bbox drift: 0.0
- area drift: -0.002283%
- Hausdorff approx: 0.622237
- Chamfer approx: 0.295963

Set 2 Poisson frozen baseline:

- boundary edges: 226
- non-manifold edges: 39
- orientable: false
- watertight: false
- connected components: 39

Set 2 Open3D cleanup control:

- boundary edges: 318
- non-manifold edges: 0
- non-manifold vertices: 26
- orientable: false
- watertight: false
- bbox drift: 0.0
- area drift: -0.009183%
- Hausdorff approx: 0.516047
- Chamfer approx: 0.227462

## Decision

The baseline evidence supports `pipeline-inherent`, not `dataset-dependent`.

The benchmark could not rank CGAL, MeshFix, PyMeshLab, VTK, or trimesh by repair
quality because those engines are not installed in the current backend runtime.
The only executed control preserved bbox and area closely but did not produce a
watertight mesh for either dataset, so it is not sufficient as a repair strategy.
