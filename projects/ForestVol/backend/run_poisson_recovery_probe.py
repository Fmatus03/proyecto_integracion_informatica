from __future__ import annotations

import json
from pathlib import Path

from backend.app.services.mesh_service import generate_preliminary_volumetry


SESSION_ID = "b6b04af0-122f-4fcc-af8a-cc553ca5e28d"
point_cloud = Path("/app/data/processed") / SESSION_ID / "point_cloud.ply"
output_dir = Path("/app/data/processed") / SESSION_ID / "poisson_recovery_probe"
result = generate_preliminary_volumetry(
    point_cloud,
    output_dir,
    scale_px_per_cm=0.9865,
    point_cloud_scale_m_per_unit=1.0,
    scale_source="aruco_gcp_generated",
    ground_truth_volume_m3=119.74,
    mesh_name="poisson_recovery_mesh",
)
payload = {
    "mesh_ply_path": result.mesh_ply_path,
    "volume_m3": result.volume_m3,
    "error_percentage": result.error_percentage,
    "vertex_count": result.vertex_count,
    "triangle_count": result.triangle_count,
    "mesh_watertight": result.mesh_watertight,
    "repair_cycles": result.repair_cycles,
    "bounding_box_m": result.bounding_box_m,
    "mesh_recovery": result.point_cloud_quality.get("mesh_recovery"),
}
(output_dir / "probe-result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(json.dumps(payload, indent=2))
