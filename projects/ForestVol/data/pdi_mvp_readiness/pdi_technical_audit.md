# Point Density Integration Technical Audit

## Scope

This document audits the current Point Density Integration estimator as an isolated experimental component. It does not define a production-pipeline change.

## Geometric Assumptions

- Input is a segmented object point cloud in metric coordinates.
- The segmented cloud has broad spatial support around the object.
- Background contamination is low; off-object points are not part of the intended support.
- The estimator can use voxelized density support as an auxiliary solid for volume, without requiring a watertight mesh.

## Parameters

- `voxel_size_m`: `0.25`.
- Density threshold: `max(1, ceil(hull_density_points_per_m3 * voxel_size_m^3 * 0.35))`.
- Solidification: binary dilation with 3D connectivity-2 for 2 iterations, hole fill, binary closing for 1 iteration, second hole fill, then dominant connected component.
- No Ground Truth is used to set any parameter.

## Implementation Stages

- Input: finite Nx3 point cloud loaded from PLY.
- Preprocessing: finite-point filter only.
- Estimation: ConvexHull density, voxel point counts, dense-voxel selection, solid occupancy, volume by solid voxel count.
- Postprocessing: dominant connected component in the solid occupancy grid.
- Metrics: volume, threshold, hull density, solid voxels, quality gates, confidence score and benchmark error.

## Dependencies

- Open3D for PLY point-cloud loading.
- NumPy for array operations.
- SciPy ConvexHull, cKDTree and ndimage.
- Matplotlib only for benchmark plots.

## Complexity

- Convex hull: approximately O(n log n) in typical 3D cases, with higher worst-case behavior depending on hull structure.
- Voxel indexing/counting: O(n).
- Morphological operations: O(V), where V is the voxel-grid cell count.
- Quality gates: nearest-neighbor diagnostics use O(n log n) on a capped sample; coverage and component metrics are O(n + V).
- Memory: O(n + V). Runtime memory is dominated by boolean/int voxel grids.

## Known Limitations

- Spurious background points can expand the convex hull and voxel support, causing severe overestimation.
- Structured occlusion can remove full faces or bands and cause underestimation.
- The result is quantized by voxel size.
- The method does not produce a high-fidelity mesh; the mesh is not the product.
- Quality gates are diagnostic only and do not repair the cloud or alter the volume.

## Observed Strengths

- Lowest mean volumetric error among evaluated estimators in the previous benchmark.
- Fast execution on Set 1 and Set 2.
- Robust to moderate random point removal in the previous robustness benchmark.
- Does not depend on Poisson watertightness or mesh repair.
