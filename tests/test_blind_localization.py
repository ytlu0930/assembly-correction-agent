from __future__ import annotations

import pytest

from assembly_agent.correction import plan_verified_localization_correction
from assembly_agent.vision.gemini import GeminiRequest, GeminiVisionAdapter, InlineImage
from assembly_agent.vision.localization import (
    StageAAnalysis, StageBLocalization, bbox_center, bbox_iou,
    evaluate_localization, normalized_center_distance,
)


def stage_a() -> StageAAnalysis:
    return StageAAnalysis.from_dict({"status": "error", "error_type": "extra_part", "target_part_descriptor": "TEST_PART", "confidence": 0.9, "structural_evidence": "Structural mismatch."}, {"TEST_PART"})


def candidate(candidate_id: str, comparison: str, bbox=None) -> dict:
    return {"candidate_id": candidate_id, "bbox": bbox or [100, 100, 200, 200], "point": [150, 150], "structural_relation": "attached to a central connector", "neighboring_parts": ["CONNECTOR"], "comparison_result": comparison, "confidence": 0.8}


def stage_b(status="verified", selected="candidate_02") -> StageBLocalization:
    return StageBLocalization.from_dict({"target_descriptor": "TEST_PART", "candidates": [candidate("candidate_01", "present_in_both"), candidate("candidate_02", "current_only")], "selected_candidate_id": selected, "localization_status": status}, "TEST_PART")


def test_stage_separation_and_multiple_instances() -> None:
    assert "bbox" not in stage_a().to_dict()
    assert len(stage_b().candidates) == 2


def test_selected_candidate_must_exist() -> None:
    with pytest.raises(ValueError, match="must reference"):
        stage_b(selected="candidate_99")


@pytest.mark.parametrize("bbox", [[10, 10, 10, 20], [-1, 0, 10, 10], [0, 0, 1001, 10]])
def test_malformed_candidate_bbox_is_rejected(bbox) -> None:
    value = {"target_descriptor": "TEST_PART", "candidates": [candidate("candidate_01", "current_only", bbox)], "selected_candidate_id": "candidate_01", "localization_status": "verified"}
    with pytest.raises(ValueError, match="bbox"):
        StageBLocalization.from_dict(value, "TEST_PART")


def test_comparison_enum_and_verification_gate() -> None:
    value = {"target_descriptor": "TEST_PART", "candidates": [candidate("candidate_01", "invented")], "selected_candidate_id": None, "localization_status": "not_verified"}
    with pytest.raises(ValueError, match="comparison_result"):
        StageBLocalization.from_dict(value, "TEST_PART")
    assert plan_verified_localization_correction(stage_a(), stage_b()).action == "REMOVE"
    assert plan_verified_localization_correction(stage_a(), stage_b("not_verified", None)) is None


def test_verified_requires_current_only_candidate() -> None:
    with pytest.raises(ValueError, match="current_only"):
        StageBLocalization.from_dict({"target_descriptor": "TEST_PART", "candidates": [candidate("candidate_01", "present_in_both")], "selected_candidate_id": "candidate_01", "localization_status": "verified"}, "TEST_PART")


def test_metrics_and_missing_gt() -> None:
    assert bbox_iou((0, 0, 100, 100), (50, 50, 150, 150)) == pytest.approx(2500 / 17500)
    assert bbox_center((0, 100, 200, 300)) == (100, 200)
    assert normalized_center_distance((0, 0, 100, 100), (100, 100, 200, 200)) == pytest.approx(0.1)
    result = evaluate_localization((0, 0, 100, 100), None)
    assert result["localization_correct"] is None and result["evaluation_status"] == "unevaluated"

def test_stage_b_request_has_no_ground_truth_or_case_hint(monkeypatch) -> None:
    image = InlineImage("neutral_current", "image/jpeg", b"image")
    request = GeminiRequest("semantic prompt", image, image, (
        InlineImage("part_reference_0001_TEST_PART", "image/jpeg", b"part"),
    ), ("TEST_PART",), {"current_image_id": "neutral_current"})
    captured = {}

    def fake_generate(contents, schema):
        captured["prompt"] = contents[0]
        return {"target_descriptor": "TEST_PART", "candidates": [], "selected_candidate_id": None, "localization_status": "not_verified"}

    adapter = GeminiVisionAdapter("test-key", "test-model")
    monkeypatch.setattr(adapter, "_generate_json", fake_generate)
    adapter.localize(request, "TEST_PART")
    prompt = captured["prompt"].lower()
    assert "raw_data" not in prompt and "extrapart" not in prompt
    assert "pin_red_short" not in prompt and "left hole" not in prompt
    assert "known target" not in prompt and "ground truth" not in prompt
