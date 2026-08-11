import hashlib
from pathlib import Path

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
