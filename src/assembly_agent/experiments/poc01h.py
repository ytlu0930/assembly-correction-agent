"""POC-01H: verify Python-generated candidates with Gemini candidate IDs only."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np
from PIL import Image, ImageDraw

from assembly_agent.reference import CANONICAL_VIEWS
from assembly_agent.vision.gemini import VisionConfigurationError, VisionProviderError

from .poc01f import TEMPERATURE, VISION_MODEL, SelectedImage, _load_dotenv, _select_images, _write_json

EXPERIMENT = "POC-01H"
UPSTREAM_EXPERIMENT = "POC-01F-B"


@dataclass(frozen=True)
class Hypothesis:
    error_type: str
    descriptor: str
    comparison_result: str


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    view: str
    source_record_id: str
    bbox_original_xyxy: tuple[int, int, int, int]
    tight_crop_path: str
    context_crop_path: str


def load_hypothesis(root: Path) -> Hypothesis:
    payload = json.loads((root / "outputs/poc01fb/raw_diagnosis.json").read_text(encoding="utf-8"))
    parts = payload.get("suspected_parts")
    if not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], dict):
        raise ValueError("POC-01F-B must contain exactly one suspected part for POC-01H")
    part = parts[0]
    return Hypothesis(payload["error_type"], part["descriptor"], part["comparison_result"])


def _expanded(box: tuple[int, int, int, int], size: tuple[int, int], factor: float) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    width, height = size
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    half_w, half_h = max(16, (x2 - x1) * factor / 2), max(16, (y2 - y1) * factor / 2)
    return max(0, int(cx - half_w)), max(0, int(cy - half_h)), min(width, int(cx + half_w)), min(height, int(cy + half_h))


def _red_regions(path: Path) -> list[tuple[int, int, int, int]]:
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"cannot read Current image: {path}")
    height, width = image.shape[:2]
    scale = min(1.0, 1200 / max(height, width))
    work = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else image
    hsv = cv2.cvtColor(work, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([0, 70, 45]), np.array([12, 255, 255]))
    mask |= cv2.inRange(hsv, np.array([168, 70, 45]), np.array([179, 255, 255]))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    minimum = max(20, round(work.shape[0] * work.shape[1] * 0.00004))
    boxes = []
    for x, y, w, h, area in stats[1:count]:
        if area >= minimum and w >= 4 and h >= 4:
            boxes.append(tuple(round(value / scale) for value in (x, y, x + w, y + h)))
    return sorted(boxes, key=lambda box: (box[1], box[0], box[3], box[2]))


def generate_candidates(root: Path, current: tuple[SelectedImage, ...], output_dir: Path) -> tuple[Candidate, ...]:
    crop_dir = output_dir / "candidates"
    crop_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[Candidate] = []
    for selected in current:
        source = Image.open(selected.path).convert("RGB")
        for index, box in enumerate(_red_regions(selected.path), start=1):
            candidate_id = f"current_{selected.view}_candidate_{index:03d}"
            tight_box = _expanded(box, source.size, 1.6)
            context_box = _expanded(box, source.size, 5.0)
            tight = source.crop(tight_box)
            context = source.crop(context_box)
            for crop, crop_box in ((tight, tight_box), (context, context_box)):
                draw = ImageDraw.Draw(crop)
                marker = (box[0] - crop_box[0], box[1] - crop_box[1], box[2] - crop_box[0], box[3] - crop_box[1])
                draw.rectangle(marker, outline=(255, 255, 0), width=max(2, round(min(crop.size) / 150)))
                draw.text((4, 4), candidate_id, fill=(255, 255, 0), stroke_width=2, stroke_fill=(0, 0, 0))
            tight_path = crop_dir / f"{candidate_id}_tight.jpg"
            context_path = crop_dir / f"{candidate_id}_context.jpg"
            tight.save(tight_path, quality=95)
            context.save(context_path, quality=95)
            try:
                tight_record = tight_path.relative_to(root).as_posix()
                context_record = context_path.relative_to(root).as_posix()
            except ValueError:
                tight_record, context_record = tight_path.as_posix(), context_path.as_posix()
            candidates.append(Candidate(
                candidate_id, selected.view, selected.record_id, box,
                tight_record, context_record,
            ))
    return tuple(candidates)


def verification_schema() -> dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False,
        "required": ["hypothesis", "view_results", "cross_view_assessment"],
        "properties": {
            "hypothesis": {"type": "object", "additionalProperties": False,
                "required": ["error_type", "descriptor", "comparison_result"],
                "properties": {name: {"type": "string"} for name in ("error_type", "descriptor", "comparison_result")}},
            "view_results": {"type": "array", "minItems": 6, "maxItems": 6, "items": {
                "type": "object", "additionalProperties": False,
                "required": ["view", "selection", "candidate_id", "confidence", "evidence"],
                "properties": {
                    "view": {"type": "string", "enum": list(CANONICAL_VIEWS)},
                    "selection": {"type": "string", "enum": ["candidate", "not_visible", "uncertain"]},
                    "candidate_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}, "evidence": {"type": "string"},
                }}},
            "cross_view_assessment": {"type": "object", "additionalProperties": False,
                "required": ["hypothesis_status", "supporting_views", "conflicting_views", "confidence", "reason"],
                "properties": {
                    "hypothesis_status": {"type": "string", "enum": ["supported", "rejected", "uncertain"]},
                    "supporting_views": {"type": "array", "items": {"type": "string", "enum": list(CANONICAL_VIEWS)}},
                    "conflicting_views": {"type": "array", "items": {"type": "string", "enum": list(CANONICAL_VIEWS)}},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}, "reason": {"type": "string"},
                }},
        },
    }


def build_prompt(hypothesis: Hypothesis, counts: dict[str, int]) -> str:
    return f"""Verify an Agent-generated physical assembly hypothesis using only Python-generated candidate observations and six Correct Reference views.
HYPOTHESIS={json.dumps(asdict(hypothesis))}
AVAILABLE_CANDIDATE_COUNTS={json.dumps(counts)}
For each Current view, return exactly one result in front, back, left, right, top, bottom order. Select candidate only if one supplied candidate is the hypothesized physical instance and lacks a corresponding instance in Correct Reference. Otherwise return not_visible or uncertain with a null candidate_id. Candidate IDs must be copied exactly from candidates supplied for that same view. Do not invent IDs or geometry. Photographs are manually captured and may differ in camera position, angle, perspective, object rotation, lighting, scale, and occlusion; compare physical structure, not pixels. Tight crops show appearance; context crops show attachment and neighboring structure. All markers have the same neutral style. Do not output locations or correction actions."""


def validate_response(payload: dict[str, Any], candidates: tuple[Candidate, ...]) -> None:
    by_view = {view: {item.candidate_id for item in candidates if item.view == view} for view in CANONICAL_VIEWS}
    results = payload.get("view_results")
    if not isinstance(results, list) or [item.get("view") for item in results] != list(CANONICAL_VIEWS):
        raise ValueError("view_results must contain all six canonical views exactly once in order")
    for result in results:
        candidate_id = result.get("candidate_id")
        if result.get("selection") == "candidate":
            if candidate_id not in by_view[result["view"]]:
                raise ValueError(f"invalid candidate ID for {result['view']}: {candidate_id}")
        elif candidate_id is not None:
            raise ValueError("not_visible and uncertain require null candidate_id")


def call_gemini(api_key: str, prompt: str, candidates: tuple[Candidate, ...], references: tuple[SelectedImage, ...], root: Path) -> dict[str, Any]:
    from google import genai
    from google.genai import types
    contents: list[Any] = [prompt]
    for view in CANONICAL_VIEWS:
        contents.append(f"CURRENT_{view.upper()}_CANDIDATES")
        for candidate in (item for item in candidates if item.view == view):
            tight_path, context_path = Path(candidate.tight_crop_path), Path(candidate.context_crop_path)
            tight_path = tight_path if tight_path.is_absolute() else root / tight_path
            context_path = context_path if context_path.is_absolute() else root / context_path
            contents.extend([candidate.candidate_id, "TIGHT_CROP", types.Part.from_bytes(data=tight_path.read_bytes(), mime_type="image/jpeg"),
                             "CONTEXT_CROP", types.Part.from_bytes(data=context_path.read_bytes(), mime_type="image/jpeg")])
    contents.append("CORRECT_REFERENCE_ASSEMBLY")
    for reference in references:
        contents.extend([reference.neutral_id, types.Part.from_bytes(data=reference.path.read_bytes(), mime_type="image/jpeg")])
    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(model=VISION_MODEL, contents=contents, config=types.GenerateContentConfig(
            temperature=TEMPERATURE, response_mime_type="application/json", response_json_schema=verification_schema()))
        return response.parsed if isinstance(response.parsed, dict) else json.loads(response.text)
    except Exception as error:
        raise VisionProviderError(f"Gemini request failed: {error}") from error
    finally:
        client.close()


def evaluate(payload: dict[str, Any], candidates: tuple[Candidate, ...]) -> dict[str, Any]:
    # Candidate-to-human-target correspondence requires post-inference human review.
    per_view = []
    false_selections = 0
    for result in payload["view_results"]:
        bottom_bad = result["view"] == "bottom" and result["selection"] == "candidate"
        false_selections += int(bottom_bad)
        known_visibility_error = result["view"] in ("front", "back", "left", "right", "top") and result["selection"] == "not_visible"
        bottom_correct = result["view"] == "bottom" and result["selection"] in ("not_visible", "uncertain")
        correctness = "incorrect" if known_visibility_error else "correct" if bottom_correct else "unevaluated"
        per_view.append({**result, "human_evaluation_correctness": correctness, "bbox_evaluation_status": "unevaluated"})
    bottom = next(item for item in payload["view_results"] if item["view"] == "bottom")
    return {
        "per_view": per_view,
        "h1_candidate_selection_accuracy": "unevaluated",
        "h2_multi_view_consistency": "unevaluated",
        "h3_false_selection_control": "pass" if bottom["selection"] in ("not_visible", "uncertain") else "fail",
        "h3_bottom_behavior": bottom["selection"],
        "h4_localization": {view: "unevaluated" for view in CANONICAL_VIEWS},
        "visible_view_candidate_accuracy": None,
        "false_selection_count": false_selections,
        "not_visible_handling": bottom["selection"],
        "invalid_candidate_id_count": 0,
        "correct_candidate_bbox_count": 0,
    }


def run(root: Path, *, provider_call: Callable[..., dict[str, Any]] | None = None, output_dir: Path | None = None,
        evaluator: Callable[[dict[str, Any], tuple[Candidate, ...]], dict[str, Any]] = evaluate) -> dict[str, Any]:
    output_dir = output_dir or root / "outputs/poc01h"
    output_dir.mkdir(parents=True, exist_ok=True)
    hypothesis = load_hypothesis(root)
    current, references = _select_images(root)
    candidates = generate_candidates(root, current, output_dir)
    _write_json(output_dir / "candidate_manifest.json", {"candidates": [asdict(item) for item in candidates]})
    counts = {view: sum(item.view == view for item in candidates) for view in CANONICAL_VIEWS}
    prompt = build_prompt(hypothesis, counts)
    audit = {"experiment": EXPERIMENT, "upstream_experiment": UPSTREAM_EXPERIMENT, "vision_model": VISION_MODEL,
        "temperature": TEMPERATURE, "current_view_count": 6, "reference_view_count": 6,
        "current_record_ids": [item.record_id for item in current], "reference_record_ids": [item.record_id for item in references],
        "candidate_counts_per_view": counts, "hypothesis_source": "persisted_agent_prediction", "human_target_exposed": False,
        "human_bbox_exposed": False, "gemini_coordinates_allowed": False, "structural_location_used_for_candidate_generation": False,
        "candidate_ids_neutral": True}
    _write_json(output_dir / "request_audit.json", audit)
    if provider_call is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise VisionConfigurationError("GEMINI_API_KEY is required for POC-01H")
        provider_call = lambda p, c, r: call_gemini(api_key, p, c, r, root)
    payload = provider_call(prompt, candidates, references)
    _write_json(output_dir / "raw_verification.json", payload)
    validate_response(payload, candidates)
    result = {"experiment": EXPERIMENT, "hypothesis": asdict(hypothesis), "verification": payload,
              "evaluation": evaluator(payload, candidates)}
    _write_json(output_dir / "experiment_result.json", result)
    return result


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    _load_dotenv(root / ".env")
    try:
        result = run(root)
    except (VisionConfigurationError, VisionProviderError, ValueError) as error:
        error_path = root / "outputs/poc01h/api_error.json"
        error_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(error_path, {"experiment": EXPERIMENT, "error": str(error)})
        raise SystemExit(str(error)) from error
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
