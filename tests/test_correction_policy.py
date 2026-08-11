from assembly_agent.correction import plan_demo01_correction
from assembly_agent.vision.schemas import VisionAnalysis


def analysis(status="error", error_type="extra_part"):
    return VisionAnalysis.from_dict({
        "status": status, "error_type": error_type,
        "actual_part": {"descriptor": "PIN_RED_SHORT", "description": None},
        "location": {"coordinate_space": "normalized_0_1000_xyxy", "region": None, "bbox": [1, 1, 2, 2], "point": None},
        "confidence": 0.8, "evidence_summary": "evidence",
    }, {"PIN_RED_SHORT"})


def test_extra_part_maps_to_remove() -> None:
    assert plan_demo01_correction(analysis()).action == "REMOVE"


def test_non_extra_prediction_does_not_fabricate_remove() -> None:
    assert plan_demo01_correction(analysis(error_type="unknown_error")) is None

