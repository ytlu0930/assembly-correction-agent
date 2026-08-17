import hashlib
from pathlib import Path

import numpy as np
from PIL import Image

from assembly_agent.imaging import annotate_remove, normalized_bbox_to_pixels


def test_coordinate_conversion() -> None:
    assert normalized_bbox_to_pixels((100, 200, 900, 800), 200, 100) == (20, 20, 180, 80)


def test_annotation_preserves_source_and_pixels_outside_overlay(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    output = tmp_path / "annotated.png"
    Image.new("RGB", (200, 120), (20, 30, 40)).save(source, quality=95)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    result = annotate_remove(source, output, (300, 300, 600, 700))
    assert output.is_file() and output != source
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before == result.source_sha256_after
    original = Image.open(source).convert("RGB")
    annotated = Image.open(output).convert("RGB")
    x1, y1, x2, y2 = result.overlay_bounds
    for y in range(original.height):
        for x in range(original.width):
            if not (x1 <= x < x2 and y1 <= y < y2):
                assert annotated.getpixel((x, y)) == original.getpixel((x, y))


def test_annotation_refuses_source_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (10, 10)).save(source)
    try:
        annotate_remove(source, source, (100, 100, 200, 200))
    except ValueError as error:
        assert "must not overwrite" in str(error)
    else:
        raise AssertionError("source overwrite was not rejected")


def test_annotation_uses_exif_display_orientation(tmp_path: Path) -> None:
    source = tmp_path / "oriented.jpg"
    output = tmp_path / "annotated.png"
    stored = Image.fromarray(np.full((40, 80, 3), 255, dtype=np.uint8))
    exif = stored.getexif()
    exif[274] = 6
    stored.save(source, exif=exif)

    result = annotate_remove(source, output, (500, 100, 900, 400))

    assert (result.image_width, result.image_height) == (40, 80)
    assert Image.open(output).size == (40, 80)


def test_remove_arrow_extends_away_from_image_center(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "annotated.png"
    Image.new("RGB", (1000, 1000), "white").save(source)

    result = annotate_remove(source, output, (100, 400, 200, 600))

    # A target left of center must produce overlay pixels left of its box.
    assert result.overlay_bounds[0] < result.pixel_bbox[0]
