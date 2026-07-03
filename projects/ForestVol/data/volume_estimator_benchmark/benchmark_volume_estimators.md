# Volume Estimator Benchmark

Ground Truth: `119.74 m3`

| Dataset | Method | Volume | Abs Error | % Error | Time s | Noise Std | Cross-set Delta | Components | Boundary | Watertight |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| set1 | Convex Hull | 156.927698 | 37.187698 | 31.057038 | 0.012216 | 1.199168 | 74.425726 | 1 | 0 | True |
| set1 | Alpha Shape | None | None | None | 0.976071 | None | None | 156 | 0 | False |
| set1 | Voxel Occupancy | 97.375 | 22.365 | 18.677969 | 0.027858 | 0.249413 | 38.296875 | None | None | None |
| set1 | Octree Occupancy | 840.421875 | 720.681875 | 601.872286 | 1.997745 | 1.425279 | 322.828125 | None | None | None |
| set1 | Surface Mesh (Poisson) | None | None | None | 0.424937 | None | None | 10 | 191 | False |
| set1 | TSDF Occupancy | 97.375 | 22.365 | 18.677969 | 0.033447 | 0.0 | 38.296875 | None | None | None |
| set1 | Point Density Integration | 97.375 | 22.365 | 18.677969 | 0.033571 | 0.249413 | 35.296875 | None | None | None |
| set2 | Convex Hull | 82.501972 | 37.238028 | 31.099072 | 0.007128 | 0.724453 | 74.425726 | 1 | 0 | True |
| set2 | Alpha Shape | None | None | None | 1.098167 | None | None | 319 | 0 | False |
| set2 | Voxel Occupancy | 135.671875 | 15.931875 | 13.305391 | 0.015632 | 0.305667 | 38.296875 | None | None | None |
| set2 | Octree Occupancy | 1163.25 | 1043.51 | 871.479873 | 3.429219 | 8.792729 | 322.828125 | None | None | None |
| set2 | Surface Mesh (Poisson) | None | None | None | 1.217743 | None | None | 39 | 226 | False |
| set2 | TSDF Occupancy | 135.671875 | 15.931875 | 13.305391 | 0.013817 | 0.0 | 38.296875 | None | None | None |
| set2 | Point Density Integration | 132.671875 | 12.931875 | 10.799962 | 0.026479 | 0.481341 | 35.296875 | None | None | None |

## Recommendation

- Best by mean percent error: `Point Density Integration`.
- Mean percent error: `14.738966`.
- Mean execution time: `0.030025 s`.
- Rationale: Selected strictly by lowest mean percent error across Set 1 and Set 2; runtime is secondary context.

## Notes

- Ground Truth was used only for final error calculation.
- No main pipeline code was modified.
- Memory is recorded as null because no profiler was added.
