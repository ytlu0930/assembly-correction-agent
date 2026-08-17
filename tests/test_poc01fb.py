from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from assembly_agent.experiments import poc01fb


@pytest.fixture
def root() -> Path:
    return Path(__file__).parents[1]


def prediction(descriptor: str = "PIN_RED_SHORT") -> dict:
    return {
        "part_inventory": [],
        "status": "error",
        "error_type": "extra_part",
        "suspected_parts": [{
            "descriptor": descriptor,
            "description": "a correspondence-supported difference",
            "comparison_result": "current_only",
            "supporting_views": ["front"],
            "confidence": 0.9,
        }],
        "structural_difference": "one unmatched physical instance",
        "supporting_views": ["front"],
        "conflicting_views": [],
        "confidence": 0.9,
    }


def with_inventory(payload: dict, descriptors: tuple[str, ...]) -> dict:
    return {**payload, "part_inventory": [{"descriptor": item} for item in descriptors]}


def test_complete_catalog_is_neutral_and_request_is_independently_blind(root: Path) -> None:
    prompt, images, descriptors, audit = poc01fb.build_request(root)
    catalog = json.loads((root / "data/part_catalog.json").read_text())
    expected = tuple(part["descriptor"] for part in catalog["parts"])
    assert descriptors == expected
    assert audit["catalog_descriptor_count"] == len(expected) == 15
    assert audit["catalog_descriptors"] == list(expected)
    assert all(prompt.count(descriptor) == 1 for descriptor in expected)
    assert [image.record_id for image in images] == [
        item["record_id"] for key in ("current_images", "reference_images")
        for item in json.loads((root / "outputs/poc01f/request_audit.json").read_text())[key]
    ]
    forbidden = (
        "extrapart", "expected extra_part", "expected pin_red_short", "raw_data", ".jpg",
        "red peg", "orange flared piece", "poc-01f-a", "previous prediction",
    )
    assert all(term not in prompt.lower() for term in forbidden)
    assert audit["reference_capture_selection_rule"] == "lowest_capture_id_then_source_path_then_record_id"
    assert audit["ground_truth_exposed"] is False
    assert audit["previous_prediction_exposed"] is False
    assert "complete instance count" in prompt
    assert "image-left and image-right are camera-relative" in prompt.lower()
    assert "do not stop after detecting the first error class" in prompt.lower()


def test_schema_has_no_localization_and_rejects_non_catalog_descriptor(root: Path) -> None:
    descriptors = poc01fb.load_catalog_descriptors(root)
    serialized = json.dumps(poc01fb.diagnosis_schema(descriptors)).lower()
    assert all(term not in serialized for term in ("bbox", "point", "coordinate", "polygon", "segmentation", "pixel"))
    valid = with_inventory(prediction(), descriptors)
    poc01fb.validate_prediction(valid, descriptors)
    with pytest.raises(ValueError, match="outside complete Part Catalog"):
        invalid = with_inventory(prediction("red peg"), descriptors)
        poc01fb.validate_prediction(invalid, descriptors)


def test_inventory_is_complete_and_ordered(root: Path) -> None:
    descriptors = poc01fb.load_catalog_descriptors(root)
    with pytest.raises(ValueError, match="every catalog descriptor"):
        poc01fb.validate_prediction(prediction(), descriptors)


def test_persistence_order_and_baseline_preservation(tmp_path: Path, root: Path, monkeypatch) -> None:
    baseline_files = tuple((root / "outputs/poc01f").glob("*.json"))
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in baseline_files}
    events: list[str] = []
    original_write = Path.write_text

    def tracked_write(path: Path, data: str, *args, **kwargs):
        if path.parent == tmp_path:
            events.append(path.name)
        return original_write(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", tracked_write)
    monkeypatch.setattr(poc01fb, "evaluate", lambda value: events.append("evaluate") or {
        "gate_a_error_detection": True, "gate_b_error_classification": True,
        "gate_c_part_identification": True, "unsupported_hypothesis_count": 0,
    })
    poc01fb.run(root, provider_call=lambda p, i, d: with_inventory(prediction(), d), output_dir=tmp_path)
    assert events[:4] == ["request_audit.json", "raw_diagnosis.json", "evaluate", "experiment_result.json"]
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in baseline_files}
    assert after == before
