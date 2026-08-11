"""Schemas and failure taxonomy for verification constrained to grounded boxes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .grounding import GroundingResult

COMPARISON_RESULTS = ("present_in_both", "current_only", "uncertain")
FAILURES = ("candidate_detection_failure", "candidate_selection_failure", "verification_failure")

GROUNDED_MATCHING_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["target_descriptor", "assessments", "selected_candidate_id", "localization_status"],
    "properties": {
        "target_descriptor": {"type": "string"},
        "assessments": {"type": "array", "items": {"type": "object", "required": [
            "candidate_id", "comparison_result", "confidence", "evidence"], "properties": {
            "candidate_id": {"type": "string"},
            "comparison_result": {"type": "string", "enum": list(COMPARISON_RESULTS)},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence": {"type": "string"},
        }}},
        "selected_candidate_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "localization_status": {"type": "string", "enum": ["verified", "not_verified"]},
    },
}

@dataclass(frozen=True)
class CandidateAssessment:
    candidate_id: str
    comparison_result: str
    confidence: float
    evidence: str


@dataclass(frozen=True)
class GroundedLocalization:
    target_descriptor: str
    assessments: tuple[CandidateAssessment, ...]
    selected_candidate_id: str | None
    localization_status: str
    failure_type: str | None

    @classmethod
    def from_dict(cls, value: dict[str, Any], expected: str, grounding: GroundingResult) -> "GroundedLocalization":
        if value.get("target_descriptor") != expected or not isinstance(value.get("assessments"), list):
            raise ValueError("matching target/assessments are invalid")
        grounded_ids = {item.candidate_id for item in grounding.candidates}
        seen, assessments = set(), []
        for raw in value["assessments"]:
            candidate_id = raw.get("candidate_id")
            comparison, confidence, evidence = raw.get("comparison_result"), raw.get("confidence"), raw.get("evidence")
            if candidate_id not in grounded_ids or candidate_id in seen:
                raise ValueError("every assessment must reference one unique grounded candidate")
            if comparison not in COMPARISON_RESULTS or type(confidence) not in (int, float) or not 0 <= confidence <= 1:
                raise ValueError("invalid candidate comparison")
            if not isinstance(evidence, str) or not evidence:
                raise ValueError("candidate evidence must be non-empty")
            seen.add(candidate_id)
            assessments.append(CandidateAssessment(candidate_id, comparison, float(confidence), evidence))
        if seen != grounded_ids:
            raise ValueError("matching must preserve and assess every grounded candidate")
        selected, status = value.get("selected_candidate_id"), value.get("localization_status")
        if selected is not None and selected not in grounded_ids:
            raise ValueError("selection cannot invent a non-grounded candidate or bbox")
        by_id = {item.candidate_id: item for item in assessments}
        if status == "verified" and (selected is None or by_id[selected].comparison_result != "current_only"):
            raise ValueError("verified requires a grounded current_only candidate")
        if status not in ("verified", "not_verified") or (status == "not_verified" and selected is not None):
            raise ValueError("invalid grounded localization status")
        failure = classify_localization(grounding, status, selected, assessments)
        return cls(expected, tuple(assessments), selected, status, failure)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_localization(grounding, status, selected, assessments) -> str | None:
    if not grounding.candidates:
        return "candidate_detection_failure"
    if selected is None and any(item.comparison_result == "current_only" for item in assessments):
        return "candidate_selection_failure"
    if status != "verified":
        return "verification_failure"
    return None
