"""Run the explicit Model03 Step03 Gemini extra-part demo."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from assembly_agent.correction import CorrectionAction
from assembly_agent.imaging import annotate_remove
from assembly_agent.localization import GroundedLocalization, GroundingDinoDetector
from assembly_agent.reference import ReferenceRepository
from assembly_agent.vision import GeminiVisionAdapter, VisionConfigurationError, build_gemini_request
from assembly_agent.vision.localization import evaluate_localization

MODEL_ID = "model03"
STEP_ID = "step03"
DEMO_VIEW = "front"
CURRENT_CASE_ID = "A01"
REFERENCE_CASE_ID = "01"
CURRENT_NEUTRAL_ID = "demo_current_0001"
REFERENCE_NEUTRAL_ID = "demo_reference_0001"


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _select_current(records: list[dict]) -> dict:
    matches = [record for record in records if (
        record.get("model_id") == MODEL_ID and record.get("step_id") == STEP_ID
        and record.get("normalized_label") == "extra_part" and record.get("case_id") == CURRENT_CASE_ID
        and record.get("view") == DEMO_VIEW and record.get("capture_id") == "01"
    )]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one configured demo current image, found {len(matches)}")
    return matches[0]


def _part_references(root: Path) -> list[tuple[str, Path]]:
    catalog = json.loads((root / "data/part_catalog.json").read_text(encoding="utf-8"))
    return [(part["descriptor"], root / part["reference_image_paths"][0]) for part in catalog["parts"]]


def run(root: Path) -> dict:
    _load_dotenv(root / ".env")
    provider = os.environ.get("VISION_PROVIDER", "google")
    model = os.environ.get("VISION_MODEL", "gemini-3.1-pro-preview")
    temperature = float(os.environ.get("VISION_TEMPERATURE", "0"))
    if provider != "google":
        raise VisionConfigurationError(f"unsupported VISION_PROVIDER for Demo 01: {provider}")
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise VisionConfigurationError(
            "GEMINI_API_KEY is missing. Set it in the environment or in the repository .env file before the live demo."
        )

    records = _load_jsonl(root / "data/dataset_manifest.jsonl")
    current = _select_current(records)
    repository = ReferenceRepository(root)
    reference = repository.get_reference_view(MODEL_ID, STEP_ID, REFERENCE_CASE_ID, DEMO_VIEW).captures[0]
    request = build_gemini_request(
        root / current["source_path"], root / reference.source_path, _part_references(root),
        current_id=CURRENT_NEUTRAL_ID, reference_id=REFERENCE_NEUTRAL_ID,
    )
    adapter = GeminiVisionAdapter(api_key, model, temperature=temperature)
    diagnosis = adapter.diagnose(request)
    grounding = None
    localization = None
    if diagnosis.status == "error" and diagnosis.target_part_descriptor:
        catalog = json.loads((root / "data/part_catalog.json").read_text(encoding="utf-8"))
        part = next(item for item in catalog["parts"] if item["descriptor"] == diagnosis.target_part_descriptor)
        grounding = GroundingDinoDetector().detect_candidates(
            root / current["source_path"], diagnosis.target_part_descriptor, part.get("display_name")
        )
        localization = (
            adapter.compare_grounded_candidates(request, diagnosis.target_part_descriptor, grounding)
            if grounding.candidates else GroundedLocalization(
                diagnosis.target_part_descriptor, (), None, "not_verified", "candidate_detection_failure"
            )
        )
    output_dir = root / "outputs/demo01"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "stage_a_result.json").write_text(
        json.dumps(diagnosis.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    grounding_payload = grounding.to_dict() if grounding else None
    (output_dir / "grounding_result.json").write_text(
        json.dumps(grounding_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    stage_b_payload = localization.to_dict() if localization else {
        "target_descriptor": diagnosis.target_part_descriptor, "assessments": [],
        "selected_candidate_id": None, "localization_status": "not_verified",
        "failure_type": "verification_failure",
    }
    (output_dir / "stage_b_result.json").write_text(
        json.dumps(stage_b_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    grounded_by_id = {item.candidate_id: item for item in grounding.candidates} if grounding else {}
    selected = grounded_by_id.get(localization.selected_candidate_id) if localization else None
    action = CorrectionAction("REMOVE", diagnosis.target_part_descriptor) if (
        localization and localization.localization_status == "verified" and selected is not None
        and diagnosis.status == "error" and diagnosis.error_type == "extra_part"
    ) else None
    annotation = None
    annotated_path = output_dir / "annotated_remove.png"
    if action and selected:
        width, height = grounding.image_size
        normalized = tuple(round(value * 1000 / (width if index % 2 == 0 else height)) for index, value in enumerate(selected.bbox))
        annotation = annotate_remove(root / current["source_path"], annotated_path, normalized)
    elif annotated_path.exists():
        annotated_path.unlink()
    evaluator = {
        "error_type_correct": diagnosis.error_type == "extra_part",
        "part_correct": diagnosis.target_part_descriptor == "PIN_RED_SHORT",
        **evaluate_localization(None, None),
    }
    result = {
        "model_id": MODEL_ID,
        "step_id": STEP_ID,
        "neutral_input_image_id": CURRENT_NEUTRAL_ID,
        "reference_image_id": REFERENCE_NEUTRAL_ID,
        "vision_provider": provider,
        "vision_model": model,
        "vision_prompt_version": os.environ.get("VISION_PROMPT_VERSION", "demo01-v1"),
        "predicted_error_type": diagnosis.error_type,
        "predicted_part_descriptor": diagnosis.target_part_descriptor,
        "stage_a": diagnosis.to_dict(),
        "stage_b": stage_b_payload,
        "grounding": grounding_payload,
        "localization_status": stage_b_payload["localization_status"],
        "localization": asdict(selected) if selected else None,
        "correction_action": asdict(action) if action else None,
        "annotated_image_path": "outputs/demo01/annotated_remove.png" if annotation else None,
        "evaluator": evaluator,
    }
    (output_dir / "demo_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"source_path": current["source_path"], "reference_path": reference.source_path, "result": result}


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    try:
        payload = run(root)
    except VisionConfigurationError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

