# Volumetric Reconstruction Architecture

## Decision Context

The Set 1 and Set 2 baseline establishes that the failure is pipeline-inherent.
Poisson produces open and non-manifold surfaces before repair, and downstream repair
cannot reliably recover a valid solid. The architectural change is therefore to stop
repairing broken meshes and instead generate a surface from a volumetric or implicit
solid representation.

## Option A: TSDF / Voxel Fusion

Pipeline:

`images -> OpenSfM/NodeODM cameras + depth/proxy geometry -> TSDF volume -> Marching Cubes -> volume`

Integration:

- Keep OpenSfM/NodeODM for camera poses, sparse/dense points, and scale bootstrap.
- Replace Poisson meshing in `mesh_service` with a new volumetric surface stage.
- If dense depth maps are available from ODM/MVS, integrate each depth image into a
  TSDF. If only point clouds are available, initialize a coarse occupancy/SDF proxy
  from scaled segmented points.

Existing point cloud:

- Use it as either TSDF observations or as a fallback occupancy prior.
- Segment before volumetric fusion to avoid integrating background.

Scale:

- Preserve the current calibration/GCP scale before volume construction.
- Define voxel length in meters, so extracted volume is directly in m3.

Watertight by construction:

- Marching Cubes over a closed signed field yields a closed isosurface when the field
  is defined over a bounded volume with an outside band.
- Boundary behavior is controlled at the volume boundary, not repaired afterward.

Avoiding non-manifold structure:

- Use a well-tested Marching Cubes implementation or dual contouring variant.
- Enforce one connected foreground component before extraction if the object contract
  is one solid object.

Impact:

- Moderate. Calibration, upload, reconstruction, scale, and segmentation can remain.
- Meshing and volumetric measurement become a new service boundary.

Risks:

- Needs depth maps or robust point-to-field conversion.
- Voxel resolution controls accuracy, memory, and runtime.
- Thin structures may vanish if voxel size is too coarse.

Complexity:

- Medium if depth maps are accessible.
- Medium/high if TSDF must be inferred from point-only observations.

## Option B: Global Implicit Reconstruction

Pipeline:

`scaled segmented point cloud -> oriented SDF/occupancy function -> isosurface extraction -> volume`

Integration:

- Keep NodeODM/OpenSfM for point generation and scale.
- Replace Poisson with implicit fitting. The SDF can be classical first, learned later.

Existing point cloud:

- Use points and estimated normals as zero-level constraints.
- Add free-space/outside samples from camera rays when camera poses are available.
- Add inside/outside constraints from a coarse visual hull or bounding volume.

Scale:

- Train/fit in metric coordinates after the current scale service.
- Compute volume from the extracted metric mesh or directly from occupied voxels.

Watertight by construction:

- The zero level set of a continuous scalar field over a bounded domain is extracted
  as a coherent surface.
- Closure comes from the implicit domain and boundary conditions, not mesh patching.

Avoiding non-manifold structure:

- Use extraction algorithms with manifold guarantees where possible.
- Avoid raw triangle surgery. Topology comes from the scalar field.

Impact:

- Disruptive for meshing internals but preserves upstream data acquisition.
- Neural SDF adds model/runtime/dependency concerns.

Risks:

- Classical SDF fitting can oversmooth or hallucinate closure.
- Neural SDF/NeRF requires training data, GPU expectations, and stronger validation.
- Volume may drift if free-space constraints are weak.

Complexity:

- Classical RBF/Poisson-like implicit SDF: medium/high.
- Neural SDF or NeRF-derived geometry: high.

## Option C: Hybrid Volumetric + Constraint Meshing

Pipeline:

`point cloud -> volumetric solid proposal -> constrained extraction/simplification -> volume`

Integration:

- Keep the current reconstruction and segmentation.
- Build a conservative volumetric solid first.
- Extract a topologically valid surface, then simplify/project vertices under bounded
  geometric constraints.

Existing point cloud:

- Drives voxel occupancy, signed distance estimation, and local projection constraints.
- The mesh is never repaired from a non-manifold Poisson output.

Scale:

- Voxel size and all geometric tolerances are metric.
- Volume can be checked against both voxel count and extracted mesh volume.

Watertight by construction:

- The source object is a closed voxel/implicit solid.
- Constraint meshing refines an already valid solid surface.

Avoiding non-manifold structure:

- Use well-composed voxelization, Marching Cubes 33, dual contouring with topology
  checks, or manifold tetrahedral extraction.

Impact:

- Moderate/high. It can start as an experimental meshing path while leaving the old
  path behind a flag.

Risks:

- Naive voxel surfaces can still create non-manifold triangulations in ambiguous
  configurations.
- Projection back to points can reopen defects unless constrained.

Complexity:

- Medium for coarse voxel proof-of-concept.
- High for production-quality constrained extraction.

## Prototype Result

The included prototype uses the available backend runtime only: Open3D, NumPy, and
SciPy. It builds a binary voxel solid from the frozen point clouds, keeps the dominant
volumetric component, and extracts external voxel faces. This is not TSDF and not
production Marching Cubes; it is a minimal architectural probe.

Set 1:

- Poisson: 191 boundary edges, 4 non-manifold edges, not orientable, not watertight.
- Volumetric voxel surface: 0 boundary edges, 1 non-manifold edge, one component,
  not orientable, not watertight.
- Voxel volume estimate: 97.375 m3 vs pipeline reference 156.9277 m3.

Set 2:

- Poisson: 226 boundary edges, 39 non-manifold edges, not orientable, not watertight.
- Volumetric voxel surface: 0 boundary edges, 0 non-manifold edges, orientable,
  watertight.
- Extracted volume: 135.671875 m3 vs pipeline reference 46.7197 m3.

## Interpretation

The volumetric approach improves structural topology substantially and fully solves
Set 2 topological validity in this coarse prototype. It does not yet satisfy the full
success criterion because Set 1 still has one non-manifold edge and the volume drift
is not controlled.

The result supports the architectural shift but rejects this exact naive voxel method
as production-ready. The next viable path is a real TSDF/SDF extraction pipeline with
a manifold extraction algorithm and explicit metric resolution validation.

## Strategic Decision

Do not continue with Poisson repair, alpha fallback, or external mesh repair as the
main solution.

Proceed with a volumetric reconstruction branch:

1. Extract or generate per-view depth from ODM/MVS outputs.
2. Implement TSDF fusion in metric coordinates.
3. Use Marching Cubes or dual contouring from the scalar field.
4. Validate topology and volume on Set 1 and Set 2 before integration.

If TSDF cannot control volume drift from available captures, move to hybrid constrained
meshing or learned geometry with camera-ray/free-space constraints.

## TSDF / SDF Prototype

The next experiment implements a functional SDF/TSDF prototype in
`tsdf_sdf_prototype.py`.

This is still isolated and does not modify the production pipeline.

### Input

- Set 1 frozen point cloud:
  `surface_closure_diagnostics/poisson_input_cloud.ply`
- Set 2 frozen point cloud:
  `surface_closure_diagnostics_2/poisson_input_cloud.ply`

### Representation

The prototype builds a metric scalar field:

- Unsigned distance: nearest-neighbor Euclidean distance from each grid node to the
  scaled point cloud using `scipy.spatial.cKDTree`.
- Sign: inside/outside prior from the dominant volumetric component generated from
  the segmented point cloud.
- TSDF band: distances are truncated to `0.75 m`, equal to `3 * grid_step` for the
  current `0.25 m` grid.

This is a point-cloud SDF with TSDF truncation. It is not yet full multi-view TSDF
fusion because the current experiment uses frozen point clouds, not per-view depth
maps or camera-ray integration.

### Surface Extraction

The prototype uses an in-repo marching tetrahedra extractor over the scalar field.
This avoids Poisson, alpha shapes, convex hulls, and mesh repair. The mesh is born
from the zero level set of the scalar field.

Outputs:

- `tsdf_outputs/set1/sdf_grid.npz`
- `tsdf_outputs/set1/sdf_marching_tetrahedra_mesh.ply`
- `tsdf_outputs/set2/sdf_grid.npz`
- `tsdf_outputs/set2/sdf_marching_tetrahedra_mesh.ply`
- `tsdf_outputs/tsdf_sdf_results.json`

### Comparative Results

Set 1:

- Poisson: 191 boundary edges, 4 non-manifold edges, not orientable, not watertight.
- Voxel baseline: 0 boundary edges, 1 non-manifold edge, not orientable, not watertight.
- SDF/TSDF: 0 boundary edges, 0 non-manifold edges, orientable, watertight.
- SDF/TSDF volume: 95.756277 m3.
- SDF/TSDF bbox drift vs Poisson: 0.48026213.
- SDF/TSDF area drift vs Poisson: -29.404725%.
- SDF/TSDF Hausdorff approx vs Poisson: 10.759122.
- SDF/TSDF Chamfer approx vs Poisson: 3.987835.

Set 2:

- Poisson: 226 boundary edges, 39 non-manifold edges, not orientable, not watertight.
- Voxel baseline: 0 boundary edges, 0 non-manifold edges, orientable, watertight.
- SDF/TSDF: 0 boundary edges, 0 non-manifold edges, orientable, watertight.
- SDF/TSDF volume: 133.573573 m3.
- SDF/TSDF bbox drift vs Poisson: 0.03400707.
- SDF/TSDF area drift vs Poisson: 50.863806%.
- SDF/TSDF Hausdorff approx vs Poisson: 1.309915.
- SDF/TSDF Chamfer approx vs Poisson: 1.221416.

### Evaluation

The SDF/TSDF prototype satisfies the structural criterion:

- Boundary edges are eliminated in both sets.
- Non-manifold edges are eliminated in both sets.
- Non-manifold vertices are eliminated in both sets.
- Both outputs are orientable and watertight.
- No post-hoc mesh repair is used as the primary mechanism.

It does not yet satisfy the full precision criterion:

- Set 1 geometry is still distorted by the inside/outside prior.
- Set 2 volume remains close to the voxel baseline rather than the prior pipeline
  reference.
- The experiment lacks true multi-view free-space constraints, so the sign field can
  overfill or underfill where point observations are incomplete.

### Recommendation

This validates the architectural direction but not the current point-cloud-only SDF
as a drop-in replacement.

The next implementation should be true TSDF fusion:

1. Use OpenSfM/ODM camera poses and depth/depth-like observations.
2. Integrate signed distances along camera rays, with free-space carving.
3. Keep voxel size, truncation distance, and integration weights in metric units.
4. Extract the zero level set with a manifold surface extractor.
5. Compare against Set 1 and Set 2 before any pipeline integration.

If ODM depth products are unavailable or insufficient, use a hybrid method: global
SDF plus camera-ray free-space constraints and constrained manifold extraction.

## Camera-Ray TSDF Prototype

The next isolated prototype is implemented in `camera_tsdf_prototype.py`.

This experiment uses actual SfM/ODM camera data:

- Set 1 NodeODM task: `56396d01-c139-445e-ba50-55644781e877`
- Set 2 NodeODM task: `002ca5e3-6eca-4aba-b3e2-623f97878136`
- OpenSfM poses: `/nodeodm-data/<task>/opensfm/reconstruction.json`
- Intrinsics: OpenSfM camera records in the same reconstruction file
- Depth products detected: `/nodeodm-data/<task>/opensfm/undistorted/openmvs/depthmaps/*.dmap`

The runtime does not include an OpenMVS `.dmap` decoder, so the experiment uses the
allowed fallback: approximate depth from SfM landmark reprojection.

### Method

For each dataset:

1. Load OpenSfM cameras, shot rotations/translations, and sparse landmarks.
2. Robustly align SfM coordinates to the metric processed point-cloud frame.
3. Select the cameras with the highest projected landmark support.
4. For each voxel and each selected camera:
   - Project voxel into the image using camera intrinsics and pose.
   - Query nearest projected SfM landmark as sparse depth observation.
   - Integrate TSDF value `observed_depth - voxel_depth`.
   - Positive values are free space before observed depth.
   - Negative values are behind observed depth.
5. Fuse all camera TSDF values with projection-distance weighting.
6. Extract the zero level set with marching tetrahedra.

This is ray-based and camera-driven, not point-cloud nearest-neighbor SDF. It is still
not full dense TSDF fusion because depth is sparse and approximate.

### Outputs

- `camera_tsdf_outputs/set1/camera_ray_tsdf_grid.npz`
- `camera_tsdf_outputs/set1/camera_ray_tsdf_mesh.ply`
- `camera_tsdf_outputs/set2/camera_ray_tsdf_grid.npz`
- `camera_tsdf_outputs/set2/camera_ray_tsdf_mesh.ply`
- `camera_tsdf_outputs/camera_tsdf_results.json`

### Results

Set 1 camera TSDF:

- Cameras used: 10
- Known voxel ratio: 0.248847
- Boundary edges: 0
- Non-manifold edges: 0
- Non-manifold vertices: 0
- Orientable: true
- Watertight: false
- Connected components: 23
- Volume: null
- Bbox drift vs Poisson: 0.24602666
- Area drift vs Poisson: +126.0992%
- Hausdorff approx vs Poisson: 4.67374
- Chamfer approx vs Poisson: 1.834984

Set 2 camera TSDF:

- Cameras used: 10
- Known voxel ratio: 0.167967
- Boundary edges: 232
- Non-manifold edges: 0
- Non-manifold vertices: 0
- Orientable: true
- Watertight: false
- Connected components: 30
- Volume: null
- Bbox drift vs Poisson: 0.14442085
- Area drift vs Poisson: +131.873704%
- Hausdorff approx vs Poisson: 5.34958
- Chamfer approx vs Poisson: 2.058291

A second coverage stress test using more cameras and a larger reprojection radius
increased known voxel ratio but did not improve the result. Set 2 boundary edges
increased, confirming that sparse landmark reprojection is not a sufficient depth
source for production TSDF.

### Evaluation Against Criteria

The camera TSDF prototype satisfies:

- No mesh repair as structural mechanism.
- Real camera poses and intrinsics are used.
- TSDF sign is ray/depth based rather than KDTree-to-point-cloud based.
- Non-manifold edges are eliminated in both sets.
- Orientability is achieved in both sets.
- Camera-ray geometry improves Set 1 bbox and distance metrics versus point-cloud SDF.

It fails:

- Watertight is not consistent in either set.
- Set 2 still has boundary edges.
- Volume cannot be computed from the extracted meshes.
- Area drift is higher than point-cloud SDF and voxel baseline.
- Sparse SfM landmark depth is too incomplete to define a stable closed zero level set.

### Final Decision

Do not integrate this prototype as a pipeline replacement.

The architectural direction remains correct, but a successful real TSDF requires dense
depth, not sparse SfM depth approximation. The next viable implementation must decode
OpenMVS `.dmap` depth maps or generate dense depth maps, then fuse them with camera-ray
free-space constraints. If dense depth cannot be obtained reliably from NodeODM, the
system should evolve to a hybrid approach:

- camera-ray free-space carving from SfM/ODM poses,
- dense learned or MVS depth,
- global SDF regularization,
- manifold extraction from the scalar field.

## Dense Depth TSDF Prototype

The dense-depth upgrade is implemented in `dense_depth_tsdf_prototype.py`.

This experiment keeps the pipeline untouched and replaces only the TSDF depth signal:

- Previous camera TSDF input: sparse pseudo-depth from SfM landmark reprojection.
- New dense-depth TSDF input: OpenMVS `.dmap` dense depth maps generated by NodeODM.

### OpenMVS `.dmap` Reader

The local OpenMVS depth maps are binary `.dmap` files. The implemented reader parses:

- `DR` header.
- image/depth dimensions.
- min/max depth range.
- source image path.
- 196-byte metadata block.
- payload with 5 `float32` channels per pixel.

The first float32 channel is used as dense per-pixel depth. The reader maps
`Capturade...png.tif` depth images back to OpenSfM shot ids like
`Capturade...png`.

### TSDF Fusion

For each dataset:

1. Load OpenSfM poses/intrinsics from `/nodeodm-data/<task>/opensfm/reconstruction.json`.
2. Load dense OpenMVS `.dmap` depth maps.
3. Robustly align SfM frame to the metric processed cloud frame.
4. Project every voxel into each selected depth map.
5. Sample real depth per pixel.
6. Integrate signed distance `depth_pixel - voxel_depth`.
7. Truncate in metric units.
8. Fuse multi-view TSDF by weighted averaging.
9. Extract surface with marching tetrahedra.

This is dense-depth ray-based TSDF. It does not use Poisson, alpha shapes, convex hull,
or mesh repair.

### Primary Run: Conservative Integration

Configuration:

- `DENSE_TSDF_GRID_STEP_M=0.35`
- `DENSE_TSDF_MAX_DEPTHMAPS=12`
- `DENSE_TSDF_MIN_WEIGHT=2.0`

Set 1:

- Depth maps used: 7
- Known voxel ratio: 0.001300
- Dense-depth TSDF: watertight true, boundary edges 0, non-manifold edges 0.
- Components: 17
- Volume: 0.078526 m3
- Bbox drift vs Poisson: 0.68961878
- Area drift vs Poisson: -98.217917%
- Chamfer approx vs Poisson: 7.525142

Set 2:

- Depth maps used: 11
- Known voxel ratio: 0.001368
- Dense-depth TSDF: watertight true, boundary edges 0, non-manifold edges 0.
- Components: 6
- Volume: 0.145167 m3
- Bbox drift vs Poisson: 0.68692286
- Area drift vs Poisson: -97.743801%
- Chamfer approx vs Poisson: 3.358572

This run proves that dense depth can generate topologically closed local components,
but coverage is far too sparse for full-object volume.

### Sensitivity Run: Lower Weight Threshold

Configuration:

- `DENSE_TSDF_GRID_STEP_M=0.35`
- `DENSE_TSDF_MAX_DEPTHMAPS=12`
- `DENSE_TSDF_MIN_WEIGHT=0.1`

Set 1:

- Known voxel ratio: 0.025996
- Boundary edges: 80
- Non-manifold edges: 0
- Watertight: false
- Components: 56
- Volume: null
- Bbox drift vs Poisson: 0.36286241
- Area drift vs Poisson: -47.407438%
- Chamfer approx vs Poisson: 5.164254

Set 2:

- Known voxel ratio: 0.024186
- Boundary edges: 6
- Non-manifold edges: 0
- Watertight: false
- Components: 40
- Volume: null
- Bbox drift vs Poisson: 0.06806145
- Area drift vs Poisson: -53.02338%
- Chamfer approx vs Poisson: 1.865074

This run confirms that real dense depth improves geometric alignment and, for Set 2,
dramatically reduces boundary edges compared with pseudo-depth camera TSDF
(`232 -> 6`). It still fails the final criterion because the depth support is
fragmented and does not produce a single stable watertight object.

### Dense Depth Decision

Dense-depth TSDF is not ready to replace the pipeline yet.

The experiment validates the correct direction but exposes a new bottleneck:

- OpenMVS depth maps are sparse after filtering for these screenshot datasets.
- Set 1 valid depth ratios are only about 5-7% for selected views.
- Set 2 selected views are better, about 2-23%, but still insufficient for full
  object closure at the current grid/projection setup.
- The robust SfM-to-metric alignment is approximate and likely contributes to depth
  projection mismatch.

Next technical step:

1. Consume OpenMVS camera metadata directly from `.mvs` or the `.dmap` metadata block,
   avoiding the current robust alignment approximation.
2. Use all valid dense depth pixels by integrating pixels/rays into TSDF, rather than
   projecting voxels and nearest-sampling depth.
3. Add free-space carving along depth rays before surface extraction.
4. Re-run Set 1 and Set 2 with dense depth coverage diagnostics.

Final decision for now:

- Do not return to Poisson.
- Do not use mesh repair as a structural solution.
- Do not integrate the current dense-depth TSDF into production.
- Continue TSDF development with exact OpenMVS camera/depth coordinate coupling.

## Ray-Based Free-Space Carving Layer

The free-space upgrade is implemented as an optional plug-in layer:

- `ray_integration.py`

It does not replace the dense-depth TSDF module. It returns an additive TSDF update,
weights, and visibility masks. The base TSDF remains available unchanged when
`DENSE_TSDF_ENABLE_RAY_CARVING=0`.

### Algorithm

For each selected OpenMVS depth map:

1. Iterate valid depth pixels with configurable stride.
2. Reconstruct a camera ray using OpenSfM pose and intrinsics.
3. Transform the ray into the metric reconstruction frame.
4. Traverse voxels along the ray.
5. Mark voxels before the depth hit as observed free space.
6. Mark voxels near the depth hit as surface band.
7. Ignore voxels behind the hit as occluded.
8. Return TSDF update and visibility weights.

The existing TSDF convention is preserved:

- positive: observed free space before the surface.
- near zero: surface band.
- negative: behind/inside the observed surface band.

The merge is non-destructive:

`refined_tsdf = weighted_merge(base_tsdf, ray_update)`

### Primary Ray-Carving Run

Configuration:

- `DENSE_TSDF_MIN_WEIGHT=0.1`
- `DENSE_TSDF_ENABLE_RAY_CARVING=1`
- `DENSE_TSDF_RAY_PIXEL_STRIDE=18`
- `DENSE_TSDF_RAY_WEIGHT_SCALE=1.0`

Set 1:

- Base known voxel ratio: 0.025996
- Refined known voxel ratio: 0.064403
- Rays integrated: 12064
- Free-space voxels: 1968
- Surface voxels: 2149
- Components: 56 -> 47
- Boundary edges: 80 -> 66
- Non-manifold edges: 0 -> 0
- Watertight: false -> false
- Volume: null -> null

Set 2:

- Base known voxel ratio: 0.024186
- Refined known voxel ratio: 0.075397
- Rays integrated: 41882
- Free-space voxels: 1262
- Surface voxels: 1784
- Components: 40 -> 36
- Boundary edges: 6 -> 6
- Non-manifold edges: 0 -> 1
- Watertight: false -> false
- Volume: null -> null

### Lower-Weight Sensitivity Run

Configuration:

- `DENSE_TSDF_RAY_WEIGHT_SCALE=0.25`

Set 1:

- Refined known voxel ratio: 0.062600
- Components: 56 -> 44
- Boundary edges: 80 -> 72
- Non-manifold edges: 0 -> 0
- Watertight: false -> false

Set 2:

- Refined known voxel ratio: 0.074302
- Components: 40 -> 28
- Boundary edges: 6 -> 6
- Non-manifold edges: 0 -> 1
- Watertight: false -> false

### Ray-Carving Decision

The plug-in layer works as intended as a visibility integration layer:

- It significantly increases observed/known voxel coverage.
- It reduces fragmentation in both datasets.
- It reduces boundary edges for Set 1.
- It remains optional and the dense-depth TSDF still runs without it.

It does not yet satisfy the final success criterion:

- Watertight consistency is not recovered.
- Set 2 keeps boundary edges.
- Low-weight and full-weight variants can introduce small non-manifold artifacts in
  Set 2, which means free-space evidence is not yet spatially aligned enough.
- Volume remains unavailable after extraction.

Technical conclusion:

Ray-based free-space carving is the correct architectural layer, but its current
quality is limited by approximate SfM-to-metric alignment and by using OpenSfM camera
models while sampling OpenMVS depth maps. The next step is not to remove ray carving;
it is to bind rays to the exact OpenMVS camera/depth metadata from `.mvs`/`.dmap`
instead of the current approximate bridge.

## Validation + Alignment Layer

This phase adds a pre-TSDF plug-in module:

- `validation_alignment_layer.py`

It runs before dense-depth TSDF fusion and can be toggled with:

- `DENSE_TSDF_ENABLE_ALIGNMENT_LAYER=1`

When the flag is disabled, dense-depth TSDF runs as before. The layer does not modify
OpenMVS, OpenSfM, the base TSDF extractor, ray carving, or mesh extraction.

### Layer Responsibilities

For each `.dmap` frame the layer:

1. Samples valid dense-depth pixels.
2. Reconstructs sampled depth points through the OpenSfM camera pose.
3. Converts those points to the metric TSDF frame.
4. Measures voxel-grid coverage.
5. Estimates spatial consistency against the processed metric cloud.
6. Computes depth discontinuity and TSDF contribution variance proxies.
7. Flags bad frames and assigns a per-frame weight multiplier.

For the dataset as a whole it estimates only global, non-deforming corrections:

- global scale correction,
- origin/center offset correction,
- rejected-frame list,
- accepted-frame list,
- drift report.

The TSDF fusion consumes the accepted depth maps and multiplies per-frame TSDF
contributions by `alignment_weight_multiplier`.

### Alignment-Only Experiment

Configuration:

- `DENSE_TSDF_GRID_STEP_M=0.35`
- `DENSE_TSDF_MAX_DEPTHMAPS=12`
- `DENSE_TSDF_MIN_WEIGHT=0.1`
- `DENSE_TSDF_ENABLE_ALIGNMENT_LAYER=1`
- `DENSE_TSDF_ALIGNMENT_MIN_COVERAGE=0.02`
- `DENSE_TSDF_ALIGNMENT_MAX_ERROR_M=2.5`
- `DENSE_TSDF_ENABLE_RAY_CARVING=0`

Set 1:

- Scale correction: 0.780479
- Offset correction: `[-0.237183, -1.882064, -0.697847] m`
- Frames: 7 input, 7 accepted, 0 rejected
- Median consistency error: 1.009785 m
- Mean voxel coverage: 0.921824
- Known voxel ratio: 0.025996 -> 0.014004
- Components: 56 -> 35
- Boundary edges: 80 -> 18
- Non-manifold edges: 0 -> 0
- Watertight: false -> false
- BBox drift: 0.36286241 -> 0.46487168
- Area drift: -47.407438% -> -69.633404%

Set 2:

- Scale correction: 1.218154
- Offset correction: `[0.181147, -0.319858, -0.294882] m`
- Frames: 11 input, 9 accepted, 2 rejected
- Rejected frames: `depth0021.dmap`, `depth0005.dmap`
- Median consistency error: 0.661309 m
- Mean voxel coverage: 0.996982
- Known voxel ratio: 0.024186 -> 0.043138
- Components: 40 -> 63
- Boundary edges: 6 -> 12
- Non-manifold edges: 0 -> 0
- Watertight: false -> false
- BBox drift: 0.06806145 -> 0.13725012
- Area drift: -53.02338% -> -20.911198%
- Chamfer approx: 1.929819 -> 1.898001

### Alignment + Ray-Carving Experiment

Configuration:

- `DENSE_TSDF_ENABLE_ALIGNMENT_LAYER=1`
- `DENSE_TSDF_ENABLE_RAY_CARVING=1`
- `DENSE_TSDF_RAY_PIXEL_STRIDE=18`
- `DENSE_TSDF_RAY_WEIGHT_SCALE=0.25`

Set 1:

- Known voxel ratio: 0.014004 -> 0.049937
- Rays integrated: 12064
- Free-space voxels: 1729
- Surface voxels: 1555
- Components: 35 -> 39
- Boundary edges: 18 -> 18
- Non-manifold edges: 0 -> 0
- Non-manifold vertices: 0 -> 4
- Watertight: false -> false

Set 2:

- Known voxel ratio: 0.043138 -> 0.107177
- Rays integrated: 41174
- Free-space voxels: 1965
- Surface voxels: 2443
- Components: 63 -> 50
- Boundary edges: 12 -> 12
- Non-manifold edges: 0 -> 1
- Non-manifold vertices: 0 -> 9
- Watertight: false -> false

### Alignment-Layer Decision

The validation/alignment layer is useful and should remain in the experimental
architecture:

- It detects measurable OpenMVS-depth-to-TSDF-frame drift.
- It finds bad frames in Set 2 that were previously integrated blindly.
- It substantially improves Set 1 topology under alignment-only mode.
- It increases known voxel coverage when combined with ray carving.

It is not yet sufficient as a final correction layer:

- Set 1 loses known voxel ratio under alignment-only mode.
- Set 2 improves coverage and Chamfer slightly, but fragmentation increases.
- Ray carving still behaves as a corrective layer rather than a pure refinement layer.
- Watertight consistency is still not recovered in either dataset.

Technical conclusion:

The remaining bottleneck is not mesh repair or Poisson. It is residual camera/depth
coordinate inconsistency and incomplete free-space/surface evidence coupling. The next
required step is to replace the approximate OpenSfM-to-OpenMVS bridge with exact
OpenMVS camera metadata parsing from the `.mvs` scene and `.dmap` metadata, then repeat
the same alignment and ray-carving experiments without changing the production
pipeline.

## Self-Consistent Camera Refinement Layer

This phase adds a second pre-refinement plug-in module:

- `sccr_camera_refinement.py`

It is enabled with:

- `DENSE_TSDF_ENABLE_SCCR_LAYER=1`

The layer does not assume perfect camera metadata and does not run bundle adjustment.
It uses the coarse TSDF itself as the consistency reference for small, regularized
camera-pose updates.

### SCCR Pipeline Order

The experimental order is:

1. Load approximate OpenSfM/OpenMVS cameras and dense depth maps.
2. Optionally run `validation_alignment_layer.py`.
3. Fuse an initial coarse dense-depth TSDF.
4. Run `sccr_camera_refinement.py` against the coarse TSDF.
5. Reintegrate dense-depth TSDF with refined poses and per-camera scores.
6. Optionally run ray-based free-space carving.
7. Extract mesh with the existing marching tetrahedra path.

When SCCR is disabled, the dense-depth TSDF prototype follows the previous behavior.

### SCCR Scoring

For each camera, SCCR computes:

- depth alignment error: sampled depth points are back-projected through the current
  pose and evaluated against the coarse TSDF zero level set.
- voxel occupancy agreement: fraction of sampled depth points landing inside known
  TSDF support.
- voxel coverage ratio: fraction of sampled depth points landing inside the TSDF grid.
- silhouette overlap proxy: coarse TSDF surface samples projected into the frame are
  compared with valid depth pixels.
- surface depth error: projected TSDF surface depth is compared with dense depth.
- TSDF alignment stability: variance of TSDF residuals around sampled depth points.

The camera score is a weighted metric over these terms. Low-score cameras are
downweighted or rejected.

### SCCR Pose Refinement

SCCR performs local coordinate search only:

- translation perturbations: `+/- DENSE_TSDF_SCCR_TRANSLATION_STEP_M`
- rotation perturbations: `+/- DENSE_TSDF_SCCR_ROTATION_STEP_DEG`
- default iterations: `DENSE_TSDF_SCCR_ITERATIONS=2`

Candidate poses are accepted only when the regularized TSDF/depth consistency
objective improves. This keeps the layer intentionally weaker than full bundle
adjustment and prevents global drift.

### SCCR Outputs

The dense-depth TSDF report now includes:

- `sccr_camera_refinement`
- `camera_metrics_before`
- `camera_metrics_after`
- `accepted_frames`
- `rejected_frames`
- `sccr_coarse_dense_depth_tsdf_metrics`
- refined dense-depth TSDF metrics after reintegration

Per accepted camera, SCCR writes:

- refined `shot.rotation`
- refined `shot.translation`
- `sccr_camera_score`
- updated `alignment_weight_multiplier`

### SCCR Runtime Status

Implementation status:

- `sccr_camera_refinement.py` created.
- `dense_depth_tsdf_prototype.py` integrated with optional SCCR toggle.
- Python syntax validated with the bundled Codex Python runtime.

Experimental execution status:

- Full Set 1 / Set 2 SCCR execution requires the ForestVol container runtime because
  the local bundled Python environment does not include `scipy` and `open3d`.
- The Docker daemon was unavailable during this phase:
  `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`.

Therefore, comparative SCCR metrics are pending runtime availability. The exact command
for the first full run is:

```bash
PYTHONPATH=/tmp \
DENSE_TSDF_ROOT=/app \
NODEODM_ROOT=/nodeodm-data \
DENSE_TSDF_OUT=/app/data/dense_depth_tsdf_sccr_outputs \
DENSE_TSDF_GRID_STEP_M=0.35 \
DENSE_TSDF_MAX_DEPTHMAPS=12 \
DENSE_TSDF_MIN_WEIGHT=0.1 \
DENSE_TSDF_ENABLE_ALIGNMENT_LAYER=1 \
DENSE_TSDF_ALIGNMENT_MIN_COVERAGE=0.02 \
DENSE_TSDF_ALIGNMENT_MAX_ERROR_M=2.5 \
DENSE_TSDF_ENABLE_SCCR_LAYER=1 \
DENSE_TSDF_SCCR_ITERATIONS=2 \
DENSE_TSDF_SCCR_TRANSLATION_STEP_M=0.08 \
DENSE_TSDF_SCCR_ROTATION_STEP_DEG=0.35 \
DENSE_TSDF_ENABLE_RAY_CARVING=1 \
DENSE_TSDF_RAY_PIXEL_STRIDE=18 \
DENSE_TSDF_RAY_WEIGHT_SCALE=0.25 \
python /tmp/dense_depth_tsdf_prototype.py
```

### SCCR Decision Gate

SCCR should only be promoted if the pending run shows:

- lower component count than dense-depth TSDF plus alignment,
- lower TSDF consistency/depth alignment error after refinement,
- higher known voxel ratio without increasing non-manifold defects,
- lower boundary edge count,
- better stability between Set 1 and Set 2.

If SCCR improves camera scores but not mesh topology, the bottleneck is likely not
recoverable by local pose refinement alone and requires a stronger joint formulation:
camera-depth confidence estimation, exact OpenMVS camera parsing, or learned/hybrid
geometry constraints.

## SCCR Experimental Validation

Run ID:

- `SCCR-VALIDATION-01`

Environment:

- Docker Desktop: operational.
- Containers: `forestvol-backend`, `forestvol-frontend`, `forestvol-nodeodm`.
- Backend runtime: Python 3.11.15, scipy 1.17.1, Open3D 0.19.0, numpy 2.4.6.
- Total SCCR protocol time: 56 seconds.
- Approximate post-run backend memory: `997.4MiB / 7.616GiB`.
- Stage timing was not available because the existing prototype has no stage timer and
  code was not modified during validation.

Environment correction:

- Historical Set 2 task path `002ca5e3-6eca-4aba-b3e2-623f97878136` was absent from
  the NodeODM volume.
- The path was restored from existing task `37fe01cd-356f-4776-952a-17e989f8452b`,
  which uses the same Set 2 image directory.
- No NodeODM reconstruction was rerun.
- No project code or parameters were changed for this validation.

Deliverables:

- `projects/ForestVol/data/dense_depth_tsdf_sccr_outputs/benchmark_results.json`
- `projects/ForestVol/data/dense_depth_tsdf_sccr_outputs/benchmark_comparison.csv`
- `projects/ForestVol/data/dense_depth_tsdf_sccr_outputs/benchmark_summary.md`

### SCCR Metrics Versus Dense Depth + Alignment

Set 1:

- Components: 37 -> 32
- Boundary edges: 18 -> 0
- Non-manifold edges: 0 -> 0
- Non-manifold vertices: 0 -> 0
- Watertight: false -> true
- Orientable: true -> true
- Known voxel ratio: 0.014004 -> 0.014591
- BBox drift: 0.46487168 -> 0.49423951
- Area drift: -70.659436% -> -69.299877%
- Chamfer: 4.478468 -> 4.389832
- Hausdorff: 10.819039 -> 10.623811
- Volume: null -> 7.077038 m3

Set 2:

- Components: 63 -> 28
- Boundary edges: 12 -> 0
- Non-manifold edges: 0 -> 0
- Non-manifold vertices: 0 -> 0
- Watertight: false -> true
- Orientable: true -> true
- Known voxel ratio: 0.043103 -> 0.01081
- BBox drift: 0.13725012 -> 0.22747311
- Area drift: -20.845712% -> -77.619474%
- Chamfer: 1.861858 -> 1.746864
- Hausdorff: 3.290061 -> 4.539742
- Volume: null -> 1.620532 m3

SCCR camera refinement diagnostics:

- Set 1 mean camera score: 0.677278 -> 0.682209
- Set 1 median depth alignment error: 0.371768 m -> 0.36939 m
- Set 1 pose updates: 6
- Set 2 mean camera score: 0.601486 -> 0.635381
- Set 2 median depth alignment error: 0.476134 m -> 0.462423 m
- Set 2 pose updates: 15

### SCCR Validation Decision

Decision:

- **B. SCCR aporta mejoras topologicas claras, pero debe permanecer como experimento.**

Data basis:

- SCCR improves topology in both datasets: boundary edges go to zero, non-manifold
  edges remain zero, and the non-ray SCCR meshes become watertight.
- SCCR reduces fragmentation in both datasets: Set 1 components 37 -> 32; Set 2
  components 63 -> 28.
- SCCR improves Chamfer in both datasets.
- SCCR does not yet provide stable geometry/volume: Set 2 known voxel ratio drops,
  Set 2 Hausdorff worsens, bbox drift worsens in both datasets, and Set 2 volume is
  not stable.

Conclusion:

SCCR is not rejected, because it provides measurable topological gains. It is not ready
for integration, because geometric and volumetric stability remain insufficient. The
next architectural decision must not introduce a new layer until SCCR is either
stabilized with stronger evidence or explicitly retired.

## Volume Estimator Benchmark

Run ID:

- `VOLUME-ESTIMATORS-BENCHMARK-01`

Scope:

- The mesh is treated as an auxiliary artifact.
- The decision criterion is volumetric error against Ground Truth.
- Ground Truth was used only after estimation, for final error calculation.
- No main pipeline code was modified.
- No reconstruction method was optimized or retuned.

Ground Truth:

- `119.74 m3`

Common input:

- Set 1: `poisson_input_cloud.ply` from
  `data/processed/a3c36266-f866-402f-8bc8-1c2b59b4a4ce/surface_closure_diagnostics/`
- Set 2: `poisson_input_cloud.ply` from
  `data/processed/b6b04af0-122f-4fcc-af8a-cc553ca5e28d/surface_closure_diagnostics_2/`

Deliverables:

- `projects/ForestVol/data/volume_estimator_benchmark/benchmark_volume_estimators.json`
- `projects/ForestVol/data/volume_estimator_benchmark/benchmark_volume_estimators.csv`
- `projects/ForestVol/data/volume_estimator_benchmark/benchmark_volume_estimators.md`
- `projects/ForestVol/data/volume_estimator_benchmark/set1_volume_error.png`
- `projects/ForestVol/data/volume_estimator_benchmark/set2_volume_error.png`

Execution:

- Total benchmark time: 95 seconds.
- Approximate backend memory after benchmark: `101.3MiB / 7.616GiB`.
- Per-method memory was not measured because no profiler was added.

### Volume Results

Set 1:

- Convex Hull: 156.927698 m3, error 31.057038%.
- Alpha Shape: no valid volume.
- Voxel Occupancy: 97.375 m3, error 18.677969%.
- Octree Occupancy: 840.421875 m3, error 601.872286%.
- Surface Mesh (Poisson): no valid volume.
- TSDF Occupancy: 97.375 m3, error 18.677969%.
- Point Density Integration: 97.375 m3, error 18.677969%.

Set 2:

- Convex Hull: 82.501972 m3, error 31.099072%.
- Alpha Shape: no valid volume.
- Voxel Occupancy: 135.671875 m3, error 13.305391%.
- Octree Occupancy: 1163.25 m3, error 871.479873%.
- Surface Mesh (Poisson): no valid volume.
- TSDF Occupancy: 135.671875 m3, error 13.305391%.
- Point Density Integration: 132.671875 m3, error 10.799962%.

### Stability And Noise

Cross-set volume deltas:

- Convex Hull: 74.425726 m3.
- Voxel Occupancy: 38.296875 m3.
- TSDF Occupancy: 38.296875 m3.
- Point Density Integration: 35.296875 m3.
- Octree Occupancy: 322.828125 m3.

Noise sensitivity, volume standard deviation:

- Convex Hull: Set 1 1.199168 m3; Set 2 0.724453 m3.
- Voxel Occupancy: Set 1 0.249413 m3; Set 2 0.305667 m3.
- TSDF Occupancy: Set 1 0.0 m3; Set 2 0.0 m3.
- Point Density Integration: Set 1 0.249413 m3; Set 2 0.481341 m3.
- Octree Occupancy: Set 1 1.425279 m3; Set 2 8.792729 m3.

### Volume-First Recommendation

Recommended MVP candidate:

- **Point Density Integration**

Evidence:

- Lowest mean percent error across Set 1 and Set 2: `14.738966%`.
- Mean runtime: `0.030025 s`.
- Best Set 2 error among evaluated methods with valid volume: `10.799962%`.
- Cross-set volume delta: `35.296875 m3`, lower than Convex Hull, Voxel
  Occupancy, TSDF Occupancy, and Octree Occupancy.

Non-selected methods:

- Convex Hull is fast and stable, but mean error is about 31.08%.
- Voxel Occupancy and TSDF Occupancy tie at 15.99168% mean error, slightly worse than
  Point Density Integration.
- Alpha Shape and Poisson did not produce valid volumes in this benchmark.
- Octree Occupancy is rejected due extreme overestimation.

Conclusion:

For the MVP volume objective, the current evidence supports a volume-first estimator
based on Point Density Integration rather than a mesh-first method. The result should
remain experimental until validated on more datasets, but future MVP decisions should
prioritize this class of estimator over topological mesh quality when the objective is
minimum volumetric error.

## PDI Robustness Benchmark

Run ID:

- `RUN-PDI-ROBUSTNESS-01`

Scope:

- This phase validates the previously selected Point Density Integration estimator.
- The objective is robustness characterization, not improving the estimator.
- PDI parameters are unchanged from the previous benchmark.
- Ground Truth is used only for final error calculation.
- No main pipeline, NodeODM, OpenSfM, Open3D, TSDF, SCCR, ray carving, or reconstruction
  code was modified.

Deliverables:

- `projects/ForestVol/data/pdi_robustness_benchmark/benchmark_robustness.json`
- `projects/ForestVol/data/pdi_robustness_benchmark/benchmark_robustness.csv`
- `projects/ForestVol/data/pdi_robustness_benchmark/benchmark_robustness.md`
- `projects/ForestVol/data/pdi_robustness_benchmark/set1_robustness_errors.png`
- `projects/ForestVol/data/pdi_robustness_benchmark/set2_robustness_errors.png`
- `projects/ForestVol/data/pdi_robustness_benchmark/sensitivity_random_point_reduction.png`
- `projects/ForestVol/data/pdi_robustness_benchmark/sensitivity_gaussian_noise.png`

Execution:

- Total runtime: 10 seconds.
- Approximate backend memory after run: `91.6MiB / 7.616GiB`.

### Robustness Findings

Baseline PDI:

- Set 1: 97.375 m3, 18.677969% error.
- Set 2: 132.671875 m3, 10.799962% error.
- Cross-set difference: 35.296875 m3.
- Cross-set coefficient of variation: 0.216988.

Random point reduction:

- Set 1 remains between 18.717116% and 20.4135% error from 5% to 50% point removal.
- Set 2 remains between 8.255387% and 12.091824% error from 5% to 50% point removal.
- No abrupt error threshold was detected for random point loss.

Gaussian noise:

- Set 1 error decreases as noise inflates the occupied support, reaching 0.086646% at
  sigma 10 cm.
- Set 2 error increases with noise, reaching 25.14093% at sigma 10 cm.
- This behavior means noise can accidentally compensate underestimation in one dataset
  while harming another; it should not be interpreted as a reliable improvement.

Partial occlusion:

- Set 1 is sensitive to removed faces/bands: worst partial occlusion error is
  38.603954%.
- Set 2 partial occlusion remains lower in this test, with worst partial occlusion
  error 12.505742%.
- Structured missing regions are more damaging than random point loss.

Segmentation imperfecta:

- Missing object points are tolerated well:
  - Set 1 2%-10% removal remains around 18.5%-18.77% error.
  - Set 2 2%-10% removal remains around 10.29%-10.64% error.
- Spurious/background points are catastrophic:
  - Set 1 add 2%: 439.019438% error.
  - Set 1 add 10%: 1226.611304% error.
  - Set 2 add 2%: 452.995031% error.
  - Set 2 add 10%: 770.558084% error.

### Robustness Decision

PDI is sufficiently robust for an MVP only under explicit operating limits:

- broad object coverage,
- low background contamination,
- segmentation that avoids including off-object points,
- no missing full faces/bands/corners in capture.

PDI should not be treated as universally robust. The MVP can integrate it as the
volume-first estimator only if the product documents these limits and future work adds
quality gates for background contamination and structured occlusion.

## PDI MVP Readiness Layer

Run ID:

- `RUN-PDI-MVP-READINESS-01`

Scope:

- This phase converts Point Density Integration into an isolated experimental
  component suitable for MVP integration review.
- The production pipeline remains unchanged.
- PDI behavior and parameters remain unchanged.
- Quality gates and confidence scoring are diagnostic only; they do not stop execution
  and do not alter the point cloud or estimated volume.
- Ground Truth is used only for final error reporting.

Implementation:

- New isolated module:
  `experiments/volume_estimator_validation/pdi_estimator.py`
- New isolated benchmark runner:
  `experiments/volume_estimator_validation/pdi_mvp_readiness_benchmark.py`

PDI preserved behavior:

- `voxel_size_m`: `0.25`
- Density threshold:
  `max(1, ceil(hull_density_points_per_m3 * voxel_size_m^3 * 0.35))`
- Solid occupancy:
  binary dilation, hole fill, closing, second hole fill, dominant connected component.

Deliverables:

- `projects/ForestVol/data/pdi_mvp_readiness/benchmark_pdi_mvp_readiness.json`
- `projects/ForestVol/data/pdi_mvp_readiness/benchmark_pdi_mvp_readiness.csv`
- `projects/ForestVol/data/pdi_mvp_readiness/benchmark_pdi_mvp_readiness.md`
- `projects/ForestVol/data/pdi_mvp_readiness/pdi_technical_audit.md`
- `projects/ForestVol/data/pdi_mvp_readiness/pdi_readiness_error_confidence.png`
- `projects/ForestVol/data/pdi_mvp_readiness/pdi_quality_gates.png`

### Readiness Results

Set 1:

- Volume: `97.375 m3`
- Previous PDI volume: `97.375 m3`
- Volume delta vs previous PDI: `0.0 m3`
- Error vs Ground Truth: `18.677969%`
- Point count: `19879`
- Quality gates: `11 PASS`, `1 WARNING`, `0 FAIL`
- Confidence score: `95.0% HIGH`
- Warning: top coverage ratio `0.111111`
- PDI execution time: `0.037979 s`
- Total diagnostic time: `0.269671 s`

Set 2:

- Volume: `132.671875 m3`
- Previous PDI volume: `132.671875 m3`
- Volume delta vs previous PDI: `0.0 m3`
- Error vs Ground Truth: `10.799962%`
- Point count: `26113`
- Quality gates: `12 PASS`, `0 WARNING`, `0 FAIL`
- Confidence score: `100.0% HIGH`
- PDI execution time: `0.031168 s`
- Total diagnostic time: `0.200771 s`

Cross-dataset readiness:

- Mean confidence score: `97.5%`
- Total FAIL gates: `0`
- Numeric equivalence with previous PDI: `true`
- Ground Truth was not used by quality gates or confidence scoring.

### PDI MVP Decision

Decision:

- **SI. PDI is ready to be converted into the MVP volumetric estimator candidate, with
  the diagnostic quality-gate layer retained as an integration requirement.**

Evidence basis:

- PDI output did not change after refactoring: both Set 1 and Set 2 have exactly
  `0.0 m3` volume delta versus the previous benchmark.
- Current Set 1 and Set 2 inputs produce no quality-gate FAIL states.
- Confidence is high on both datasets: `95.0%` and `100.0%`.
- Runtime remains compatible with MVP usage: PDI execution is below `0.04 s` per set
  in the backend container.
- Previous robustness evidence still applies: PDI must be protected from background
  contamination and structured occlusion by segmentation/capture quality gates.

Operational limits:

- Do not treat PDI as universally reliable when segmentation includes off-object
  points.
- Do not use PDI confidence as Ground Truth; it is an input-quality estimate only.
- The next production integration should preserve the same estimator parameters and
  expose PASS/WARNING/FAIL diagnostics to users or downstream quality gates.

## Productive PDI Migration

Run ID:

- `RUN-PDI-PRODUCTIVE-MIGRATION-01`

Decision:

- Point Density Integration is now the official productive volume estimator.
- Mesh reconstruction is legacy/debug/visual-only and disabled by default for official
  volume calculation.
- Poisson, Alpha Shape, mesh repair and watertight mesh volume are not official
  volume sources.

Productive flow:

1. RGB images.
2. ArUco/GCP scale evidence.
3. NodeODM/OpenSfM point cloud.
4. Point-cloud cleanup and segmentation.
5. Quality gates.
6. Confidence score.
7. Point Density Integration.
8. API result.
9. Frontend display.

Backend/API fields:

- `volume_m3`
- `volume_method`
- `confidence_score`
- `confidence_level`
- `quality_gates`
- `diagnostic`
- `pdi_metrics`

Validation:

- Backend unit tests in Docker: `32 passed`.
- Frontend image rebuilt and includes PDI volume, confidence score, quality gates and
  diagnostic display.
- Official API flow was executed for Set 1 and Set 2 without experimental benchmark
  scripts.

Set 1 official API result:

- Session: `b3c14c84-b660-407f-817f-1fc185ce3e9c`
- State: `COMPLETED`
- Images: `18`
- Volume: `69.8281 m3`
- Method: `point_density_integration`
- Confidence: `100.0% HIGH`
- Quality gates: `0 FAIL`
- Error vs Ground Truth: `41.6836%`
- Runtime: `292.533 s`

Set 2 official API result:

- Session: `723f91e2-b1b5-43f7-b336-6816d8300509`
- State: `COMPLETED`
- Images: `28`
- Volume: `39.0156 m3`
- Method: `point_density_integration`
- Confidence: `25.0% CRITICAL`
- Quality gates: `5 FAIL`
- Error vs Ground Truth: `67.4164%`
- Runtime: `335.804 s`

Acceptance status:

- Productive integration: **complete**.
- Hito 0.5 official acceptance: **blocked**.

Blocking reason:

- The productive pipeline uses PDI end to end and completes, but both official end-to-end
  runs exceed the Hito 0.5 volumetric error threshold.
- This is an acceptance failure, not a runtime failure.
- No new reconstruction research, PDI tuning, Poisson fallback, or Ground Truth-based
  parameter adjustment was introduced.

Evidence:

- `projects/ForestVol/data/pdi_productive_migration_hito05_set1.json`
- `projects/ForestVol/data/pdi_productive_migration_hito05_set2.json`
- `projects/ForestVol/data/pdi_productive_migration_summary.csv`
- `projects/ForestVol/data/pdi_productive_migration_summary.md`
