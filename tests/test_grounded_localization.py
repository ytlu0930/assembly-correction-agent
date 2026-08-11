from __future__ import annotations

import pytest

from assembly_agent.localization import (
    GroundedLocalization,
    GroundingCandidate,
    GroundingResult,
    build_grounding_query,
)


def candidate(candidate_id: str, bbox=(10, 20, 40, 60), score=0.5) -> GroundingCandidate:
    return GroundingCandidate(candidate_id, bbox, score, "grounding_dino:test")


def grounding(*candidates: GroundingCandidate) -> GroundingResult:
    return GroundingResult("red short pin.", 0.18, (100, 100), tuple(candidates), "grounding_dino:test")


def assessment(candidate_id: str, result: str) -> dict:
    return {"candidate_id": candidate_id, "comparison_result": result, "confidence": 0.8, "evidence": "structural comparison"}


def payload(assessments, selected=None, status="not_verified") -> dict:
    return {"target_descriptor": "PIN_RED_SHORT", "assessments": assessments,
            "selected_candidate_id": selected, "localization_status": status}


def test_grounding_schema_coordinates_ids_and_preservation() -> None:
    result = grounding(candidate("grounded_001"), candidate("grounded_002", (40, 30, 90, 80)))
    assert [item.candidate_id for item in result.candidates] == ["grounded_001", "grounded_002"]
    with pytest.raises(ValueError, match="unique"):
        grounding(candidate("same"), candidate("same", (40, 30, 90, 80)))
    with pytest.raises(ValueError, match="bbox"):
        grounding(candidate("outside", (10, 10, 101, 20)))


def test_selection_is_constrained_to_grounded_candidates_and_all_are_compared() -> None:
    result = grounding(candidate("grounded_001"), candidate("grounded_002", (40, 30, 90, 80)))
    with pytest.raises(ValueError, match="every grounded"):
        GroundedLocalization.from_dict(payload([assessment("grounded_001", "uncertain")]), "PIN_RED_SHORT", result)
    with pytest.raises(ValueError, match="grounded candidate"):
        GroundedLocalization.from_dict(payload([
            assessment("grounded_001", "uncertain"), assessment("invented", "current_only")
        ], "invented", "verified"), "PIN_RED_SHORT", result)


def test_verification_requires_grounded_current_only_and_valid_enum() -> None:
    result = grounding(candidate("grounded_001"))
    with pytest.raises(ValueError, match="current_only"):
        GroundedLocalization.from_dict(payload([assessment("grounded_001", "present_in_both")], "grounded_001", "verified"), "PIN_RED_SHORT", result)
    with pytest.raises(ValueError, match="comparison"):
        GroundedLocalization.from_dict(payload([assessment("grounded_001", "wrong")]), "PIN_RED_SHORT", result)


def test_explicit_detection_selection_and_verification_failures() -> None:
    empty = GroundingResult("pin.", 0.18, (100, 100), (), "grounding_dino:test")
    detected = grounding(candidate("grounded_001"))
    assert GroundedLocalization.from_dict(payload([]), "PIN_RED_SHORT", empty).failure_type == "candidate_detection_failure"
    assert GroundedLocalization.from_dict(payload([assessment("grounded_001", "current_only")]), "PIN_RED_SHORT", detected).failure_type == "candidate_selection_failure"
    assert GroundedLocalization.from_dict(payload([assessment("grounded_001", "uncertain")]), "PIN_RED_SHORT", detected).failure_type == "verification_failure"


def test_grounding_query_is_object_only_and_contains_no_blind_hint() -> None:
    query = build_grounding_query("PIN_RED_SHORT", "Pin Red Short")
    assert query == "pin red short. pin red short."
    lowered = query.lower()
    for forbidden in ("extra", "wrong", "remove", "location", "ground truth", "left", "right"):
        assert forbidden not in lowered
