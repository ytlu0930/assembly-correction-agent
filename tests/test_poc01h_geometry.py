from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from assembly_agent.experiments.poc01h_geometry import (
    CONTEXT_XYXY, LOCAL_XYXY, RENDERED_XYXY, XYXY, clip_xyxy, context_bounds,
    context_local_to_rendered, original_to_context_local, run_geometry_audit,
    xywh_to_xyxy, xyxy_to_xywh,
)


def test_named_box_conversions_and_validation() -> None:
    assert xywh_to_xyxy((10, 20, 30, 40)) == (10, 20, 40, 60)
    assert xyxy_to_xywh((10, 20, 40, 60)) == (10, 20, 30, 40)
    for malformed in ((1, 2, 3), (1, 2, 1, 4), (1, 5, 3, 4), ("1", 2, 3, 4)):
        with pytest.raises(ValueError):
            xyxy_to_xywh(malformed)


def test_context_transforms_edges_and_non_square_resize() -> None:
    assert context_bounds((0, 0, 10, 20), (100, 80)) == (0, 0, 30, 60)
    assert context_bounds((90, 60, 100, 80), (100, 80)) == (70, 20, 100, 80)
    assert original_to_context_local((90, 60, 100, 80), (70, 20, 100, 80)) == (20, 40, 30, 60)
    assert context_local_to_rendered((20, 40, 30, 60), (30, 60), (300, 120)) == (200, 80, 300, 120)
    assert clip_xyxy((-5, -8, 12, 14), (10, 10)) == (0, 0, 10, 10)


def test_pixel_fidelity_and_explicit_coordinate_names() -> None:
    original = Image.fromarray(np.arange(100 * 80 * 3, dtype=np.uint8).reshape(80, 100, 3))
    bbox = (4, 7, 20, 24)
    context = (0, 0, 44, 50)
    local = original_to_context_local(bbox, context)
    assert np.array_equal(np.asarray(original.crop(bbox)), np.asarray(original.crop(context).crop(local)))
    assert (XYXY, CONTEXT_XYXY, LOCAL_XYXY, RENDERED_XYXY) == (
        "original_image_xyxy", "context_crop_original_xyxy", "context_crop_local_xyxy", "context_rendered_xyxy")


def test_full_audit_preserves_candidates_and_generator(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    source_path = root / "src/assembly_agent/experiments/poc01h.py"
    source = source_path.read_text()
    function = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "_red_regions")
    before_hash = hashlib.sha256(ast.get_source_segment(source, function).encode()).hexdigest()
    old = json.loads((root / "outputs/poc01h/candidate_manifest.json").read_text())["candidates"]
    report = run_geometry_audit(root, tmp_path)
    new = json.loads((tmp_path / "candidate_geometry_manifest.json").read_text())["candidates"]
    assert report == {"candidate_count": 47, "pixel_fidelity_failures": 0, "out_of_bounds_failures": 0,
                      "invalid_bbox_failures": 0, "failure_classification": [], "gemini_calls": 0}
    assert [(item["candidate_id"], item["bbox_original_xyxy"]) for item in new] == [
        (item["candidate_id"], item["bbox_original_xyxy"]) for item in old]
    after_source = source_path.read_text()
    after_function = next(node for node in ast.parse(after_source).body if isinstance(node, ast.FunctionDef) and node.name == "_red_regions")
    assert hashlib.sha256(ast.get_source_segment(after_source, after_function).encode()).hexdigest() == before_hash

