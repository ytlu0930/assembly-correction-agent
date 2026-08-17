"""Round 02: blind six-view diagnosis of Model03 Step03 case A01."""

from __future__ import annotations

import json
import os
from pathlib import Path

from assembly_agent.reference import CANONICAL_VIEWS, ReferenceRepository

from .poc01f import SelectedImage, _load_dotenv, _load_jsonl, _write_json
from .instance_matching import diagnose, inventory_schema, matching_schema, validate_inventory
from .poc01fb import load_catalog_descriptors

EXPERIMENT = "ROUND-02-INSTANCE-MATCHING-V4"
MODEL_ID = "model03"
STEP_ID = "step03"
CASE_ID = "A01"


def select_images(root: Path) -> tuple[SelectedImage, ...]:
    rows = _load_jsonl(root / "data/dataset_manifest.jsonl")
    current = []
    for view in CANONICAL_VIEWS:
        matches = [row for row in rows if row.get("model_id") == MODEL_ID
                   and row.get("step_id") == STEP_ID and row.get("normalized_label") == "wrong_part"
                   and row.get("case_id") == CASE_ID and row.get("view") == view]
        row = sorted(matches, key=lambda item: (item["capture_id"], item["source_path"], item["record_id"]))[0]
        current.append(SelectedImage("current", view, f"current_{view}", root / row["source_path"],
                                     row["record_id"], row["capture_id"], row["source_path"]))
    repository = ReferenceRepository(root)
    reference = []
    for view in CANONICAL_VIEWS:
        capture = sorted(repository.get_reference_view(MODEL_ID, STEP_ID, "01", view).captures,
                         key=lambda item: (item.capture_id, item.source_path, item.record_id))[0]
        reference.append(SelectedImage("reference", view, f"reference_{view}", root / capture.source_path,
                                       capture.record_id, capture.capture_id, capture.source_path))
    return tuple(current + reference)


def run(root: Path) -> dict:
    from google import genai
    from google.genai import types

    output = root / "outputs/round02/instance_matching_v4"
    output.mkdir(parents=True, exist_ok=True)
    images = select_images(root)
    descriptors = load_catalog_descriptors(root)
    audit = {
        "experiment": EXPERIMENT, "model_id": MODEL_ID, "step_id": STEP_ID,
        "case_id": CASE_ID, "image_ids": [image.neutral_id for image in images],
        "record_ids": [image.record_id for image in images], "ground_truth_exposed": False,
        "dataset_label_exposed": False, "human_annotation_exposed": False,
        "stages": ["current_inventory", "reference_inventory", "instance_matching", "deterministic_diagnosis"],
    }
    _write_json(output / "request_audit.json", audit)
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=types.HttpOptions(timeout=120_000))
    inventories = {}
    try:
        for role in ("current", "reference"):
            role_images = [image for image in images if image.role == role]
            combined_instances = []
            batches = [descriptors[index:index + 5] for index in range(0, len(descriptors), 5)]
            for batch_index, batch in enumerate(batches, start=1):
                batch_path = output / f"{role}_inventory_batch_{batch_index}.json"
                if batch_path.exists():
                    cached = json.loads(batch_path.read_text(encoding="utf-8"))
                    combined_instances.extend(cached["instances"])
                    continue
                prompt = f"""Inventory one physical assembly from six views, but report ONLY instances whose descriptor is
in the supplied batch. Build one record per physical 3D part instance and deduplicate it across views. Do not compare
assemblies, diagnose errors, or infer expected state. Use every relevant view to recover occluded instances.
IDs must be unique and start with {role}_. Batch descriptors: {json.dumps(batch)}.
attachment_anchor must describe structural attachment, not image-left/right."""
                contents = [prompt]
                for image in role_images:
                    contents.extend([image.neutral_id, types.Part.from_bytes(data=image.path.read_bytes(), mime_type="image/jpeg")])
                response = None
                for attempt in range(1, 4):
                    response = client.models.generate_content(model="gemini-3.1-pro-preview", contents=contents,
                        config=types.GenerateContentConfig(temperature=0, max_output_tokens=16384, response_mime_type="application/json",
                                                           response_json_schema=inventory_schema(batch)))
                    if isinstance(response.parsed, dict):
                        break
                    (output / f"{role}_inventory_batch_{batch_index}_attempt_{attempt}_invalid.txt").write_text(
                        response.text or "", encoding="utf-8")
                if response is None or not isinstance(response.parsed, dict):
                    raise ValueError(f"{role} inventory batch {batch_index} failed three structured-output attempts")
                _write_json(batch_path, response.parsed)
                combined_instances.extend(response.parsed["instances"])
            inventory = {"instances": combined_instances}
            validate_inventory(inventory, role)
            inventories[role] = inventory
            _write_json(output / f"{role}_inventory.json", inventory)

        match_prompt = f"""Match Current and Reference physical part instances one-to-one by descriptor, attachment anchor,
neighbors, and 3D structural role. Camera-relative left/right is not identity. Cover every supplied ID exactly once,
either in matches or the appropriate unmatched list. Use identity_mismatch only for the same structural slot with
different descriptors, and attachment_mismatch only for the same physical role with different attachment.
CURRENT_INVENTORY={json.dumps(inventories['current'])}
REFERENCE_INVENTORY={json.dumps(inventories['reference'])}"""
        response = client.models.generate_content(model="gemini-3.1-pro-preview", contents=match_prompt,
            config=types.GenerateContentConfig(temperature=0, max_output_tokens=32768, response_mime_type="application/json",
                                               response_json_schema=matching_schema()))
        if not isinstance(response.parsed, dict):
            (output / "matching_invalid_response.txt").write_text(response.text or "", encoding="utf-8")
            raise ValueError("instance matching response was not complete structured JSON")
        matching = response.parsed
        _write_json(output / "instance_matching.json", matching)
        prediction = diagnose(inventories["current"], inventories["reference"], matching)
    finally:
        client.close()
    _write_json(output / "deterministic_diagnosis.json", prediction)
    result = {"experiment": EXPERIMENT, "prediction": prediction, "evaluation_status": "pending_human_gt_comparison"}
    _write_json(output / "experiment_result.json", result)
    return result


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[3]
    _load_dotenv(root / ".env")
    print(json.dumps(run(root), ensure_ascii=False, indent=2))
