# Castillo Geometric Audit

Source cloud: `projects\ForestVol\data\processed\971d6e25-8ff0-41d2-8784-c981dec7ccbf\point_cloud.ply`

Scale factor used for measurement: `0.54611448 m/unit`

No reconstruction, PDI, DBSCAN pipeline stage, or algorithm parameter was modified. This audit operates only on the existing point cloud.

## Detection Method

The trunk detector does not assume 4 layers, 8 trunks per layer, or 32 trunks. It first estimates the dominant horizontal log direction using PCA, projects the cloud into the transverse Y/Z section, finds local density peaks in that section, and assigns points to the nearest accepted peak. The expected 8x4 model is used only after detection, as a comparison target.

Detector parameters recorded in `trunk_measurements.json`:

- Forced expected structure: `false`
- Raw density peaks: `10`
- Accepted trunk candidates: `9`
- Inferred layer count from detected centers: `3`
- Density bin size: `0.12 m`
- Minimum peak distance: `0.45 m`
- Maximum point-to-peak assignment distance: `0.85 m`

## Expected Physical Geometry

| Metric | Expected |
|---|---:|
| Trunks | 32 |
| Layers | 4 |
| Trunks per layer | 8 |
| Log length | 6.00 m |
| Log diameter | 1.26 m |
| Total width | 10.08 m |
| Total height | 5.04 m |

## Detected Geometry

| Metric | Measured |
|---|---:|
| Detected trunk candidates | 9 |
| Missing vs 32 expected | 23 |
| Mean trunk length | 5.5338 m |
| Trunk length std | 0.9614 m |
| Mean diameter p90 | 1.1784 m |
| Diameter p90 std | 0.1279 m |
| Mean center-center distance | 1.4328 m |
| Center-center std | 0.4477 m |

## Global Deformation

Robust AABB extents from selected castle points:

| Axis | Expected | Measured | Error |
|---|---:|---:|---:|
| X length | 6.0000 m | 7.5720 m | 26.20% |
| Y width | 10.0800 m | 6.7845 m | -32.69% |
| Z height | 5.0400 m | 3.5059 m | -30.44% |

Axis scale ratios vs expected:

- X: 1.2620
- Y: 0.6731
- Z: 0.6956

This is anisotropic: X is expanded while Y and Z are compressed.

## Layer Summary

| Layer | Z center | Trunks | Avg length | Avg diameter p90 |
|---:|---:|---:|---:|---:|
| 0 | 0.2762 | 2 | 5.7391 | 1.1273 |
| 1 | 1.5557 | 5 | 5.3439 | 1.1407 |
| 2 | 2.4737 | 2 | 5.8029 | 1.3239 |

## Objective Conclusion

1. Geometry vs 8x4 castle: the independent geometric detector found 9 separable trunk-like candidates, not 32. Compared after the fact with the expected 8x4 model, this leaves 23 expected trunks not separable as independent geometric candidates.
2. Log length: mean detected length is 5.5338 m vs 6.0000 m expected, error -7.77%.
3. Diameter: mean p90 diameter is 1.1784 m vs 1.2600 m expected, error -6.48%.
4. Systematic deformation: robust global dimensions show X error 26.20%, Y error -32.69%, Z error -30.44%. This is not compatible with a uniform global scale error.
5. The remaining volume discrepancy is therefore supported by geometric deformation evidence: anisotropic expansion/compression and reconstructed trunk cross-sections that do not match the expected 6.0 m by 1.26 m logs.
