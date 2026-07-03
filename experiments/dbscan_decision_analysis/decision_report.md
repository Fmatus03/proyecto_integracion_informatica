# DBSCAN Decision Report

## set1

- Selected clusters: `[14, 0]`.
- Selected PDI volume: `69.8281` m3.
- Best simulated combination by PDI volume: `[14, 2, 31]` -> `82.2969` m3.
- Segmentation voxelization loss: `0.921054` of after-outlier points.
- Cluster selection loss after DBSCAN input: `0.497887`.
- Selected points ratio after outlier: `0.03964`.
- Evidence: the observed 96-99% loss is dominated by the segmentation-stage voxelization used before DBSCAN, then compounded by the current cluster selection/ranking.

## set2

- Selected clusters: `[4, 8]`.
- Selected PDI volume: `39.0156` m3.
- Best simulated combination by PDI volume: `[4, 8, 2]` -> `42.1719` m3.
- Segmentation voxelization loss: `0.988467` of after-outlier points.
- Cluster selection loss after DBSCAN input: `0.219524`.
- Selected points ratio after outlier: `0.009001`.
- Evidence: the observed 96-99% loss is dominated by the segmentation-stage voxelization used before DBSCAN, then compounded by the current cluster selection/ranking.

No pipeline change is proposed or applied in this experiment.
