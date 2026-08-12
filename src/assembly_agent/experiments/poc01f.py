"""POC-01F: blind Gemini diagnosis from six current and six reference views."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from assembly_agent.reference import CANONICAL_VIEWS, ReferenceRepository
from assembly_agent.vision.gemini import VisionConfigurationError, VisionProviderError

EXPERIMENT = "POC-01F"
MODEL_ID = "model03"
STEP_ID = "step03"
CURRENT_CASE_ID = "A01"
REFERENCE_CASE_ID = "01"
VISION_MODEL = "gemini-3.1-pro-preview"
TEMPERATURE = 0
USE_PART_CATALOG = False

DIAGNOSIS_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "status", "error_type", "suspected_parts", "structural_difference",
        "supporting_views", "conflicting_views", "confidence",
    ],
    "properties": {
        "status": {"type": "string", "enum": ["correct", "error", "uncertain"]},
        "error_type": {
            "type": "string",
            "enum": [
                "extra_part", "missing_part", "wrong_part", "position_error",
                "composite_error", "uncertain",
            ],
        },
        "suspected_parts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["descriptor", "description", "confidence"],
                "properties": {
                    "descriptor": {"type": "string"},
                    "description": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "structural_difference": {"type": "string"},
        "supporting_views": {"type": "array", "items": {"type": "string", "enum": list(CANONICAL_VIEWS)}},
        "conflicting_views": {"type": "array", "items": {"type": "string", "enum": list(CANONICAL_VIEWS)}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

BLIND_PROMPT = """You are inspecting a physical construction model.

You are given multiple views of:
1. a CURRENT assembly that may contain an assembly error;
2. a CORRECT REFERENCE assembly for the same model and assembly step.

Compare the assemblies as physical 3D structures. Same-view photographs may have different manually captured camera poses. Do not treat ordinary differences in camera position, angle, perspective, object rotation, lighting, scale, or partial occlusion as assembly errors. Reason about physical parts and structural relationships, and only report a difference when it is a plausible physical assembly difference.

Determine whether the Current assembly differs structurally from the Correct Reference. If an error exists, classify it, identify the most likely affected physical part or part type, describe the structural difference, identify the views that provide evidence, and identify views that conflict with or weaken the hypothesis. If evidence is insufficient, return uncertain.

Do not output pixel coordinates, bounding boxes, or points. Do not generate repair instructions.

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


@dataclass(frozen=True)
class SelectedImage:
    role: str
    view: str
    neutral_id: str
    path: Path
    record_id: str
    capture_id: str
    source_path: str


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _select_images(root: Path) -> tuple[tuple[SelectedImage, ...], tuple[SelectedImage, ...]]:
    records = _load_jsonl(root / "data/dataset_manifest.jsonl")
    current: list[SelectedImage] = []
    for view in CANONICAL_VIEWS:
        matches = [record for record in records if (
            record.get("model_id") == MODEL_ID and record.get("step_id") == STEP_ID
            and record.get("normalized_label") == "extra_part" and record.get("case_id") == CURRENT_CASE_ID
            and record.get("view") == view
        )]
        matches.sort(key=lambda item: (item["capture_id"], item["source_path"], item["record_id"]))
        if len(matches) != 1:
            raise RuntimeError(f"expected exactly one current {view} capture, found {len(matches)}")
        record = matches[0]
        current.append(SelectedImage(
            "current", view, f"current_{view}", root / record["source_path"], record["record_id"],
            record["capture_id"], record["source_path"],
        ))

    repository = ReferenceRepository(root)
    reference: list[SelectedImage] = []
    for view in CANONICAL_VIEWS:
        captures = repository.get_reference_view(MODEL_ID, STEP_ID, REFERENCE_CASE_ID, view).captures
        selected = sorted(captures, key=lambda item: (item.capture_id, item.source_path, item.record_id))[0]
        reference.append(SelectedImage(
            "reference", view, f"reference_{view}", root / selected.source_path, selected.record_id,
            selected.capture_id, selected.source_path,
        ))
    return tuple(current), tuple(reference)


def build_request(root: Path) -> tuple[str, tuple[SelectedImage, ...], dict[str, Any]]:
    current, reference = _select_images(root)
    images = current + reference
    audit = {
        "experiment": EXPERIMENT,
        "model_id": MODEL_ID,
        "step_id": STEP_ID,
        "vision_model": VISION_MODEL,
        "temperature": TEMPERATURE,
        "current_images": [_audit_image(image) for image in current],
        "reference_images": [_audit_image(image) for image in reference],
        "reference_capture_selection_rule": "lowest_capture_id_then_source_path_then_record_id",
        "gemini_facing_image_ids": [image.neutral_id for image in images],
        "use_part_catalog": USE_PART_CATALOG,
        "ground_truth_exposed": False,
    }
    return BLIND_PROMPT, images, audit


def _audit_image(image: SelectedImage) -> dict[str, str]:
    return {
        "view": image.view, "gemini_facing_id": image.neutral_id, "record_id": image.record_id,
        "capture_id": image.capture_id, "source_path": image.source_path,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def call_gemini(api_key: str, prompt: str, images: tuple[SelectedImage, ...]) -> dict[str, Any]:
    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise VisionConfigurationError("install google-genai before running POC-01F") from error
    contents: list[Any] = [prompt]
    for image in images:
        contents.extend([
            image.neutral_id,
            types.Part.from_bytes(data=image.path.read_bytes(), mime_type="image/jpeg"),
        ])
    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=VISION_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=TEMPERATURE,
                response_mime_type="application/json",
                response_json_schema=DIAGNOSIS_RESPONSE_SCHEMA,
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
    suspected = prediction.get("suspected_parts", [])
    raw_descriptions = [
        {"descriptor": part.get("descriptor"), "description": part.get("description")}
        for part in suspected if isinstance(part, dict)
    ]
    normalized = " ".join(
        str(value).lower().replace("_", " ")
        for part in raw_descriptions for value in part.values() if value is not None
    )
    part_match = "pin red short" in normalized or "red short pin" in normalized or "short red pin" in normalized
    return {
        "gate_a_error_detection": prediction.get("status") == "error",
        "gate_b_error_classification": prediction.get("error_type") == "extra_part",
        "gate_c_part_identification": part_match,
        "gate_c_raw_description": raw_descriptions,
        "gate_c_normalized_target": "PIN_RED_SHORT" if part_match else None,
        "gate_d_structural_localization": "unevaluated",
        "gate_e_view_evidence": "unevaluated",
    }


def run(
    root: Path,
    *,
    provider_call: Callable[[str, tuple[SelectedImage, ...]], dict[str, Any]] | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    output_dir = output_dir or root / "outputs/poc01f"
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt, images, audit = build_request(root)
    _write_json(output_dir / "request_audit.json", audit)

    if provider_call is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise VisionConfigurationError("GEMINI_API_KEY is required for POC-01F")
        provider_call = lambda request_prompt, request_images: call_gemini(api_key, request_prompt, request_images)

    prediction = provider_call(prompt, images)
    _write_json(output_dir / "raw_diagnosis.json", prediction)
    result = {"experiment": EXPERIMENT, "prediction": prediction, "evaluation": evaluate(prediction)}
    _write_json(output_dir / "experiment_result.json", result)
    return result


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    _load_dotenv(root / ".env")
    try:
        result = run(root)
    except (VisionConfigurationError, VisionProviderError) as error:
        error_path = root / "outputs/poc01f/api_error.json"
        error_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(error_path, {"experiment": EXPERIMENT, "error": str(error)})
        raise SystemExit(str(error)) from error
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

