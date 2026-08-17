from assembly_agent.experiments.instance_matching import diagnose, validate_inventory


def instance(instance_id, anchor):
    return {"instance_id": instance_id, "descriptor": "EYE_BALL", "attachment_anchor": anchor,
            "neighboring_parts": [], "supporting_views": ["front", "top"], "confidence": 0.9}


def test_simultaneous_extra_and_missing_same_part_type() -> None:
    current = {"instances": [instance(f"current_eye_{i}", anchor) for i, anchor in enumerate(
        ["shared_1", "shared_2", "shared_3", "tail_left", "tail_right"], 1)]}
    reference = {"instances": [instance(f"reference_eye_{i}", anchor) for i, anchor in enumerate(
        ["shared_1", "shared_2", "shared_3", "triangle_center"], 1)]}
    matching = {"matches": [{"current_id": f"current_eye_{i}", "reference_id": f"reference_eye_{i}",
                              "status": "matched", "confidence": 1, "reason": "same anchor"} for i in range(1, 4)],
                "unmatched_current_ids": ["current_eye_4", "current_eye_5"],
                "unmatched_reference_ids": ["reference_eye_4"]}
    result = diagnose(current, reference, matching)
    assert result["error_type"] == "composite_error"
    assert [claim["error_type"] for claim in result["claims"]] == ["extra_part", "extra_part", "missing_part"]


def test_inventory_ids_are_unique_and_role_scoped() -> None:
    validate_inventory({"instances": [instance("current_eye_1", "a")]}, "current")
