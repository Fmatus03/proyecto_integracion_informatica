# DBSCAN Cluster Selection Report

## set1

- Segmentation voxelization: `398562` -> `31465` points; removed ratio `0.921054`.
- DBSCAN input after voxelization: `31465` points.
- Clusters found: `60`; noise points: `1008`.
- Pipeline selected clusters: `[14, 0]` by `plausible_woodpile_components`.
- Selected ratio vs after-outlier cloud: `0.03964`.

| Rank | Cluster | Selected | Points | Ratio | BBox volume | Density | Discard reasons |
|---:|---:|---|---:|---:|---:|---:|---|
| 1 | 14 | True | 12247 | 0.389226 | 134.283931 | 91.202275 | - |
| 2 | 1 | False | 7156 | 0.227427 | 20.488038 | 349.276975 | axis_ratio_exceeds_max_component_axis_ratio, not_plausible_woodpile |
| 3 | 0 | True | 3552 | 0.112887 | 8.450375 | 420.336368 | - |
| 4 | 2 | False | 2402 | 0.076339 | 132.242558 | 18.163593 | not_in_top_max_components_after_ranking |
| 5 | 7 | False | 533 | 0.016939 | 3.037861 | 175.452396 | below_min_component_ratio |
| 6 | 41 | False | 450 | 0.014302 | 4.832154 | 93.126164 | below_min_component_ratio |
| 7 | 31 | False | 417 | 0.013253 | 5.133218 | 81.235588 | below_min_component_ratio |
| 8 | 10 | False | 407 | 0.012935 | 1.814134 | 224.349444 | below_min_component_ratio |
| 9 | 20 | False | 373 | 0.011854 | 1.556076 | 239.70557 | below_min_component_ratio |
| 10 | 13 | False | 321 | 0.010202 | 1.131954 | 283.580537 | below_min_component_ratio |
| 11 | 8 | False | 261 | 0.008295 | 1.366273 | 191.030682 | below_min_component_ratio |
| 12 | 34 | False | 220 | 0.006992 | 0.387786 | 567.322903 | below_min_component_ratio |

## set2

- Segmentation voxelization: `364166` -> `4200` points; removed ratio `0.988467`.
- DBSCAN input after voxelization: `4200` points.
- Clusters found: `11`; noise points: `342`.
- Pipeline selected clusters: `[4, 8]` by `plausible_woodpile_components`.
- Selected ratio vs after-outlier cloud: `0.009001`.

| Rank | Cluster | Selected | Points | Ratio | BBox volume | Density | Discard reasons |
|---:|---:|---|---:|---:|---:|---:|---|
| 1 | 4 | True | 2609 | 0.62119 | 44.739571 | 58.315266 | - |
| 2 | 8 | True | 669 | 0.159286 | 3.234557 | 206.828934 | - |
| 3 | 7 | False | 276 | 0.065714 | 0.408722 | 675.275848 | axis_ratio_exceeds_max_component_axis_ratio, not_plausible_woodpile |
| 4 | 2 | False | 61 | 0.014524 | 0.097553 | 625.299113 | below_min_component_ratio |
| 5 | 6 | False | 55 | 0.013095 | 0.00769 | 7152.100176 | below_min_component_ratio, axis_ratio_exceeds_max_component_axis_ratio, not_plausible_woodpile |
| 6 | 1 | False | 50 | 0.011905 | 0.020708 | 2414.529401 | below_min_component_ratio, axis_ratio_exceeds_max_component_axis_ratio, not_plausible_woodpile |
| 7 | 10 | False | 38 | 0.009048 | 0.002992 | 12701.378628 | below_min_component_ratio, axis_ratio_exceeds_max_component_axis_ratio, not_plausible_woodpile |
| 8 | 0 | False | 31 | 0.007381 | 0.002679 | 11572.449659 | below_min_component_ratio, axis_ratio_exceeds_max_component_axis_ratio, not_plausible_woodpile |
| 9 | 3 | False | 31 | 0.007381 | 0.030763 | 1007.717568 | below_min_component_ratio |
| 10 | 9 | False | 21 | 0.005 | 0.001472 | 14270.654311 | below_min_component_ratio, axis_ratio_exceeds_max_component_axis_ratio, not_plausible_woodpile |
| 11 | 5 | False | 17 | 0.004048 | 0.025215 | 674.213053 | below_min_component_ratio, not_plausible_woodpile |

