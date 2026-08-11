"""Deterministic overlays on original assembly pixels."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


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
        base = opened.convert("RGBA")
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
    arrow_start = (pixel_bbox[2], pixel_bbox[1])
    arrow_end = (min(width - 1, pixel_bbox[2] + max(40, width // 12)), max(0, pixel_bbox[1] - max(40, height // 12)))
    draw.line((arrow_start, arrow_end), fill=(220, 20, 20, 255), width=line_width)
    draw.polygon(
        (arrow_end, (arrow_end[0] - line_width * 3, arrow_end[1]), (arrow_end[0], arrow_end[1] + line_width * 3)),
        fill=(220, 20, 20, 255),
    )
    bounds = overlay.getbbox()
    if bounds is None:
        raise RuntimeError("annotation overlay is empty")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(base, overlay).convert("RGB").save(output_path, format="PNG")
    after = _sha256(source_path)
    if before != after:
        raise RuntimeError("original source image changed during annotation")
    return AnnotationResult(output_path.as_posix(), before, after, width, height, pixel_bbox, bounds)

