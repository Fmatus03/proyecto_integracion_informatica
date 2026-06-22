from __future__ import annotations

from backend.app.services.nodeodm_client import ATTEMPTS, options_for_attempt
from backend.app.services.scale_service import ScaleEvidence


def _options(attempt_index: int) -> dict[str, str]:
    return {option["name"]: option["value"] for option in ATTEMPTS[attempt_index].options}


def test_first_nodeodm_attempt_prioritizes_dense_geometry() -> None:
    options = _options(0)

    assert options["feature-quality"] == "ultra"
    assert options["pc-quality"] == "high"
    assert int(options["min-num-features"]) >= 16000
    assert int(options["matcher-neighbors"]) >= 12
    assert options["depthmap-resolution"] == "high"
    assert options["end-with"] == "odm_filterpoints"


def test_nodeodm_fallbacks_do_not_drop_to_low_point_cloud_quality() -> None:
    fallback_options = [_options(1), _options(2)]

    assert [options["pc-quality"] for options in fallback_options] == ["high", "medium"]
    assert [options["feature-quality"] for options in fallback_options] == ["high", "medium"]
    assert [int(options["matcher-neighbors"]) for options in fallback_options] == [10, 8]


def test_nodeodm_options_do_not_enable_scale_without_gcp_or_gps() -> None:
    scale = ScaleEvidence(
        image_count=18,
        images_with_exif=0,
        images_with_gps=0,
        gcp_path=None,
        scale_certified=False,
        reason="missing_gcp_and_gps_exif",
    )
    options = {option["name"]: option["value"] for option in options_for_attempt(ATTEMPTS[0], scale)}

    assert "gcp" not in options
    assert "force-gps" not in options
    assert "use-exif" not in options


def test_nodeodm_options_do_not_pass_local_gcp_path_as_option() -> None:
    scale = ScaleEvidence(
        image_count=18,
        images_with_exif=0,
        images_with_gps=0,
        gcp_path="set_imagenes+guia/gcp_list.txt",
        scale_certified=True,
        reason="gcp_file_available",
    )
    options = {option["name"]: option["value"] for option in options_for_attempt(ATTEMPTS[0], scale)}

    assert "gcp" not in options
    assert "force-gps" not in options
