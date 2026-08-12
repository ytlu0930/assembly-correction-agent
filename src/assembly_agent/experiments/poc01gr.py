"""Faithful repository reproduction of the validated POC-01G-R proposals."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from assembly_agent.reference import CANONICAL_VIEWS

from .poc01f import _select_images, _write_json

EXPERIMENT = "POC-01G-R"
MAX_DIMENSION = 1200
LOWER_RED_1 = (0, 80, 55)
UPPER_RED_1 = (10, 255, 255)
LOWER_RED_2 = (168, 80, 55)
UPPER_RED_2 = (179, 255, 255)
OPEN_KERNEL_SIZE = (3, 3)
CLOSE_KERNEL_SIZE = (5, 5)
MIN_CONTOUR_AREA = 300.0
MAX_NORMALIZED_AREA = 0.025
MIN_DENSITY = 0.45
MAX_WIDTH_FRACTION = 0.25
MAX_HEIGHT_FRACTION = 0.25
EXPECTED_COUNTS = {"front": 6, "back": 5, "left": 6, "right": 8, "top": 7, "bottom": 7}


@dataclass(frozen=True)
class Proposal:
    candidate_id: str
    view: str
    source_record_id: str
    bbox_original_xyxy: tuple[int, int, int, int]
    bbox_coordinate_space: str
    contour_area_working: float
    density: float
    aspect_ratio: float
    working_scale: float


def working_scale(original_height: int, original_width: int) -> float:
    if original_height <= 0 or original_width <= 0:
        raise ValueError("image dimensions must be positive")
    return MAX_DIMENSION / max(original_height, original_width)


def working_image(original: np.ndarray) -> tuple[np.ndarray, float]:
    height, width = original.shape[:2]
    scale = working_scale(height, width)
    return cv2.resize(original, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA), scale


def red_mask(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask1 = cv2.inRange(hsv, LOWER_RED_1, UPPER_RED_1)
    mask2 = cv2.inRange(hsv, LOWER_RED_2, UPPER_RED_2)
    mask = cv2.bitwise_or(mask1, mask2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones(OPEN_KERNEL_SIZE, np.uint8))
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones(CLOSE_KERNEL_SIZE, np.uint8))


def contour_is_candidate(area: float, x: int, y: int, width: int, height: int, image_width: int, image_height: int) -> bool:
    del x, y
    if width <= 0 or height <= 0 or area < MIN_CONTOUR_AREA:
        return False
    if area / (image_height * image_width) > MAX_NORMALIZED_AREA:
        return False
    if area / (width * height) < MIN_DENSITY:
        return False
    return width <= MAX_WIDTH_FRACTION * image_width and height <= MAX_HEIGHT_FRACTION * image_height


def resized_xywh_to_original_xyxy(x: int, y: int, width: int, height: int, scale: float) -> tuple[int, int, int, int]:
    if width <= 0 or height <= 0 or scale <= 0:
        raise ValueError("bbox dimensions and scale must be positive")
    inverse_scale = 1 / scale
    return (round(x * inverse_scale), round(y * inverse_scale),
            round((x + width) * inverse_scale), round((y + height) * inverse_scale))


def propose(image_path: Path, view: str, source_record_id: str) -> tuple[Proposal, ...]:
    original = cv2.imread(str(image_path))
    if original is None:
        raise ValueError(f"cannot read Current image: {image_path}")
    resized, scale = working_image(original)
    mask = red_mask(resized)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    accepted: list[tuple[float, int, int, int, int, float, float]] = []
    height, width = resized.shape[:2]
    for contour in contours:
        area = float(cv2.contourArea(contour))
        x, y, box_width, box_height = cv2.boundingRect(contour)
        if contour_is_candidate(area, x, y, box_width, box_height, width, height):
            density = area / (box_width * box_height)
            aspect = max(box_width / box_height, box_height / box_width)
            accepted.append((area, x, y, box_width, box_height, density, aspect))
    accepted.sort(key=lambda item: (-item[0], item[2], item[1], item[4], item[3]))
    return tuple(Proposal(
        f"current_{view}_candidate_{index:03d}", view, source_record_id,
        resized_xywh_to_original_xyxy(x, y, box_width, box_height, scale), "original_image_xyxy",
        area, density, aspect, scale,
    ) for index, (area, x, y, box_width, box_height, density, aspect) in enumerate(accepted, start=1))


def load_agent_descriptor(root: Path) -> str:
    payload = json.loads((root / "outputs/poc01fb/raw_diagnosis.json").read_text(encoding="utf-8"))
    parts = payload.get("suspected_parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError("persisted POC-01F-B prediction has no suspected part")
    return parts[0]["descriptor"]


def _visualize(image_path: Path, proposals: tuple[Proposal, ...], output_path: Path) -> None:
    image = cv2.imread(str(image_path))
    for proposal in proposals:
        x1, y1, x2, y2 = proposal.bbox_original_xyxy
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 255), 8)
        cv2.putText(image, proposal.candidate_id, (x1, max(30, y1 - 12)), cv2.FONT_HERSHEY_SIMPLEX,
                    1.2, (0, 255, 255), 3, cv2.LINE_AA)
    cv2.imwrite(str(output_path), image, [cv2.IMWRITE_JPEG_QUALITY, 92])


def run(root: Path, output_dir: Path | None = None) -> dict[str, Any]:
    output_dir = output_dir or root / "outputs/poc01gr"
    visualization_dir = output_dir / "visualizations"
    visualization_dir.mkdir(parents=True, exist_ok=True)
    descriptor = load_agent_descriptor(root)
    current, _ = _select_images(root)
    all_proposals: list[Proposal] = []
    counts: dict[str, int] = {}
    for selected in current:
        proposals = propose(selected.path, selected.view, selected.record_id)
        counts[selected.view] = len(proposals)
        all_proposals.extend(proposals)
        _visualize(selected.path, proposals, visualization_dir / f"{selected.view}_candidates.jpg")
    manifest = {"experiment": EXPERIMENT, "descriptor": descriptor,
                "candidates": [asdict(proposal) for proposal in all_proposals]}
    _write_json(output_dir / "candidate_manifest.json", manifest)
    audit = {"experiment": EXPERIMENT, "upstream_hypothesis_source": "outputs/poc01fb/raw_diagnosis.json",
        "descriptor": descriptor, "descriptor_source": "agent_generated", "human_gt_used": False,
        "correct_reference_used": False, "structural_location_prose_used": False, "gemini_calls": 0,
        "working_max_dimension": MAX_DIMENSION, "candidate_counts": counts,
        "candidate_total": len(all_proposals),
        "maximum_candidate_aspect_ratio": max(proposal.aspect_ratio for proposal in all_proposals),
        "minimum_candidate_density": min(proposal.density for proposal in all_proposals),
        "p1_objectness": "pending_human_validation", "p2_visible_recall": "pending_human_validation"}
    _write_json(output_dir / "proposal_audit.json", audit)
    if counts != EXPECTED_COUNTS:
        raise RuntimeError(f"POC01GR_REPRODUCTION_MISMATCH: expected {EXPECTED_COUNTS}, got {counts}")
    return audit


if __name__ == "__main__":
    print(json.dumps(run(Path(__file__).resolve().parents[3]), indent=2))

