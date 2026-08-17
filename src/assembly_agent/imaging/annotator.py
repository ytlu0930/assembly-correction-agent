"""Deterministic overlays on original assembly pixels."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


@dataclass(frozen=True)
class AnnotationResult:
    output_path: str
    source_sha256_before: str
    source_sha256_after: str
    image_width: int
    image_height: int
    pixel_bbox: tuple[int, int, int, int]
    overlay_bounds: tuple[int, int, int, int]


def normalized_bbox_to_pixels(
    bbox: tuple[int, int, int, int], width: int, height: int
) -> tuple[int, int, int, int]:
    if width <= 0 or height <= 0:
        raise ValueError("image dimensions must be positive")
    x1, y1, x2, y2 = bbox
    if not (0 <= x1 < x2 <= 1000 and 0 <= y1 < y2 <= 1000):
        raise ValueError("bbox must be positive-area normalized 0..1000 xyxy")
    return (
        round(x1 * width / 1000), round(y1 * height / 1000),
        round(x2 * width / 1000), round(y2 * height / 1000),
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def annotate_remove(source_path: Path, output_path: Path, bbox: tuple[int, int, int, int]) -> AnnotationResult:
    source_path = source_path.resolve()
    output_path = output_path.resolve()
    if source_path == output_path:
        raise ValueError("annotation output must not overwrite the original source")
    before = _sha256(source_path)
    with Image.open(source_path) as opened:
        # Annotation coordinates refer to the displayed image plane. Apply EXIF
        # orientation before drawing so portrait phone photos share the same
        # coordinate system as localization candidates.
        base = ImageOps.exif_transpose(opened).convert("RGBA")
    width, height = base.size
    pixel_bbox = normalized_bbox_to_pixels(bbox, width, height)
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    line_width = max(4, round(min(width, height) * 0.008))
    draw.rectangle(pixel_bbox, outline=(220, 20, 20, 255), width=line_width)
    label = "1  REMOVE"
    font = ImageFont.load_default(size=max(18, round(min(width, height) * 0.025)))
    text_box = draw.textbbox((0, 0), label, font=font, stroke_width=1)
    text_width, text_height = text_box[2] - text_box[0], text_box[3] - text_box[1]
    label_x = max(0, min(pixel_bbox[0], width - text_width - 20))
    label_y = max(0, pixel_bbox[1] - text_height - 24)
    draw.rounded_rectangle(
        (label_x, label_y, label_x + text_width + 20, label_y + text_height + 16),
        radius=8, fill=(220, 20, 20, 230),
    )
    draw.text((label_x + 10, label_y + 8), label, fill="white", font=font, stroke_width=1)
    # Point away from the assembly/image center so REMOVE communicates taking
    # the selected part out of the model, rather than pushing it inward.
    bbox_cx = (pixel_bbox[0] + pixel_bbox[2]) / 2
    bbox_cy = (pixel_bbox[1] + pixel_bbox[3]) / 2
    dx, dy = bbox_cx - width / 2, bbox_cy - height / 2
    magnitude = math.hypot(dx, dy) or 1
    ux, uy = dx / magnitude, dy / magnitude
    half_w = (pixel_bbox[2] - pixel_bbox[0]) / 2
    half_h = (pixel_bbox[3] - pixel_bbox[1]) / 2
    edge_scale = min(
        half_w / abs(ux) if abs(ux) > 1e-9 else float("inf"),
        half_h / abs(uy) if abs(uy) > 1e-9 else float("inf"),
    )
    arrow_start = (round(bbox_cx + ux * edge_scale), round(bbox_cy + uy * edge_scale))
    arrow_length = max(80, round(min(width, height) * 0.12))
    arrow_end = (
        max(0, min(width - 1, round(arrow_start[0] + ux * arrow_length))),
        max(0, min(height - 1, round(arrow_start[1] + uy * arrow_length))),
    )
    draw.line((arrow_start, arrow_end), fill=(220, 20, 20, 255), width=line_width)
    perpendicular = (-uy, ux)
    arrow_base = (arrow_end[0] - ux * line_width * 4, arrow_end[1] - uy * line_width * 4)
    draw.polygon((arrow_end,
        (round(arrow_base[0] + perpendicular[0] * line_width * 2), round(arrow_base[1] + perpendicular[1] * line_width * 2)),
        (round(arrow_base[0] - perpendicular[0] * line_width * 2), round(arrow_base[1] - perpendicular[1] * line_width * 2))),
        fill=(220, 20, 20, 255))
    bounds = overlay.getbbox()
    if bounds is None:
        raise RuntimeError("annotation overlay is empty")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(base, overlay).convert("RGB").save(output_path, format="PNG")
    after = _sha256(source_path)
    if before != after:
        raise RuntimeError("original source image changed during annotation")
    return AnnotationResult(output_path.as_posix(), before, after, width, height, pixel_bbox, bounds)
