# Castillo Dimension Validation

Session: `971d6e25-8ff0-41d2-8784-c981dec7ccbf`

Source cloud: `projects\ForestVol\data\processed\971d6e25-8ff0-41d2-8784-c981dec7ccbf\point_cloud.ply`

Scale factor applied for measurement: `0.54611448 m/unit`

## Reported Dimensions

Dimensions are reported from the AABB of the automatically selected dense main castle component, trimmed at 1%-99% per axis.

| Measurement | Value |
|---|---:|
| Length X | 8.3627 m |
| Width Y | 7.2424 m |
| Height Z including upper extension | 3.7315 m |
| Height Z excluding sparse upper extension | 3.7071 m |

## Bounding Boxes

| Box | X/major | Y/minor | Z |
|---|---:|---:|---:|
| AABB | 8.3627 m | 7.2424 m | 3.7315 m |
| OBB | 9.2653 m | 8.2239 m | 3.7315 m |

AABB is used for final reporting because the requested dimensions are explicitly X, Y and Z extents. OBB is included as an orientation check.

## Vertical Evidence

| Metric | Value |
|---|---:|
| Z min | -0.5049 m |
| Z max | 3.2266 m |
| Z p95 | 3.1047 m |
| Z p99 | 3.2022 m |
| Top 0.75m points | 103324 |
| Previous 0.75m points | 192783 |
| Top/previous ratio | 0.535960 |

Upper extension classification: `no_sparse_upper_extension_detected`.

## Conclusion

1. Final dimensions: X=8.3627 m, Y=7.2424 m, Z=3.7315 m including upper extension.
2. This report does not have an external measured ground-truth dimension table; it can only compare internal AABB/OBB consistency.
3. Fifth level / upper extension: `no_sparse_upper_extension_detected` based on top-vs-previous vertical point distribution.
4. Since the model dimensions remain large while the ArUco scale was applied, the remaining volume error is more consistent with geometry/segmentation/PDI support than with a missing global scale application. Exact ground-truth dimensions are required to conclude whether the ArUco factor itself is numerically correct.
