"""Build a deterministic part catalog from Dataset Manifest records."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "1.0"


def load_manifest(path: str | Path) -> list[dict[str, Any]]:
    """Load JSON Lines records from a Dataset Manifest."""
    manifest_path = Path(path)
    return [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _display_name(descriptor: str) -> str:
    """Convert a dataset-local descriptor into a stable, readable label."""
    words: list[str] = []
    for token in descriptor.split("_"):
        words.extend(re.findall(r"[A-Z]+|\d+", token))
    return " ".join(word.title() if word.isalpha() else word for word in words)


def build_part_catalog(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Group part-image records by descriptor and return a validated catalog."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_record_ids: set[str] = set()
    seen_paths: set[str] = set()

    for record in records:
        if record.get("source_kind") != "part_image":
            continue
        descriptor = record.get("part_descriptor")
        record_id = record.get("record_id")
        source_path = record.get("source_path")
        if not isinstance(descriptor, str) or not descriptor:
            raise ValueError("part image record is missing part_descriptor")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError(f"part image for {descriptor} is missing record_id")
        if not isinstance(source_path, str) or not source_path:
            raise ValueError(f"part image for {descriptor} is missing source_path")
        if record_id in seen_record_ids:
            raise ValueError(f"duplicate part-image record_id: {record_id}")
        if source_path in seen_paths:
            raise ValueError(f"duplicate part-image source_path: {source_path}")
        seen_record_ids.add(record_id)
        seen_paths.add(source_path)
        grouped[descriptor].append(record)

    parts: list[dict[str, Any]] = []
    for descriptor in sorted(grouped):
        references = sorted(grouped[descriptor], key=lambda item: (item["source_path"], item["record_id"]))
        parts.append(
            {
                "part_id": f"PART_{descriptor}",
                "descriptor": descriptor,
                "display_name": _display_name(descriptor),
                "reference_image_record_ids": [item["record_id"] for item in references],
                "reference_image_paths": [item["source_path"] for item in references],
                "reference_image_count": len(references),
                "quantity": None,
                "source": "dataset_local",
                "is_manufacturer_identifier": False,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "part_count": len(parts),
        "reference_image_count": len(seen_record_ids),
        "parts": parts,
    }


def write_part_catalog(
    repository_root: str | Path,
    manifest_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Generate ``data/part_catalog.json`` from the existing manifest."""
    root = Path(repository_root).resolve()
    manifest = Path(manifest_path) if manifest_path else root / "data/dataset_manifest.jsonl"
    output = Path(output_path) if output_path else root / "data/part_catalog.json"
    catalog = build_part_catalog(load_manifest(manifest))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository_root", nargs="?", default=".")
    args = parser.parse_args()
    print(json.dumps(write_part_catalog(args.repository_root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
