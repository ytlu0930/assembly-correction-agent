from __future__ import annotations

import hashlib
import json
from pathlib import Path

from assembly_agent.dataset.manifest import build_dataset, write_artifacts


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_manifest_keeps_physical_records_and_detects_duplicate_hashes(tmp_path: Path) -> None:
    front = tmp_path / "raw_data/model08/normal/model08_step01/model08_step01_correct-01_front_01.jpg"
    back = tmp_path / "raw_data/model08/normal/model08_step01/model08_step01_correct-01_back_01.jpg"
    part = tmp_path / "raw_data/parts/part_EYE_BALL_01.jpg"
    write_bytes(front, b"same image")
    write_bytes(back, b"same image")
    write_bytes(part, b"part image")

    records, cases, report = build_dataset(tmp_path)
    assert len(records) == 3
    assert len({item["record_id"] for item in records}) == 3
    assert report["assembly_images"] == 2
    assert report["part_images"] == 1
    assert len(report["duplicate_hashes"]) == 1
    assert report["cross_view_duplicate_content_cases"] == ["model08|step01|correct|01"]
    assert "duplicate_content_across_views" in cases[0]["data_quality_flags"]


def test_artifacts_are_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "raw_data/model08/wrongpart/model08_step05/model08_step05_wrongpart-A01_top_01.jpg"
    write_bytes(source, b"image")
    output = tmp_path / "data"
    write_artifacts(tmp_path, output)
    first = {path.name: path.read_bytes() for path in output.iterdir()}
    write_artifacts(tmp_path, output)
    second = {path.name: path.read_bytes() for path in output.iterdir()}
    assert first == second


def test_generated_jsonl_and_audit_are_readable(tmp_path: Path) -> None:
    source = tmp_path / "raw_data/parts/part_WHEEL_BLUE_LARGE_01.jpg"
    write_bytes(source, b"wheel")
    report = write_artifacts(tmp_path)
    manifest_line = (tmp_path / "data/dataset_manifest.jsonl").read_text().strip()
    assert json.loads(manifest_line)["sha256"] == hashlib.sha256(b"wheel").hexdigest()
    assert json.loads((tmp_path / "data/dataset_audit_report.json").read_text()) == report
