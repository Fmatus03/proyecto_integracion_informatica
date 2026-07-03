from __future__ import annotations

from backend.app.api.routes.reconstruction import _metric_point_cloud_scale_from_session


def test_metric_point_cloud_scale_requires_reconstructed_aruco_evidence() -> None:
    scale, source = _metric_point_cloud_scale_from_session(
        {
            "scale_evidence": {
                "scale_certified": True,
                "reason": "aruco_gcp_generated",
                "gcp_path": "data/processed/session/gcp_list.txt",
            }
        }
    )

    assert scale is None
    assert source is None


def test_metric_point_cloud_scale_uses_reconstructed_aruco_factor() -> None:
    scale, source = _metric_point_cloud_scale_from_session(
        {
            "scale_evidence": {
                "scale_certified": True,
                "reason": "reconstructed_aruco_3d",
                "reconstructed_aruco_scale": {
                    "scale_factor_m_per_unit": 0.502077,
                },
            }
        }
    )

    assert scale == 0.502077
    assert source == "reconstructed_aruco_3d"
