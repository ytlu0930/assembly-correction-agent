"""Deterministic coordinate transforms and geometry audit for POC-01H candidates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from assembly_agent.reference import CANONICAL_VIEWS

from .poc01f import _select_images, _write_json

XYXY = "original_image_xyxy"
CONTEXT_XYXY = "context_crop_original_xyxy"
LOCAL_XYXY = "context_crop_local_xyxy"
RENDERED_XYXY = "context_rendered_xyxy"


def _box(value: Iterable[int | float], name: str) -> tuple[float, float, float, float]:
    try:
        box = tuple(value)
    except TypeError as error:
        raise ValueError(f"{name} must contain four numeric xyxy values") from error
    if len(box) != 4 or any(type(item) not in (int, float) for item in box):
        raise ValueError(f"{name} must contain four numeric xyxy values")
    x1, y1, x2, y2 = box
    if x1 >= x2 or y1 >= y2:
        raise ValueError(f"{name} must have positive area in xyxy order")
    return float(x1), float(y1), float(x2), float(y2)


def xywh_to_xyxy(value: Iterable[int | float]) -> tuple[float, float, float, float]:
    x, y, width, height = _box((lambda items: (items[0], items[1], items[0] + items[2], items[1] + items[3]))(tuple(value)), "xywh")
    return x, y, width, height


def xyxy_to_xywh(value: Iterable[int | float]) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = _box(value, "xyxy")
    return x1, y1, x2 - x1, y2 - y1


def clip_xyxy(value: Iterable[int | float], size: tuple[int, int]) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = _box(value, "bbox")
    width, height = size
    clipped = max(0, round(x1)), max(0, round(y1)), min(width, round(x2)), min(height, round(y2))
    _box(clipped, "clipped bbox")
    return clipped


def original_to_context_local(
    original_bbox: Iterable[int | float], context_crop: Iterable[int | float]
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = _box(original_bbox, "original bbox")
    cx1, cy1, cx2, cy2 = _box(context_crop, "context crop")
    if x1 < cx1 or y1 < cy1 or x2 > cx2 or y2 > cy2:
        raise ValueError("original bbox must be contained by context crop")
    return round(x1 - cx1), round(y1 - cy1), round(x2 - cx1), round(y2 - cy1)


def context_local_to_rendered(
    local_bbox: Iterable[int | float], crop_size: tuple[int, int], render_size: tuple[int, int]
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = _box(local_bbox, "context-local bbox")
    crop_width, crop_height = crop_size
    render_width, render_height = render_size
    if min(crop_width, crop_height, render_width, render_height) <= 0:
        raise ValueError("crop and render sizes must be positive")
    scale_x, scale_y = render_width / crop_width, render_height / crop_height
    rendered = round(x1 * scale_x), round(y1 * scale_y), round(x2 * scale_x), round(y2 * scale_y)
    return clip_xyxy(rendered, render_size)


def context_bounds(original_bbox: Iterable[int | float], image_size: tuple[int, int], factor: float = 5.0) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = _box(original_bbox, "original bbox")
    width, height = image_size
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    half_width = max(16, (x2 - x1) * factor / 2)
    half_height = max(16, (y2 - y1) * factor / 2)
    return clip_xyxy((max(0, int(cx - half_width)), max(0, int(cy - half_height)),
                      min(width, int(cx + half_width)), min(height, int(cy + half_height))), image_size)


@dataclass(frozen=True)
class GeometryRecord:
    candidate_id: str
    view: str
    source_record_id: str
    coordinate_spaces: dict[str, str]
    bbox_original_xyxy: tuple[int, int, int, int]
    context_crop_original_xyxy: tuple[int, int, int, int]
    bbox_context_local_xyxy: tuple[int, int, int, int]
    context_render_size: tuple[int, int]
    bbox_rendered_xyxy: tuple[int, int, int, int]
    context_image_path: str


def _marker(image: Image.Image, bbox: tuple[int, int, int, int], candidate_id: str) -> None:
    draw = ImageDraw.Draw(image)
    width = max(2, round(min(image.size) / 150))
    draw.rectangle(bbox, outline=(255, 255, 0), width=width)
    draw.text((4, 4), candidate_id, fill=(255, 255, 0), stroke_width=2, stroke_fill=(0, 0, 0))


def run_geometry_audit(root: Path, output_dir: Path | None = None) -> dict:
    output_dir = output_dir or root / "outputs/poc01h_geometry"
    original_dir, context_dir = output_dir / "original_candidates", output_dir / "context_candidates"
    original_dir.mkdir(parents=True, exist_ok=True)
    context_dir.mkdir(parents=True, exist_ok=True)
    persisted = json.loads((root / "outputs/poc01h/candidate_manifest.json").read_text(encoding="utf-8"))["candidates"]
    current, _ = _select_images(root)
    by_view = {image.view: image for image in current}
    records: list[GeometryRecord] = []
    pixel_failures = out_of_bounds = invalid = 0
    for view in CANONICAL_VIEWS:
        selected = by_view[view]
        with Image.open(selected.path) as source:
            original = ImageOps.exif_transpose(source).convert("RGB")
        debug = original.copy()
        for item in (entry for entry in persisted if entry["view"] == view):
            try:
                bbox = clip_xyxy(item["bbox_original_xyxy"], original.size)
                crop_box = context_bounds(bbox, original.size)
                local = original_to_context_local(bbox, crop_box)
                context = original.crop(crop_box)
                render_size = context.size
                rendered = context_local_to_rendered(local, context.size, render_size)
                original_pixels = np.asarray(original.crop(bbox))
                context_pixels = np.asarray(context.crop(local))
                if not np.array_equal(original_pixels, context_pixels):
                    pixel_failures += 1
                if not (0 <= rendered[0] < rendered[2] <= render_size[0] and 0 <= rendered[1] < rendered[3] <= render_size[1]):
                    out_of_bounds += 1
                _marker(debug, bbox, item["candidate_id"])
                _marker(context, rendered, item["candidate_id"])
                context_path = context_dir / f"{item['candidate_id']}_context.jpg"
                context.save(context_path, quality=95)
                try:
                    context_record = context_path.relative_to(root).as_posix()
                except ValueError:
                    context_record = context_path.as_posix()
                records.append(GeometryRecord(item["candidate_id"], view, item["source_record_id"],
                    {"bbox_original_xyxy": XYXY, "context_crop_original_xyxy": CONTEXT_XYXY,
                     "bbox_context_local_xyxy": LOCAL_XYXY, "bbox_rendered_xyxy": RENDERED_XYXY},
                    bbox, crop_box, local, render_size, rendered, context_record))
            except (ValueError, TypeError):
                invalid += 1
        debug.save(original_dir / f"{view}_original_candidates.png", compress_level=1)
    _write_json(output_dir / "candidate_geometry_manifest.json", {"candidates": [record.__dict__ for record in records]})
    failures = []
    if pixel_failures:
        failures.append("B. CROP_COORDINATE_TRANSFORM_WRONG")
    if out_of_bounds:
        failures.append("C. RESIZE_COORDINATE_TRANSFORM_WRONG")
    if invalid:
        failures.append("A. ORIGINAL_CANDIDATE_BBOX_WRONG")
    report = {"candidate_count": len(records), "pixel_fidelity_failures": pixel_failures,
              "out_of_bounds_failures": out_of_bounds, "invalid_bbox_failures": invalid,
              "failure_classification": failures, "gemini_calls": 0}
    _write_json(output_dir / "geometry_audit_report.json", report)
    if pixel_failures or out_of_bounds or invalid:
        raise RuntimeError("GEOMETRY_VALIDATION_FAILURE")
    return report


if __name__ == "__main__":
    print(json.dumps(run_geometry_audit(Path(__file__).resolve().parents[3]), indent=2))
