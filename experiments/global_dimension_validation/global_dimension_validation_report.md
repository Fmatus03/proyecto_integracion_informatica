# Global Dimension Validation

Source cloud: `projects\ForestVol\data\processed\971d6e25-8ff0-41d2-8784-c981dec7ccbf\point_cloud.ply`

Scale factor used only to express existing cloud coordinates in meters: `0.54611448 m/unit`

No reconstruction, NodeODM, OpenSfM, DBSCAN, PDI, segmentation, or ArUco scaling code was modified or rerun.

## Castle Isolation

Selection method: raw cloud scaled to meters, remove outer 0.5% per axis, then keep central 98% per axis.

- Raw points: 746225
- Core points after 0.5% trim: 726523
- Castle-selection points used for plane fitting: 685025

## Plane-Based Dimensions

| Dimension | Planes | Value | Uncertainty | Points | Quality | Expected | Error |
|---|---|---:|---:|---:|---:|---:|---:|
| X length | front-back | 6.5981 m | 0.3230 m | 82204 | 0.8103 | 6.0000 m | 9.97% |
| Y width | left-right | 5.7721 m | 0.4737 m | 82204 | 0.7736 | 10.0800 m | -42.74% |
| Z height | bottom-top | 3.3086 m | 0.1092 m | 82204 | 0.9345 | 5.0400 m | -34.35% |

## Method Comparison

| Method | X | Y | Z |
|---|---:|---:|---:|
| AABB full selection | 8.2490 m | 7.1802 m | 3.6797 m |
| AABB robust 1%-99% | 7.5720 m | 6.7845 m | 3.5059 m |
| OBB PCA frame full | 9.0787 m | 8.2325 m | 3.6797 m |
| OBB PCA frame robust 1%-99% | 7.2219 m | 6.4321 m | 3.5059 m |
| Face planes | 6.5981 m | 5.7721 m | 3.3086 m |

## Face Fit Quality

| Face | Points | Axis position | RMS residual | p95 residual | Normal alignment |
|---|---:|---:|---:|---:|---:|
| left | 41102 | -1.9109 m | 0.1640 m | 0.3947 m | 0.9951 |
| right | 41102 | 3.8612 m | 0.4444 m | 0.7268 m | 1.0000 |
| front | 41102 | -3.2067 m | 0.2826 m | 0.5720 m | 0.9737 |
| back | 41102 | 3.3914 m | 0.1564 m | 0.2928 m | 0.9963 |
| bottom | 41102 | -1.7022 m | 0.1015 m | 0.2017 m | 0.9998 |
| top | 41102 | 1.6064 m | 0.0402 m | 0.0718 m | 0.9999 |

## Coherence With Local Trunk Measurements

- Detected separable trunk-like candidates: 9
- Mean local trunk length: 5.5338 m
- Mean local trunk diameter p90: 1.1784 m

The plane-based X length is 6.5981 m, which differs from the local mean trunk length by 1.0643 m.
The plane-based Y width divided by the local p90 diameter is 4.90 apparent diameters.
The plane-based Z height divided by the local p90 diameter is 2.81 apparent diameters.

## Quantitative Conclusion

1. Plane dimensions vs AABB: face planes produce X=6.5981 m, Y=5.7721 m, Z=3.3086 m. These are compared above against AABB and OBB; the plane method avoids using coordinate extrema as the primary measurement.
2. Compatibility with local trunks: the local trunk diameter is close to the expected diameter, but the plane-based width corresponds to only 4.90 measured diameters, below the 8-diameter physical expectation.
3. Evidence for real deformation: the plane distances still show non-uniform errors: X 9.97%, Y -42.74%, Z -34.35%.
4. Measurement-method explanation: because plane-based, OBB, and robust AABB measurements remain broadly consistent, the discrepancy cannot be explained solely by AABB extrema. The remaining contradiction is between locally plausible trunk diameters and globally missing/semi-fused separable structure.
