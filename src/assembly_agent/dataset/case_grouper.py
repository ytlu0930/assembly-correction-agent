"""Group assembly manifest records into deterministic multi-view cases."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

EXPECTED_VIEWS = ("back", "bottom", "front", "left", "right", "top")


def semantic_image_key(record: dict[str, Any]) -> str:
    return "|".join((record["case_key"], record["view"], record["capture_id"]))


def group_cases(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record["source_kind"] == "assembly_image" and record["parse_status"] != "invalid":
            grouped[record["case_key"]].append(record)

    cases: list[dict[str, Any]] = []
    collisions: list[dict[str, Any]] = []
    for case_key, case_records in sorted(grouped.items()):
        case_records.sort(key=lambda item: (item["view"], item["capture_id"], item["source_path"]))
        by_semantic: dict[str, list[str]] = defaultdict(list)
        by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
        captures: dict[str, list[str]] = defaultdict(list)
        flags: set[str] = set()
        for record in case_records:
            by_semantic[semantic_image_key(record)].append(record["record_id"])
            by_hash[record["sha256"]].append(record)
            captures[record["view"]].append(record["capture_id"])
            if record["anomalies"]:
                flags.update(record["anomalies"])
        for key, record_ids in sorted(by_semantic.items()):
            if len(record_ids) > 1:
                flags.add("semantic_key_collision")
                collisions.append({"semantic_image_key": key, "record_ids": sorted(record_ids)})
        for same_content in by_hash.values():
            if len({record["view"] for record in same_content}) > 1:
                flags.add("duplicate_content_across_views")
        available = sorted(captures)
        missing = sorted(set(EXPECTED_VIEWS) - set(available))
        if missing:
            flags.add("incomplete_views")
        model_id, step_id, normalized_label, case_id = case_key.split("|")
        cases.append({
            "schema_version": "1.0",
            "case_key": case_key,
            "model_id": model_id,
            "step_id": step_id,
            "normalized_label": normalized_label,
            "case_id": case_id,
            "available_views": available,
            "missing_views": missing,
            "captures_per_view": {view: sorted(ids) for view, ids in sorted(captures.items())},
            "source_record_ids": [record["record_id"] for record in case_records],
            "anomaly_count": sum(len(record["anomalies"]) for record in case_records),
            "data_quality_flags": sorted(flags),
        })
    return cases, collisions
