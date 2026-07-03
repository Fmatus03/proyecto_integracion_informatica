# Cloud Source Validation

Resultado: PASS. Los benchmarks posteriores a la unificacion consumen exactamente el `point_cloud.ply` productivo mediante CloudProvider.

{
  "all_sources_match": true,
  "validated_fields": [
    "sha256",
    "point_count",
    "bbox_extent",
    "centroid",
    "canonical_path"
  ],
  "sources": [
    {
      "dataset": "set1",
      "session_id": "b3c14c84-b660-407f-817f-1fc185ce3e9c",
      "canonical_path": "/app/data/processed/b3c14c84-b660-407f-817f-1fc185ce3e9c/point_cloud.ply",
      "session_point_cloud_path": "/app/data/processed/b3c14c84-b660-407f-817f-1fc185ce3e9c/point_cloud.ply",
      "provider_path": "/app/data/processed/b3c14c84-b660-407f-817f-1fc185ce3e9c/point_cloud.ply",
      "sha256": "99c67aeed8feb3ab06bfe0f74c932af67aabbe5ebb0c8736b879c042846af777",
      "point_count": 401873,
      "bbox_extent": [
        29.503054619,
        28.359482765,
        40.850132942
      ],
      "centroid": [
        5.826524401,
        -0.680232534,
        -1.48903425
      ],
      "path_match": true
    },
    {
      "dataset": "set2",
      "session_id": "723f91e2-b1b5-43f7-b336-6816d8300509",
      "canonical_path": "/app/data/processed/723f91e2-b1b5-43f7-b336-6816d8300509/point_cloud.ply",
      "session_point_cloud_path": "/app/data/processed/723f91e2-b1b5-43f7-b336-6816d8300509/point_cloud.ply",
      "provider_path": "/app/data/processed/723f91e2-b1b5-43f7-b336-6816d8300509/point_cloud.ply",
      "sha256": "4ede2ae47fd561c67a1de73afcb3adcfc20297164b2084c911ff3785dda6d88b",
      "point_count": 371766,
      "bbox_extent": [
        12.329556823,
        11.339449644,
        9.058027625
      ],
      "centroid": [
        0.572442388,
        -0.423265432,
        -1.393282662
      ],
      "path_match": true
    }
  ]
}