"""Build deterministic image and case manifests plus a validation report."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .case_grouper import group_cases
from .filename_parser import parse_source_path


def _record_id(source_path: str) -> str:
    return "record_" + hashlib.sha256(source_path.encode("utf-8")).hexdigest()[:20]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_dataset(repository_root: str | Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    root = Path(repository_root).resolve()
    raw_root = root / "raw_data"
    paths = sorted((path for path in raw_root.rglob("*") if path.is_file()), key=lambda p: p.relative_to(root).as_posix())
    records: list[dict[str, Any]] = []
    for path in paths:
        source_path = path.relative_to(root).as_posix()
        record = parse_source_path(source_path, tolerant=True)
        record["record_id"] = _record_id(source_path)
        record["file_size_bytes"] = path.stat().st_size
        record["sha256"] = _sha256(path)
        records.append(record)

    cases, collisions = group_cases(records)
    hashes: dict[str, list[str]] = defaultdict(list)
    for record in records:
        hashes[record["sha256"]].append(record["record_id"])
    duplicate_hashes = [
        {"sha256": digest, "record_ids": sorted(ids)}
        for digest, ids in sorted(hashes.items()) if len(ids) > 1
    ]
    cross_view_cases = [case["case_key"] for case in cases if "duplicate_content_across_views" in case["data_quality_flags"]]
    assembly = [record for record in records if record["source_kind"] == "assembly_image"]
    status_counts = Counter(record["parse_status"] for record in records)
    view_counts = Counter(record["view"] for record in assembly if record["view"])
    model_steps: dict[str, set[str]] = defaultdict(set)
    for record in assembly:
        if record["model_id"] and record["step_id"]:
            model_steps[record["model_id"]].add(record["step_id"])
    report = {
        "schema_version": "1.0",
        "total_files_scanned": len(records),
        "assembly_images": len(assembly),
        "part_images": sum(record["source_kind"] == "part_image" for record in records),
        "valid_records": status_counts["valid"],
        "warning_records": status_counts["warning"],
        "invalid_records": status_counts["invalid"],
        "models": sorted(model_steps),
        "steps": {model: sorted(steps) for model, steps in sorted(model_steps.items())},
        "labels": sorted({record["normalized_label"] for record in assembly if record["normalized_label"]}),
        "case_count": len(cases),
        "view_distribution": dict(sorted(view_counts.items())),
        "incomplete_cases": [case["case_key"] for case in cases if case["missing_views"]],
        "semantic_key_collisions": collisions,
        "duplicate_hashes": duplicate_hashes,
        "cross_view_duplicate_content_cases": cross_view_cases,
        "malformed_filename_count": sum("malformed_filename" in record["anomalies"] for record in records),
        "malformed_extension_count": sum("malformed_extension" in record["anomalies"] for record in records),
        "directory_filename_mismatches": [record["record_id"] for record in records if "directory_filename_mismatch" in record["anomalies"]],
    }
    return records, cases, report


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    text = "".join(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n" for value in values)
    path.write_text(text, encoding="utf-8")


def write_artifacts(repository_root: str | Path, output_directory: str | Path | None = None) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    target = Path(output_directory) if output_directory else root / "data"
    target.mkdir(parents=True, exist_ok=True)
    records, cases, report = build_dataset(root)
    _write_jsonl(target / "dataset_manifest.jsonl", records)
    _write_jsonl(target / "dataset_case_manifest.jsonl", cases)
    (target / "dataset_audit_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository_root", nargs="?", default=".")
    args = parser.parse_args()
    print(json.dumps(write_artifacts(args.repository_root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
