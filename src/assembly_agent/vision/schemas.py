"""Validated structured contracts for vision analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

STATUSES = ("correct", "error", "uncertain")
ERROR_TYPES = ("extra_part", "missing_part", "wrong_part", "position_error", "unknown_error", "none")
COORDINATE_SPACE = "normalized_0_1000_xyxy"


def _optional_text(value: Any, field: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{field} must be a string or null")
    return value


def _coordinate_pair(value: Any, field: str) -> tuple[int, int] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 2 or any(type(item) is not int for item in value):
        raise ValueError(f"{field} must contain two integers")
    if any(item < 0 or item > 1000 for item in value):
        raise ValueError(f"{field} coordinates must be within 0..1000")
    return value[0], value[1]


def _bbox(value: Any) -> tuple[int, int, int, int] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 4 or any(type(item) is not int for item in value):
        raise ValueError("location.bbox must contain four integers")
    x_min, y_min, x_max, y_max = value
    if any(item < 0 or item > 1000 for item in value):
        raise ValueError("location.bbox coordinates must be within 0..1000")
    if x_min >= x_max or y_min >= y_max:
        raise ValueError("location.bbox must have positive area in xyxy order")
    return x_min, y_min, x_max, y_max


@dataclass(frozen=True)
class ActualPart:
    descriptor: str | None
    description: str | None


@dataclass(frozen=True)
class Location:
    coordinate_space: str
    region: str | None
    bbox: tuple[int, int, int, int] | None
    point: tuple[int, int] | None


@dataclass(frozen=True)
class VisionAnalysis:
    status: str
    error_type: str
    actual_part: ActualPart
    location: Location
    confidence: float
    evidence_summary: str

    @classmethod
    def from_dict(cls, value: dict[str, Any], allowed_descriptors: set[str]) -> "VisionAnalysis":
        if not isinstance(value, dict):
            raise ValueError("vision response must be an object")
        status = value.get("status")
        error_type = value.get("error_type")
        if status not in STATUSES:
            raise ValueError(f"unsupported status: {status}")
        if error_type not in ERROR_TYPES:
            raise ValueError(f"unsupported error_type: {error_type}")
        if status == "correct" and error_type != "none":
            raise ValueError("correct status requires error_type none")
        if status == "error" and error_type == "none":
            raise ValueError("error status cannot use error_type none")
        part = value.get("actual_part")
        location = value.get("location")
        if not isinstance(part, dict) or not isinstance(location, dict):
            raise ValueError("actual_part and location must be objects")
        descriptor = _optional_text(part.get("descriptor"), "actual_part.descriptor")
        if descriptor is not None and descriptor not in allowed_descriptors:
            raise ValueError(f"descriptor is not in the candidate vocabulary: {descriptor}")
        coordinate_space = location.get("coordinate_space")
        if coordinate_space != COORDINATE_SPACE:
            raise ValueError(f"coordinate_space must be {COORDINATE_SPACE}")
        confidence = value.get("confidence")
        if type(confidence) not in (int, float) or not 0 <= confidence <= 1:
            raise ValueError("confidence must be within 0..1")
        evidence = value.get("evidence_summary")
        if not isinstance(evidence, str):
            raise ValueError("evidence_summary must be a string")
        return cls(
            status=status,
            error_type=error_type,
            actual_part=ActualPart(descriptor, _optional_text(part.get("description"), "actual_part.description")),
            location=Location(
                coordinate_space=coordinate_space,
                region=_optional_text(location.get("region"), "location.region"),
                bbox=_bbox(location.get("bbox")),
                point=_coordinate_pair(location.get("point"), "location.point"),
            ),
            confidence=float(confidence),
            evidence_summary=evidence,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


VISION_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "error_type", "actual_part", "location", "confidence", "evidence_summary"],
    "properties": {
        "status": {"type": "string", "enum": list(STATUSES)},
        "error_type": {"type": "string", "enum": list(ERROR_TYPES)},
        "actual_part": {
            "type": "object",
            "additionalProperties": False,
            "required": ["descriptor", "description"],
            "properties": {
                "descriptor": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "description": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            },
        },
        "location": {
            "type": "object",
            "additionalProperties": False,
            "required": ["coordinate_space", "region", "bbox", "point"],
            "properties": {
                "coordinate_space": {"type": "string", "enum": [COORDINATE_SPACE]},
                "region": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "bbox": {
                    "anyOf": [
                        {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 1000}, "minItems": 4, "maxItems": 4},
                        {"type": "null"},
                    ]
                },
                "point": {
                    "anyOf": [
                        {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 1000}, "minItems": 2, "maxItems": 2},
                        {"type": "null"},
                    ]
                },
            },
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence_summary": {"type": "string"},
    },
}

