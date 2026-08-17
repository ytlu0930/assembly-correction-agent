"""Instance-level inventory, matching validation, and deterministic diagnosis."""

from __future__ import annotations

from typing import Any

from assembly_agent.reference import CANONICAL_VIEWS


def inventory_schema(descriptors: tuple[str, ...]) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": ["instances"], "properties": {
        "instances": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "required": ["instance_id", "descriptor", "attachment_anchor", "neighboring_parts", "supporting_views", "confidence"],
            "properties": {
                "instance_id": {"type": "string"},
                "descriptor": {"type": "string", "enum": list(descriptors)},
                "attachment_anchor": {"type": "string"},
                "neighboring_parts": {"type": "array", "items": {"type": "string", "enum": list(descriptors)}},
                "supporting_views": {"type": "array", "items": {"type": "string", "enum": list(CANONICAL_VIEWS)}},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            }}},
    }}


def matching_schema() -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False,
        "required": ["matches", "unmatched_current_ids", "unmatched_reference_ids"], "properties": {
            "matches": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                "required": ["current_id", "reference_id", "status", "confidence", "reason"], "properties": {
                    "current_id": {"type": "string"}, "reference_id": {"type": "string"},
                    "status": {"type": "string", "enum": ["matched", "identity_mismatch", "attachment_mismatch"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}, "reason": {"type": "string"}}}},
            "unmatched_current_ids": {"type": "array", "items": {"type": "string"}},
            "unmatched_reference_ids": {"type": "array", "items": {"type": "string"}},
        }}


def validate_inventory(payload: dict[str, Any], role: str) -> None:
    instances = payload.get("instances")
    if not isinstance(instances, list):
        raise ValueError(f"{role} inventory must contain instances")
    ids = [item.get("instance_id") for item in instances if isinstance(item, dict)]
    if len(ids) != len(instances) or len(ids) != len(set(ids)) or any(not value for value in ids):
        raise ValueError(f"{role} inventory instance IDs must be non-empty and unique")
    prefix = f"{role}_"
    if any(not value.startswith(prefix) for value in ids):
        raise ValueError(f"{role} inventory IDs must start with {prefix}")


def validate_matching(current: dict[str, Any], reference: dict[str, Any], matching: dict[str, Any]) -> None:
    current_ids = {item["instance_id"] for item in current["instances"]}
    reference_ids = {item["instance_id"] for item in reference["instances"]}
    matches = matching.get("matches", [])
    paired_current = [item.get("current_id") for item in matches]
    paired_reference = [item.get("reference_id") for item in matches]
    unmatched_current = matching.get("unmatched_current_ids", [])
    unmatched_reference = matching.get("unmatched_reference_ids", [])
    if len(paired_current) != len(set(paired_current)) or len(paired_reference) != len(set(paired_reference)):
        raise ValueError("instance matching must be one-to-one")
    if set(paired_current) | set(unmatched_current) != current_ids or set(paired_current) & set(unmatched_current):
        raise ValueError("every Current instance must be covered exactly once")
    if set(paired_reference) | set(unmatched_reference) != reference_ids or set(paired_reference) & set(unmatched_reference):
        raise ValueError("every Reference instance must be covered exactly once")


def diagnose(current: dict[str, Any], reference: dict[str, Any], matching: dict[str, Any]) -> dict[str, Any]:
    validate_matching(current, reference, matching)
    current_by_id = {item["instance_id"]: item for item in current["instances"]}
    reference_by_id = {item["instance_id"]: item for item in reference["instances"]}
    claims = []
    for instance_id in matching["unmatched_current_ids"]:
        item = current_by_id[instance_id]
        claims.append({"error_type": "extra_part", "descriptor": item["descriptor"], "current_instance_id": instance_id,
                       "reference_instance_id": None, "attachment_anchor": item["attachment_anchor"]})
    for instance_id in matching["unmatched_reference_ids"]:
        item = reference_by_id[instance_id]
        claims.append({"error_type": "missing_part", "descriptor": item["descriptor"], "current_instance_id": None,
                       "reference_instance_id": instance_id, "attachment_anchor": item["attachment_anchor"]})
    for pair in matching["matches"]:
        if pair["status"] == "identity_mismatch":
            current_item, reference_item = current_by_id[pair["current_id"]], reference_by_id[pair["reference_id"]]
            claims.append({"error_type": "wrong_part", "descriptor": current_item["descriptor"],
                           "expected_descriptor": reference_item["descriptor"], "current_instance_id": pair["current_id"],
                           "reference_instance_id": pair["reference_id"], "attachment_anchor": reference_item["attachment_anchor"]})
        elif pair["status"] == "attachment_mismatch":
            item = current_by_id[pair["current_id"]]
            claims.append({"error_type": "position_error", "descriptor": item["descriptor"],
                           "current_instance_id": pair["current_id"], "reference_instance_id": pair["reference_id"],
                           "attachment_anchor": item["attachment_anchor"]})
    error_types = {claim["error_type"] for claim in claims}
    error_type = "none" if not claims else next(iter(error_types)) if len(claims) == 1 else "composite_error"
    return {"status": "correct" if not claims else "error", "error_type": error_type, "claims": claims,
            "claim_count": len(claims), "classification_source": "deterministic_instance_matching"}
