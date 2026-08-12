"""POC-01F-B: catalog-grounded, correspondence-first blind diagnosis."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from assembly_agent.reference import CANONICAL_VIEWS
from assembly_agent.vision.gemini import VisionConfigurationError, VisionProviderError

from .poc01f import (
    MODEL_ID,
    STEP_ID,
    TEMPERATURE,
    VISION_MODEL,
    SelectedImage,
    _load_dotenv,
    _select_images,
    _write_json,
)

EXPERIMENT = "POC-01F-B"
REFERENCE_CAPTURE_SELECTION_RULE = "lowest_capture_id_then_source_path_then_record_id"
COMPARISON_RESULTS = (
    "current_only", "correct_only", "identity_mismatch", "attachment_mismatch", "uncertain",
)

PROMPT_TEMPLATE = """You are inspecting a physical construction model.

You are given multiple views of a CURRENT assembly and a CORRECT REFERENCE assembly for the same model and assembly step. Compare them as physical 3D structures. Same-view photographs may have different manually captured camera poses. Do not treat camera position, angle, perspective, object rotation, lighting, scale, or partial occlusion as assembly errors.

Use this complete allowed Part Catalog vocabulary. Every non-uncertain part descriptor in your response must exactly equal one descriptor from this list. All entries are equally weighted; none is expected, likely, or preferred:
ALLOWED_PART_DESCRIPTORS={catalog_descriptors}

Reason by physical-part correspondence before classifying any error:
1. Match plausible corresponding physical part instances between Current and Correct using multiple views where possible.
2. A verified Current-only instance is extra_part.
3. A verified Correct-only instance is missing_part; do not infer this from one occluded view.
4. Corresponding positions with different identities are wrong_part.
5. The same identity with a different attachment or structural relationship is position_error.
6. Use composite_error only for two or more independently correspondence-verified physical differences. A weak second discrepancy must not promote the result to composite_error.
7. If correspondence cannot be established reliably, return uncertain rather than inventing a difference.

Report only supported structural differences, affected catalog parts, supporting views, conflicting views, and confidence. Do not output pixel locations or generate repair instructions.

Current Assembly:
- current_front
- current_back
- current_left
- current_right
- current_top
- current_bottom

Correct Reference Assembly:
- reference_front
- reference_back
- reference_left
- reference_right
- reference_top
- reference_bottom
"""


def load_catalog_descriptors(root: Path) -> tuple[str, ...]:
    catalog = json.loads((root / "data/part_catalog.json").read_text(encoding="utf-8"))
    descriptors = tuple(part["descriptor"] for part in catalog["parts"])
    if not descriptors or len(descriptors) != len(set(descriptors)):
        raise ValueError("Part Catalog descriptors must be non-empty and unique")
    return descriptors


def diagnosis_schema(descriptors: tuple[str, ...]) -> dict[str, Any]:
    views = {"type": "array", "items": {"type": "string", "enum": list(CANONICAL_VIEWS)}}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "status", "error_type", "suspected_parts", "structural_difference",
            "supporting_views", "conflicting_views", "confidence",
        ],
        "properties": {
            "status": {"type": "string", "enum": ["correct", "error", "uncertain"]},
            "error_type": {"type": "string", "enum": [
                "extra_part", "missing_part", "wrong_part", "position_error", "composite_error", "uncertain",
            ]},
            "suspected_parts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["descriptor", "description", "comparison_result", "supporting_views", "confidence"],
                    "properties": {
                        "descriptor": {"type": "string", "enum": list(descriptors)},
                        "description": {"type": "string"},
                        "comparison_result": {"type": "string", "enum": list(COMPARISON_RESULTS)},
                        "supporting_views": views,
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            },
            "structural_difference": {"type": "string"},
            "supporting_views": views,
            "conflicting_views": views,
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }


def build_request(root: Path) -> tuple[str, tuple[SelectedImage, ...], tuple[str, ...], dict[str, Any]]:
    current, reference = _select_images(root)
    images = current + reference
    descriptors = load_catalog_descriptors(root)
    prompt = PROMPT_TEMPLATE.format(catalog_descriptors=json.dumps(descriptors))
    audit = {
        "experiment": EXPERIMENT,
        "model_id": MODEL_ID,
        "step_id": STEP_ID,
        "vision_model": VISION_MODEL,
        "temperature": TEMPERATURE,
        "current_images": [_audit_image(image) for image in current],
        "reference_images": [_audit_image(image) for image in reference],
        "reference_capture_selection_rule": REFERENCE_CAPTURE_SELECTION_RULE,
        "gemini_facing_image_ids": [image.neutral_id for image in images],
        "use_part_catalog": True,
        "catalog_descriptor_count": len(descriptors),
        "catalog_descriptors": list(descriptors),
        "ground_truth_exposed": False,
        "previous_prediction_exposed": False,
    }
    return prompt, images, descriptors, audit


def _audit_image(image: SelectedImage) -> dict[str, str]:
    return {
        "view": image.view,
        "gemini_facing_id": image.neutral_id,
        "record_id": image.record_id,
        "capture_id": image.capture_id,
        "source_path": image.source_path,
    }


def validate_prediction(prediction: dict[str, Any], descriptors: tuple[str, ...]) -> None:
    allowed = set(descriptors)
    for part in prediction.get("suspected_parts", []):
        descriptor = part.get("descriptor") if isinstance(part, dict) else None
        if descriptor not in allowed:
            raise ValueError(f"Gemini returned descriptor outside complete Part Catalog: {descriptor}")


def call_gemini(
    api_key: str, prompt: str, images: tuple[SelectedImage, ...], descriptors: tuple[str, ...]
) -> dict[str, Any]:
    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise VisionConfigurationError("install google-genai before running POC-01F-B") from error
    contents: list[Any] = [prompt]
    for image in images:
        contents.extend([image.neutral_id, types.Part.from_bytes(data=image.path.read_bytes(), mime_type="image/jpeg")])
    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=VISION_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=TEMPERATURE,
                response_mime_type="application/json",
                response_json_schema=diagnosis_schema(descriptors),
            ),
        )
        payload = response.parsed if isinstance(response.parsed, dict) else json.loads(response.text)
        if not isinstance(payload, dict):
            raise ValueError("structured response is not an object")
        return payload
    except Exception as error:
        raise VisionProviderError(f"Gemini request failed: {error}") from error
    finally:
        client.close()


def evaluate(prediction: dict[str, Any]) -> dict[str, Any]:
    parts = [part for part in prediction.get("suspected_parts", []) if isinstance(part, dict)]
    target_claims = [part for part in parts if part.get("descriptor") == "PIN_RED_SHORT"]
    unsupported_count = len(parts) - min(1, len(target_claims))
    return {
        "gate_a_error_detection": prediction.get("status") == "error",
        "gate_b_error_classification": prediction.get("error_type") == "extra_part",
        "gate_c_part_identification": bool(target_claims),
        "gate_d_structural_localization": "unevaluated",
        "gate_e_view_evidence": "unevaluated",
        "unsupported_hypothesis_count": unsupported_count,
    }


def ablation_comparison(root: Path, variant_result: dict[str, Any]) -> dict[str, Any]:
    baseline = json.loads((root / "outputs/poc01f/experiment_result.json").read_text(encoding="utf-8"))
    base_eval = baseline["evaluation"]
    variant_eval = variant_result["evaluation"]
    baseline_parts = baseline["prediction"].get("suspected_parts", [])
    baseline_unsupported = max(0, len(baseline_parts) - 1)
    return {
        "baseline": "POC-01F-A",
        "variant": EXPERIMENT,
        "changed_variables": ["full_part_catalog_grounding", "correspondence_first_reasoning_policy"],
        "gate_a": {"baseline": base_eval["gate_a_error_detection"], "variant": variant_eval["gate_a_error_detection"]},
        "gate_b": {"baseline": base_eval["gate_b_error_classification"], "variant": variant_eval["gate_b_error_classification"]},
        "gate_c": {"baseline": base_eval["gate_c_part_identification"], "variant": variant_eval["gate_c_part_identification"]},
        "unsupported_hypothesis_count": {"baseline": baseline_unsupported, "variant": variant_eval["unsupported_hypothesis_count"]},
        "interpretation": None,
    }


def run(
    root: Path,
    *,
    provider_call: Callable[[str, tuple[SelectedImage, ...], tuple[str, ...]], dict[str, Any]] | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    output_dir = output_dir or root / "outputs/poc01fb"
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt, images, descriptors, audit = build_request(root)
    _write_json(output_dir / "request_audit.json", audit)
    if provider_call is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise VisionConfigurationError("GEMINI_API_KEY is required for POC-01F-B")
        provider_call = lambda p, i, d: call_gemini(api_key, p, i, d)
    prediction = provider_call(prompt, images, descriptors)
    _write_json(output_dir / "raw_diagnosis.json", prediction)
    validate_prediction(prediction, descriptors)
    result = {"experiment": EXPERIMENT, "prediction": prediction, "evaluation": evaluate(prediction)}
    _write_json(output_dir / "experiment_result.json", result)
    _write_json(output_dir / "ablation_comparison.json", ablation_comparison(root, result))
    return result


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    _load_dotenv(root / ".env")
    try:
        result = run(root)
    except (VisionConfigurationError, VisionProviderError, ValueError) as error:
        error_path = root / "outputs/poc01fb/api_error.json"
        error_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(error_path, {"experiment": EXPERIMENT, "error": str(error)})
        raise SystemExit(str(error)) from error
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

