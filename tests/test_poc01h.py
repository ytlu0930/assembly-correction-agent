from __future__ import annotations

import json
from pathlib import Path

import pytest

from assembly_agent.experiments import poc01h
from assembly_agent.reference import CANONICAL_VIEWS


@pytest.fixture
def root() -> Path:
    return Path(__file__).parents[1]


def response(candidates):
    return {"hypothesis": {"error_type": "extra_part", "descriptor": "PIN_RED_SHORT", "comparison_result": "current_only"},
        "view_results": [{"view": view, "selection": "uncertain", "candidate_id": None, "confidence": 0.5, "evidence": "insufficient"} for view in CANONICAL_VIEWS],
        "cross_view_assessment": {"hypothesis_status": "uncertain", "supporting_views": [], "conflicting_views": [], "confidence": 0.5, "reason": "insufficient"}}


def test_hypothesis_is_persisted_agent_output_and_prompt_has_no_location_or_gt(root: Path) -> None:
    hypothesis = poc01h.load_hypothesis(root)
    persisted = json.loads((root / "outputs/poc01fb/raw_diagnosis.json").read_text())
    assert hypothesis.descriptor == persisted["suspected_parts"][0]["descriptor"]
    prompt = poc01h.build_prompt(hypothesis, {view: 1 for view in CANONICAL_VIEWS})
    forbidden = ("left hole", "blue y-joint", "f5", "b5", "l4", "r5", "t2", "bbox", "coordinate", "green-box")
    assert all(term not in prompt.lower() for term in forbidden)
    schema = json.dumps(poc01h.verification_schema()).lower()
    assert all(term not in schema for term in ("bbox", "coordinate", "xyxy", "polygon", "segmentation", "mask"))


def test_candidate_ids_are_neutral_and_response_is_view_constrained(root: Path, tmp_path: Path) -> None:
    current, _ = poc01h._select_images(root)
    candidates = poc01h.generate_candidates(root, current, tmp_path)
    assert candidates
    assert all(item.candidate_id.startswith(f"current_{item.view}_candidate_") for item in candidates)
    payload = response(candidates)
    poc01h.validate_response(payload, candidates)
    payload["view_results"][0] = {**payload["view_results"][0], "selection": "candidate", "candidate_id": "F5"}
    with pytest.raises(ValueError, match="invalid candidate ID"):
        poc01h.validate_response(payload, candidates)


def test_raw_verification_precedes_evaluator(root: Path, tmp_path: Path, monkeypatch) -> None:
    events = []
    original = Path.write_text
    def tracked(path, data, *args, **kwargs):
        if path.parent == tmp_path:
            events.append(path.name)
        return original(path, data, *args, **kwargs)
    monkeypatch.setattr(Path, "write_text", tracked)
    def evaluator(payload, candidates):
        events.append("evaluator")
        return {}
    poc01h.run(root, provider_call=lambda p, c, r: response(c), output_dir=tmp_path, evaluator=evaluator)
    assert events.index("raw_verification.json") < events.index("evaluator")
