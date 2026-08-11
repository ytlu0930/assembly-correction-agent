"""Stage-separated, auditable blind localization contracts."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import hypot
from typing import Any

from .schemas import ERROR_TYPES, STATUSES

COMPARISON_RESULTS = ("present_in_both", "current_only", "uncertain")
LOCALIZATION_STATUSES = ("verified", "not_verified")


def _bbox(value: Any) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4 or any(type(item) is not int for item in value):
        raise ValueError("candidate bbox must contain four integers")
    x1, y1, x2, y2 = value
    if not (0 <= x1 < x2 <= 1000 and 0 <= y1 < y2 <= 1000):
        raise ValueError("candidate bbox must be positive-area normalized 0..1000 xyxy")
    return x1, y1, x2, y2


def _point(value: Any) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2 or any(type(item) is not int for item in value):
        raise ValueError("candidate point must contain two integers")
    if any(item < 0 or item > 1000 for item in value):
        raise ValueError("candidate point must be normalized within 0..1000")
    return value[0], value[1]


@dataclass(frozen=True)
class StageAAnalysis:
    status: str
    error_type: str
    target_part_descriptor: str | None
    confidence: float
    structural_evidence: str

    @classmethod
    def from_dict(cls, value: dict[str, Any], allowed: set[str]) -> "StageAAnalysis":
        status, error_type = value.get("status"), value.get("error_type")
        descriptor, confidence = value.get("target_part_descriptor"), value.get("confidence")
        evidence = value.get("structural_evidence")
        if status not in STATUSES or error_type not in ERROR_TYPES:
            raise ValueError("Stage A status or error_type is invalid")
        if (status == "correct" and error_type != "none") or (status == "error" and error_type == "none"):
            raise ValueError("Stage A status and error_type conflict")
        if descriptor is not None and descriptor not in allowed:
            raise ValueError("descriptor is not in the candidate vocabulary")
        if type(confidence) not in (int, float) or not 0 <= confidence <= 1:
            raise ValueError("confidence must be within 0..1")
        if not isinstance(evidence, str):
            raise ValueError("structural_evidence must be a string")
        return cls(status, error_type, descriptor, float(confidence), evidence)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocalizationCandidate:
    candidate_id: str
    bbox: tuple[int, int, int, int]
    point: tuple[int, int]
    structural_relation: str
    neighboring_parts: tuple[str, ...]
    comparison_result: str
    confidence: float


@dataclass(frozen=True)
class StageBLocalization:
    target_descriptor: str
    candidates: tuple[LocalizationCandidate, ...]
    selected_candidate_id: str | None
    localization_status: str

    @classmethod
    def from_dict(cls, value: dict[str, Any], expected: str) -> "StageBLocalization":
        if value.get("target_descriptor") != expected or not isinstance(value.get("candidates"), list):
            raise ValueError("Stage B target/candidates are invalid")
        candidates: list[LocalizationCandidate] = []
        ids: set[str] = set()
        for raw in value["candidates"]:
            candidate_id, relation = raw.get("candidate_id"), raw.get("structural_relation")
            neighbors = raw.get("neighboring_parts")
            comparison, confidence = raw.get("comparison_result"), raw.get("confidence")
            if not isinstance(candidate_id, str) or not candidate_id or candidate_id in ids:
                raise ValueError("candidate_id must be non-empty and unique")
            ids.add(candidate_id)
            if not isinstance(relation, str) or not relation:
                raise ValueError("structural_relation must be non-empty")
            if not isinstance(neighbors, list) or any(not isinstance(item, str) for item in neighbors):
                raise ValueError("neighboring_parts must be strings")
            if comparison not in COMPARISON_RESULTS:
                raise ValueError("invalid comparison_result")
            if type(confidence) not in (int, float) or not 0 <= confidence <= 1:
                raise ValueError("candidate confidence must be within 0..1")
            candidates.append(LocalizationCandidate(candidate_id, _bbox(raw.get("bbox")), _point(raw.get("point")), relation, tuple(neighbors), comparison, float(confidence)))
        selected, status = value.get("selected_candidate_id"), value.get("localization_status")
        if status not in LOCALIZATION_STATUSES:
            raise ValueError("invalid localization_status")
        by_id = {item.candidate_id: item for item in candidates}
        if selected is not None and selected not in by_id:
            raise ValueError("selected_candidate_id must reference a returned candidate")
        if status == "verified" and (selected is None or by_id[selected].comparison_result != "current_only"):
            raise ValueError("verified requires a selected current_only candidate")
        if status == "not_verified" and selected is not None:
            raise ValueError("not_verified must not select a candidate")
        return cls(expected, tuple(candidates), selected, status)

    @property
    def selected_candidate(self) -> LocalizationCandidate | None:
        return next((item for item in self.candidates if item.candidate_id == self.selected_candidate_id), None)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


STAGE_A_RESPONSE_SCHEMA = {"type": "object", "required": ["status", "error_type", "target_part_descriptor", "confidence", "structural_evidence"], "properties": {"status": {"type": "string", "enum": list(STATUSES)}, "error_type": {"type": "string", "enum": list(ERROR_TYPES)}, "target_part_descriptor": {"anyOf": [{"type": "string"}, {"type": "null"}]}, "confidence": {"type": "number", "minimum": 0, "maximum": 1}, "structural_evidence": {"type": "string"}}}
STAGE_B_RESPONSE_SCHEMA = {"type": "object", "required": ["target_descriptor", "candidates", "selected_candidate_id", "localization_status"], "properties": {"target_descriptor": {"type": "string"}, "candidates": {"type": "array", "items": {"type": "object", "required": ["candidate_id", "bbox", "point", "structural_relation", "neighboring_parts", "comparison_result", "confidence"], "properties": {"candidate_id": {"type": "string"}, "bbox": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4}, "point": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2}, "structural_relation": {"type": "string"}, "neighboring_parts": {"type": "array", "items": {"type": "string"}}, "comparison_result": {"type": "string", "enum": list(COMPARISON_RESULTS)}, "confidence": {"type": "number", "minimum": 0, "maximum": 1}}}}, "selected_candidate_id": {"anyOf": [{"type": "string"}, {"type": "null"}]}, "localization_status": {"type": "string", "enum": list(LOCALIZATION_STATUSES)}}}


def bbox_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return intersection / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection)


def bbox_center(box: tuple[int, int, int, int]) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def normalized_center_distance(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ca, cb = bbox_center(a), bbox_center(b)
    return hypot(ca[0] - cb[0], ca[1] - cb[1]) / hypot(1000, 1000)


def evaluate_localization(predicted, ground_truth) -> dict[str, Any]:
    if ground_truth is None:
        return {"localization_correct": None, "evaluation_status": "unevaluated", "iou": None, "normalized_center_distance": None}
    if predicted is None:
        return {"localization_correct": False, "evaluation_status": "evaluated", "iou": 0.0, "normalized_center_distance": None}
    iou = bbox_iou(predicted, ground_truth)
    return {"localization_correct": iou >= 0.5, "evaluation_status": "evaluated", "iou": iou, "normalized_center_distance": normalized_center_distance(predicted, ground_truth)}
