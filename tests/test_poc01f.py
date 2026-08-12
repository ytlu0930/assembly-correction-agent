from __future__ import annotations

import json
from pathlib import Path

import pytest

from assembly_agent.experiments.poc01f import (
    CANONICAL_VIEWS,
    DIAGNOSIS_RESPONSE_SCHEMA,
    build_request,
    run,
)


@pytest.fixture
def repository_root() -> Path:
    return Path(__file__).parents[1]


def _prediction() -> dict:
    return {
        "status": "error",
        "error_type": "extra_part",
        "suspected_parts": [{"descriptor": "short red pin", "description": "a pin", "confidence": 0.9}],
        "structural_difference": "one physical part is present only in current",
        "supporting_views": ["front"],
        "conflicting_views": [],
        "confidence": 0.8,
    }


def test_blind_request_has_neutral_roles_six_views_and_no_leakage(repository_root: Path) -> None:
    prompt, images, audit = build_request(repository_root)
    forbidden = ("extrapart", "extra_part", "pin_red_short", "red short pin", "raw_data", ".jpg")
    assert all(term not in prompt.lower() for term in forbidden)
    assert tuple(image.view for image in images[:6]) == CANONICAL_VIEWS
    assert tuple(image.view for image in images[6:]) == CANONICAL_VIEWS
    assert tuple(image.role for image in images[:6]) == ("current",) * 6
    assert tuple(image.role for image in images[6:]) == ("reference",) * 6
    assert audit["gemini_facing_image_ids"] == [
        *(f"current_{view}" for view in CANONICAL_VIEWS),
        *(f"reference_{view}" for view in CANONICAL_VIEWS),
    ]
    assert audit["ground_truth_exposed"] is False
    assert audit["use_part_catalog"] is False


def test_diagnosis_schema_contains_no_localization_fields() -> None:
    serialized = json.dumps(DIAGNOSIS_RESPONSE_SCHEMA).lower()
    assert "bbox" not in serialized
    assert "point" not in serialized
    assert "coordinate" not in serialized


def test_raw_prediction_is_persisted_before_ground_truth_evaluation(tmp_path: Path, repository_root: Path, monkeypatch) -> None:
    events: list[str] = []
    original_write_text = Path.write_text

    def tracked_write_text(path: Path, data: str, *args, **kwargs):
        if path.name in {"request_audit.json", "raw_diagnosis.json", "experiment_result.json"}:
            events.append(path.name)
        return original_write_text(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", tracked_write_text)
    monkeypatch.setattr("assembly_agent.experiments.poc01f.evaluate", lambda prediction: events.append("evaluate") or {})
    run(repository_root, provider_call=lambda prompt, images: _prediction(), output_dir=tmp_path)
    assert events == ["request_audit.json", "raw_diagnosis.json", "evaluate", "experiment_result.json"]

