# PDI MVP Readiness Benchmark

Run ID: `RUN-PDI-MVP-READINESS-01`

Ground Truth used only for final error calculation: `119.74 m3`

## Equivalence And Readiness

| Dataset | Volume m3 | Previous PDI m3 | Delta | Error % | Confidence | Gates PASS/WARN/FAIL | Time s |
|---|---:|---:|---:|---:|---|---|---:|
| set1 | 97.375 | 97.375 | 0.0 | 18.677969 | 95.0% HIGH | 11/1/0 | 0.269671 |
| set2 | 132.671875 | 132.671875 | 0.0 | 10.799962 | 100.0% HIGH | 12/0/0 | 0.200771 |

## Diagnostics

### set1

- Point count: `19879`
- Quality metrics: `{"point_count": 19879, "mean_density_points_per_m3": 29.028473, "bbox_min": [1.28758, -10.007647, -4.472788], "bbox_max": [10.271735, 4.973067, 0.61537], "bbox_extent_m": [8.984155, 14.980714, 5.088158], "bbox_volume_m3": 684.810396, "bbox_aspect_ratio": 2.944231, "bbox_axis_order": ["x", "y", "z"], "median_nn_m": 0.041225, "mean_nn_m": 0.042182, "local_density_cv": 0.310786, "isolated_point_ratio": 0.000333, "outlier_ratio": 0.016667, "nn_outlier_limit_m": 0.071318, "coverage_grid_bins": 6, "spatial_coverage_ratio": 0.240741, "interior_hole_ratio": 0.734375, "lateral_coverage_ratio": 0.284722, "top_coverage_ratio": 0.111111, "bottom_coverage_ratio": 0.194444, "face_coverage_ratios": {"x_min": 0.166667, "x_max": 0.277778, "y_min": 0.222222, "y_max": 0.472222, "z_min": 0.194444, "z_max": 0.111111}, "voxel_components": 2, "dominant_component_voxel_ratio": 0.783065, "occupied_voxels": 1429}`
- Confidence diagnosis:
  - coverage.top: WARNING (Low top coverage can indicate missing upper surface observations.)

### set2

- Point count: `26113`
- Quality metrics: `{"point_count": 26113, "mean_density_points_per_m3": 67.239444, "bbox_min": [2.862918, -7.653658, -1.040662], "bbox_max": [9.662048, 1.445573, 5.236663], "bbox_extent_m": [6.79913, 9.099231, 6.277325], "bbox_volume_m3": 388.358359, "bbox_aspect_ratio": 1.449539, "bbox_axis_order": ["x", "y", "z"], "median_nn_m": 0.044955, "mean_nn_m": 0.0461, "local_density_cv": 0.283059, "isolated_point_ratio": 0.00025, "outlier_ratio": 0.05175, "nn_outlier_limit_m": 0.069738, "coverage_grid_bins": 6, "spatial_coverage_ratio": 0.361111, "interior_hole_ratio": 0.46875, "lateral_coverage_ratio": 0.243056, "top_coverage_ratio": 0.416667, "bottom_coverage_ratio": 0.305556, "face_coverage_ratios": {"x_min": 0.305556, "x_max": 0.25, "y_min": 0.055556, "y_max": 0.361111, "z_min": 0.305556, "z_max": 0.416667}, "voxel_components": 1, "dominant_component_voxel_ratio": 1.0, "occupied_voxels": 1627}`
- Confidence diagnosis:
  - No quality gate produced WARNING or FAIL.

## Decision

- Final decision: `SI`
- Basis: volumes_equivalent=True; total_fail_gates=0; mean_confidence=97.5%; decision threshold requires unchanged PDI volume, zero FAIL gates on current Set 1/Set 2, and mean confidence >= 60%.

## Traceability

- No production pipeline code was modified.
- PDI parameters were not changed.
- Quality gates and confidence score do not use Ground Truth.
- Ground Truth is used only in the final benchmark error columns.
