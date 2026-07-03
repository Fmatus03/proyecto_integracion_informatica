# ForestVol Segmentation Pipeline Full Experiment

All work stayed under `experiments/`; production, NodeODM, OpenSfM, PDI and CloudProvider were not modified.

Ground truth used for both sets: `119.74` m3.

## Baseline audit

### set1

| Stage | Points | Loss % | BBox m3 | Density | PDI volume | Abs error | % error |
|---|---:|---:|---:|---:|---:|---:|---:|
| RAW | 401873 | None | 34178.953655 | 11.757908 | None | None | None |
| Outlier Removal | 398562 | 0.8239 | 24096.383622 | 16.540324 | None | None | None |
| Voxel Down Sample + DBSCAN | 31465 | 92.1054 | 24063.057681 | 1.307606 | None | None | None |
| Ranking + Cluster Selection | 19403 | 38.3347 | 753.771215 | 25.741232 | None | None | None |
| PDI | 15799 | 18.5744 | 438.24735 | 36.050418 | 69.8281 | 49.9119 | 41.683564 |

### set2

| Stage | Points | Loss % | BBox m3 | Density | PDI volume | Abs error | % error |
|---|---:|---:|---:|---:|---:|---:|---:|
| RAW | 371766 | None | 1266.406363 | 293.559801 | None | None | None |
| Outlier Removal | 364166 | 2.0443 | 1187.996792 | 306.537865 | None | None | None |
| Voxel Down Sample + DBSCAN | 4200 | 98.8467 | 1181.264317 | 3.555512 | None | None | None |
| Ranking + Cluster Selection | 3278 | 21.9524 | 538.042284 | 6.092458 | None | None | None |
| PDI | 3278 | 0.0 | 538.042284 | 6.092458 | 39.0156 | 80.7244 | 67.416402 |

## Objective selection

| Dataset | Best voxel | Best DBSCAN eps | Best DBSCAN min_points | Best strategy | Volume | Abs error | % error | Clusters | Points |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| set1 | 0.07 | 0.5 | 10 | top_k_by_points | 119.1875 | 0.5525 | 0.461416 | 3 | 19958 |
| set2 | 0.02 | 0.5 | 10 | top_k_by_pdi_volume | 48.3125 | 71.4275 | 59.652163 | 3 | 16832 |

## Decision

The ranking criterion is absolute error vs ground truth, then percent error, stability between sets, fragmentation and compute cost. Volume alone is reported only as an explanatory measurement.

## Before vs experimental candidate

| Dataset | Baseline volume | Baseline abs error | Baseline % error | Candidate volume | Candidate abs error | Candidate % error | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| set1 | 69.8281 | 49.9119 | 41.683564 | 119.1875 | 0.5525 | 0.461416 | Strong experimental improvement |
| set2 | 39.0156 | 80.7244 | 67.416402 | 48.3125 | 71.4275 | 59.652163 | Improvement is not sufficient |

No production change is applied by this experiment. A production change remains blocked because the improvement is not clear and consistent in both datasets, and because a fresh end-to-end image-to-volume run has not been executed for the candidate pipeline.

## Generated artifacts

- `audit_pipeline_stages.json`
- `voxel_sensitivity.json` / `voxel_sensitivity.csv`
- `dbscan_sensitivity.json` / `dbscan_sensitivity.csv`
- `cluster_strategy_comparison.json` / `cluster_strategy_comparison.csv`
- `final_selection.json`
- `voxel_sensitivity_error.png`
