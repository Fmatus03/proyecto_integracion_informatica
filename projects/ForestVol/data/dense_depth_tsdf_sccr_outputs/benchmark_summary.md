# SCCR Validation Benchmark
Run ID: `SCCR-VALIDATION-01`

## Environment
- Docker Desktop: operational
- Backend runtime: Python 3.11.15, scipy 1.17.1, open3d 0.19.0, numpy 2.4.6
- SCCR total elapsed time: 56 s
- Approx memory observation after run: 997.4MiB / 7.616GiB
- Stage timing: not available without modifying the prototype.
- Set 2 environment note: historical UUID `002ca5e3-6eca-4aba-b3e2-623f97878136` was absent; path restored from existing task `37fe01cd-356f-4776-952a-17e989f8452b` using the same Set 2 images, no rerun.

## Comparison Table
| Dataset | Method | Components | Boundary | Non-manifold E | Non-manifold V | Watertight | Orientable | Known Ratio | BBox Drift | Area Drift % | Chamfer | Hausdorff | Volume |
|---|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---:|
| set1 | Baseline original / Poisson | 10 | 191 | 4 | 0 | False | False | None | None | None | None | None | None |
| set1 | TSDF / point SDF | 1 | 0 | 0 | 0 | True | True | None | 0.48026213 | -29.404725 | 3.852331 | 10.753586 | 95.756277 |
| set1 | Dense Depth TSDF | 56 | 80 | 0 | 0 | False | True | 0.025996 | 0.36286241 | -47.407438 | 5.164254 | 10.919192 | None |
| set1 | Dense Depth + Ray Carving | 44 | 72 | 0 | 4 | False | True | 0.0626 | 0.36078954 | -57.646345 | 5.327563 | 11.118629 | None |
| set1 | Dense Depth + Alignment | 37 | 18 | 0 | 0 | False | True | 0.014004 | 0.46487168 | -70.659436 | 4.478468 | 10.819039 | None |
| set1 | Dense Depth + Alignment + SCCR | 32 | 0 | 0 | 0 | True | True | 0.014591 | 0.49423951 | -69.299877 | 4.389832 | 10.623811 | 7.077038 |
| set1 | Dense Depth + Alignment + SCCR + Ray | 36 | 0 | 1 | 6 | False | False | 0.049937 | 0.49431681 | -78.98736 | 4.492918 | 10.74683 | None |
| set2 | Baseline original / Poisson | 39 | 226 | 39 | 0 | False | False | None | None | None | None | None | None |
| set2 | TSDF / point SDF | 1 | 0 | 0 | 0 | True | True | None | 0.03400707 | 50.863806 | 1.195443 | 1.273551 | 133.573573 |
| set2 | Dense Depth TSDF | 40 | 6 | 0 | 0 | False | True | 0.024186 | 0.06806145 | -53.02338 | 1.865074 | 6.248324 | None |
| set2 | Dense Depth + Ray Carving | 28 | 6 | 1 | 4 | False | False | 0.074302 | 0.08667682 | -67.286213 | 2.252851 | 6.181703 | None |
| set2 | Dense Depth + Alignment | 63 | 12 | 0 | 0 | False | True | 0.043103 | 0.13725012 | -20.845712 | 1.861858 | 3.290061 | None |
| set2 | Dense Depth + Alignment + SCCR | 28 | 0 | 0 | 0 | True | True | 0.01081 | 0.22747311 | -77.619474 | 1.746864 | 4.539742 | 1.620532 |
| set2 | Dense Depth + Alignment + SCCR + Ray | 20 | 0 | 1 | 2 | False | False | 0.061166 | 0.28040677 | -91.026083 | 2.439513 | 4.561994 | None |

## SCCR vs Alignment
- set1: components delta -5, boundary delta -18, non-manifold edge delta 0, known ratio delta 0.000587, Chamfer delta -0.088636, Hausdorff delta -0.195228, watertight [False, True].
  SCCR camera report: {'input_frame_count': 7, 'accepted_frame_count': 7, 'rejected_frame_count': 0, 'iterations': 2, 'translation_step_m': 0.08, 'rotation_step_deg': 0.35, 'surface_sample_count': 85, 'mean_camera_score_before': 0.677278, 'mean_camera_score_after': 0.682209, 'median_depth_alignment_error_before_m': 0.371768, 'median_depth_alignment_error_after_m': 0.36939, 'pose_update_count': 6}
- set2: components delta -35, boundary delta -12, non-manifold edge delta 0, known ratio delta -0.032293, Chamfer delta -0.114994, Hausdorff delta 1.249681, watertight [False, True].
  SCCR camera report: {'input_frame_count': 12, 'accepted_frame_count': 12, 'rejected_frame_count': 0, 'iterations': 2, 'translation_step_m': 0.08, 'rotation_step_deg': 0.35, 'surface_sample_count': 50, 'mean_camera_score_before': 0.601486, 'mean_camera_score_after': 0.635381, 'median_depth_alignment_error_before_m': 0.476134, 'median_depth_alignment_error_after_m': 0.462423, 'pose_update_count': 15}

## Decision
Option B: SCCR aporta mejoras topologicas claras, pero la evidencia geometrica/volumetrica es mixta; debe permanecer como experimento.

## Metric Notes
- Volumetric error: not calculated because no ground-truth volume was present in benchmark JSONs.
- Volume: null for non-watertight meshes.
- Hausdorff: existing `hausdorff_approx` metric.
- Graphs: not generated; no existing graph infrastructure was present for this benchmark.

## Decision Rationale
- Positive: Set 1 boundary 18 -> 0, Set 2 boundary 12 -> 0, both SCCR meshes become watertight before ray carving, components decrease in both sets, and Chamfer improves in both sets.
- Negative: Set 2 known voxel ratio drops 0.043103 -> 0.01081, Set 2 Hausdorff worsens 3.290061 -> 4.539742, bbox drift worsens in both sets, area drift remains large, and Set 2 volume is not stable.
