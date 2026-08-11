from __future__ import annotations

import json
from pathlib import Path

import pytest

from assembly_agent.parts.catalog import build_part_catalog, load_manifest, write_part_catalog


def part_record(descriptor: str, capture: str, record_id: str) -> dict[str, str]:
    return {
        "source_kind": "part_image",
        "part_descriptor": descriptor,
        "record_id": record_id,
        "source_path": f"raw_data/parts/part_{descriptor}_{capture}.jpg",
    }


def test_catalog_groups_only_part_images_by_dataset_descriptor() -> None:
    records = [
        part_record("PIN_RED_SHORT", "02", "record_b"),
        {"source_kind": "assembly_image", "record_id": "assembly", "part_descriptor": None},
        part_record("PIN_RED_SHORT", "01", "record_a"),
        part_record("EYE_BALL", "01", "record_c"),
    ]
    catalog = build_part_catalog(records)

    assert catalog["part_count"] == 2
    assert catalog["reference_image_count"] == 3
    assert [part["part_id"] for part in catalog["parts"]] == ["PART_EYE_BALL", "PART_PIN_RED_SHORT"]
    pin = catalog["parts"][1]
    assert pin == {
        "part_id": "PART_PIN_RED_SHORT",
        "descriptor": "PIN_RED_SHORT",
        "display_name": "Pin Red Short",
        "reference_image_record_ids": ["record_a", "record_b"],
        "reference_image_paths": [
            "raw_data/parts/part_PIN_RED_SHORT_01.jpg",
            "raw_data/parts/part_PIN_RED_SHORT_02.jpg",
        ],
        "reference_image_count": 2,
        "quantity": None,
        "source": "dataset_local",
        "is_manufacturer_identifier": False,
    }


def test_display_names_separate_numeric_descriptor_components() -> None:
    catalog = build_part_catalog([part_record("BLOCK_GREEN_4HOLE_2PEG", "01", "record_a")])
    assert catalog["parts"][0]["display_name"] == "Block Green 4 Hole 2 Peg"


@pytest.mark.parametrize("duplicate_field", ["record_id", "source_path"])
def test_duplicate_part_image_identity_is_rejected(duplicate_field: str) -> None:
    first = part_record("EYE_BALL", "01", "record_a")
    second = part_record("EYE_BALL", "02", "record_b")
    second[duplicate_field] = first[duplicate_field]
    with pytest.raises(ValueError, match="duplicate part-image"):
        build_part_catalog([first, second])


def test_repository_catalog_covers_manifest_parts_exactly() -> None:
    root = Path(__file__).parents[1]
    records = load_manifest(root / "data/dataset_manifest.jsonl")
    catalog = json.loads((root / "data/part_catalog.json").read_text(encoding="utf-8"))
    manifest_parts = [record for record in records if record["source_kind"] == "part_image"]

    assert len(manifest_parts) == 46
    assert catalog == build_part_catalog(records)
    assert catalog["part_count"] == 15
    assert catalog["reference_image_count"] == 46
    assert sum(part["reference_image_count"] for part in catalog["parts"]) == 46
    assert len({part["descriptor"] for part in catalog["parts"]}) == catalog["part_count"]
    assert len({part["part_id"] for part in catalog["parts"]}) == catalog["part_count"]
    assert all(part["quantity"] is None for part in catalog["parts"])
    assert all(part["source"] == "dataset_local" for part in catalog["parts"])
    assert all(not part["is_manufacturer_identifier"] for part in catalog["parts"])

    catalog_ids = [record_id for part in catalog["parts"] for record_id in part["reference_image_record_ids"]]
    catalog_paths = [path for part in catalog["parts"] for path in part["reference_image_paths"]]
    assert sorted(catalog_ids) == sorted(record["record_id"] for record in manifest_parts)
    assert sorted(catalog_paths) == sorted(record["source_path"] for record in manifest_parts)
    assert len(catalog_ids) == len(set(catalog_ids))
    assert len(catalog_paths) == len(set(catalog_paths))
    assert not any("/model03/" in path or "/model08/" in path for path in catalog_paths)


def test_part_catalog_artifact_is_deterministic(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    output = tmp_path / "part_catalog.json"
    write_part_catalog(root, output_path=output)
    first = output.read_bytes()
    write_part_catalog(root, output_path=output)
    assert output.read_bytes() == first
