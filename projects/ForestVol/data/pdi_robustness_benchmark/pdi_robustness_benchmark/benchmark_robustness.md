# PDI Robustness Benchmark

Ground Truth: `119.74 m3`

Base method: `Point Density Integration`, voxel size `0.25 m`, unchanged from previous benchmark.

## Summary Table

| Dataset | Experiment | Level | Volume | % Error | Points | Density | Delta vs Base % |
|---|---|---|---:|---:|---:|---:|---:|
| set1 | base | original | 97.375 | 18.677969 | 19879 | 29.028473 | 0.0 |
| set1 | random_point_reduction | remove_5pct | 97.328125 | 18.717116 | 18885 | 27.576976 | -0.048139 |
| set1 | random_point_reduction | remove_10pct | 97.28125 | 18.756264 | 17891 | 26.12548 | -0.096277 |
| set1 | random_point_reduction | remove_20pct | 96.859375 | 19.108589 | 15903 | 23.238949 | -0.529525 |
| set1 | random_point_reduction | remove_30pct | 96.4375 | 19.460915 | 13915 | 20.333898 | -0.962773 |
| set1 | random_point_reduction | remove_40pct | 95.9375 | 19.878487 | 11927 | 17.489591 | -1.476252 |
| set1 | random_point_reduction | remove_50pct | 95.296875 | 20.4135 | 9940 | 14.588172 | -2.134146 |
| set1 | gaussian_noise | sigma_1cm | 97.609375 | 18.482232 | 19879 | 28.994513 | 0.240693 |
| set1 | gaussian_noise | sigma_2cm | 99.09375 | 17.242567 | 19879 | 28.858375 | 1.765083 |
| set1 | gaussian_noise | sigma_5cm | 106.234375 | 11.279126 | 19879 | 27.668575 | 9.098203 |
| set1 | gaussian_noise | sigma_10cm | 119.84375 | 0.086646 | 19879 | 25.775024 | 23.074454 |
| set1 | partial_occlusion | remove_x_min_face_20pct | 73.515625 | 38.603954 | 15903 | 37.377784 | -24.502567 |
| set1 | partial_occlusion | remove_high_corner_20pct_xyz | 97.375 | 18.677969 | 19879 | 29.028473 | 0.0 |
| set1 | partial_occlusion | remove_vertical_band_mid_x | 87.265625 | 27.120741 | 13916 | 20.353393 | -10.3819 |
| set1 | partial_occlusion | remove_horizontal_band_mid_z | 85.8125 | 28.334308 | 13916 | 21.109656 | -11.874198 |
| set1 | partial_occlusion | remove_y_max_face_20pct | 77.5625 | 35.224236 | 15903 | 31.093507 | -20.346598 |
| set1 | partial_occlusion | remove_low_corner_20pct_xyz | 97.375 | 18.677969 | 19847 | 28.981745 | 0.0 |
| set1 | segmentation_spurious_points | add_2pct | 645.421875 | 439.019438 | 20277 | 13.723368 | 562.820924 |
| set1 | segmentation_spurious_points | add_5pct | 1185.40625 | 889.983506 | 20873 | 13.887761 | 1117.362003 |
| set1 | segmentation_spurious_points | add_10pct | 1588.484375 | 1226.611304 | 21867 | 14.55506 | 1531.306162 |
| set1 | segmentation_missing_object_points | remove_2pct | 97.265625 | 18.769313 | 19481 | 28.44729 | -0.112323 |
| set1 | segmentation_missing_object_points | remove_5pct | 97.578125 | 18.508331 | 18885 | 27.600112 | 0.208601 |
| set1 | segmentation_missing_object_points | remove_10pct | 97.265625 | 18.769313 | 17891 | 26.12548 | -0.112323 |
| set2 | base | original | 132.671875 | 10.799962 | 26113 | 67.239444 | 0.0 |
| set2 | random_point_reduction | remove_5pct | 132.53125 | 10.68252 | 24807 | 63.87657 | -0.105995 |
| set2 | random_point_reduction | remove_10pct | 132.03125 | 10.264949 | 23502 | 60.516272 | -0.482864 |
| set2 | random_point_reduction | remove_20pct | 131.546875 | 9.860427 | 20890 | 53.81851 | -0.847957 |
| set2 | random_point_reduction | remove_30pct | 130.5625 | 9.038333 | 18279 | 47.219625 | -1.589919 |
| set2 | random_point_reduction | remove_40pct | 129.625 | 8.255387 | 15668 | 40.474094 | -2.296549 |
| set2 | random_point_reduction | remove_50pct | 134.21875 | 12.091824 | 13056 | 33.784467 | 1.16594 |
| set2 | gaussian_noise | sigma_1cm | 132.890625 | 10.98265 | 26113 | 66.909576 | 0.16488 |
| set2 | gaussian_noise | sigma_2cm | 133.78125 | 11.726449 | 26113 | 66.264882 | 0.836179 |
| set2 | gaussian_noise | sigma_5cm | 138.28125 | 15.484592 | 26113 | 65.050795 | 4.228006 |
| set2 | gaussian_noise | sigma_10cm | 149.84375 | 25.14093 | 26113 | 58.995846 | 12.943116 |
| set2 | partial_occlusion | remove_x_min_face_20pct | 104.765625 | 12.505742 | 20890 | 81.374345 | -21.034036 |
| set2 | partial_occlusion | remove_high_corner_20pct_xyz | 130.3125 | 8.829547 | 25452 | 66.067843 | -1.778354 |
| set2 | partial_occlusion | remove_vertical_band_mid_x | 116.59375 | 2.627568 | 18280 | 47.069928 | -12.118714 |
| set2 | partial_occlusion | remove_horizontal_band_mid_z | 117.5625 | 1.818523 | 18280 | 47.069928 | -11.388529 |
| set2 | partial_occlusion | remove_y_max_face_20pct | 110.875 | 7.403541 | 20890 | 72.891287 | -16.42916 |
| set2 | partial_occlusion | remove_low_corner_20pct_xyz | 129.28125 | 7.968306 | 25371 | 66.529366 | -2.555647 |
| set2 | segmentation_spurious_points | add_2pct | 662.15625 | 452.995031 | 26635 | 31.670834 | 399.093157 |
| set2 | segmentation_spurious_points | add_5pct | 944.5625 | 688.84458 | 27419 | 32.205102 | 611.953833 |
| set2 | segmentation_spurious_points | add_10pct | 1042.40625 | 770.558084 | 28724 | 33.789434 | 685.702509 |
| set2 | segmentation_missing_object_points | remove_2pct | 132.484375 | 10.643373 | 25591 | 65.895324 | -0.141326 |
| set2 | segmentation_missing_object_points | remove_5pct | 132.34375 | 10.525931 | 24807 | 63.87657 | -0.247321 |
| set2 | segmentation_missing_object_points | remove_10pct | 132.0625 | 10.291047 | 23502 | 60.516272 | -0.45931 |

## Aggregate Metrics

```json
{
  "set1:random_point_reduction": {
    "count": 6,
    "mean_percent_error": 19.389145,
    "median_percent_error": 19.284752,
    "std_percent_error": 0.667051,
    "coefficient_of_variation_volume": 0.008275,
    "worst_percent_error": 20.4135,
    "best_percent_error": 18.717116,
    "ci95_percent_error": 0.533752
  },
  "set1:gaussian_noise": {
    "count": 4,
    "mean_percent_error": 11.772643,
    "median_percent_error": 14.260846,
    "std_percent_error": 8.401284,
    "coefficient_of_variation_volume": 0.096087,
    "worst_percent_error": 18.482232,
    "best_percent_error": 0.086646,
    "ci95_percent_error": 8.233259
  },
  "set1:partial_occlusion": {
    "count": 6,
    "mean_percent_error": 27.773196,
    "median_percent_error": 27.727525,
    "std_percent_error": 8.234199,
    "coefficient_of_variation_volume": 0.114005,
    "worst_percent_error": 38.603954,
    "best_percent_error": 18.677969,
    "ci95_percent_error": 6.588731
  },
  "set1:segmentation_spurious_points": {
    "count": 3,
    "mean_percent_error": 851.871416,
    "median_percent_error": 889.983506,
    "std_percent_error": 395.176714,
    "coefficient_of_variation_volume": 0.415158,
    "worst_percent_error": 1226.611304,
    "best_percent_error": 439.019438,
    "ci95_percent_error": 447.184549
  },
  "set1:segmentation_missing_object_points": {
    "count": 3,
    "mean_percent_error": 18.682319,
    "median_percent_error": 18.769313,
    "std_percent_error": 0.150678,
    "coefficient_of_variation_volume": 0.001853,
    "worst_percent_error": 18.769313,
    "best_percent_error": 18.508331,
    "ci95_percent_error": 0.170508
  },
  "set2:random_point_reduction": {
    "count": 6,
    "mean_percent_error": 10.03224,
    "median_percent_error": 10.062688,
    "std_percent_error": 1.333678,
    "coefficient_of_variation_volume": 0.012121,
    "worst_percent_error": 12.091824,
    "best_percent_error": 8.255387,
    "ci95_percent_error": 1.067164
  },
  "set2:gaussian_noise": {
    "count": 4,
    "mean_percent_error": 15.833655,
    "median_percent_error": 13.605521,
    "std_percent_error": 6.510213,
    "coefficient_of_variation_volume": 0.056203,
    "worst_percent_error": 25.14093,
    "best_percent_error": 10.98265,
    "ci95_percent_error": 6.380008
  },
  "set2:partial_occlusion": {
    "count": 6,
    "mean_percent_error": 6.858871,
    "median_percent_error": 7.685923,
    "std_percent_error": 4.015153,
    "coefficient_of_variation_volume": 0.085138,
    "worst_percent_error": 12.505742,
    "best_percent_error": 1.818523,
    "ci95_percent_error": 3.212791
  },
  "set2:segmentation_spurious_points": {
    "count": 3,
    "mean_percent_error": 637.465898,
    "median_percent_error": 688.84458,
    "std_percent_error": 164.89815,
    "coefficient_of_variation_volume": 0.223601,
    "worst_percent_error": 770.558084,
    "best_percent_error": 452.995031,
    "ci95_percent_error": 186.599823
  },
  "set2:segmentation_missing_object_points": {
    "count": 3,
    "mean_percent_error": 10.486784,
    "median_percent_error": 10.525931,
    "std_percent_error": 0.179396,
    "coefficient_of_variation_volume": 0.001624,
    "worst_percent_error": 10.643373,
    "best_percent_error": 10.291047,
    "ci95_percent_error": 0.203005
  }
}
```

## Analysis

- most_damaging_degradation: {'experiment': 'segmentation_spurious_points', 'mean_percent_error': 744.668657}
- worst_case: {'dataset': 'set1', 'experiment': 'segmentation_spurious_points', 'level': 'add_10pct', 'percent_error': 1226.611304}
- best_case: {'dataset': 'set1', 'experiment': 'gaussian_noise', 'level': 'sigma_10cm', 'percent_error': 0.086646}
- abrupt_error_thresholds: []
- dataset_variability: {'set1_volume_m3': 97.375, 'set2_volume_m3': 132.671875, 'absolute_volume_difference_m3': 35.296875, 'relative_volume_difference_pct_of_gt': 29.477931, 'mean_percent_error': 14.738966, 'coefficient_of_variation_volume': 0.216988}
- robustness_assessment: PDI is robust to moderate random point removal and small Gaussian noise, but sensitive to structured occlusion and segmentation outliers that expand the hull/density support.
- capture_scenarios_to_avoid: Avoid missing full faces/bands/corners and avoid background contamination; these degradations dominate error growth.

## Recommendation

PDI remains a viable MVP volumetric estimator only under capture conditions with broad object coverage and controlled segmentation. It should be integrated with documented operating limits and future quality gates for occlusion/background contamination, not treated as universally robust.
