from __future__ import annotations

import pytest

from assembly_agent.dataset.filename_parser import LABEL_MAP, VIEWS, parse_source_path


def assembly_path(filename: str, directory: str, step: str = "step05") -> str:
    return f"raw_data/model08/{directory}/model08_{step}/{filename}"


def test_correct_filename_parsing_and_numeric_case() -> None:
    record = parse_source_path(assembly_path("model08_step02_correct-01_bottom_01.jpg", "normal", "step02"))
    assert record["parse_status"] == "valid"
    assert (record["model_id"], record["step_id"]) == ("model08", "step02")
    assert record["directory_label"] == "normal"
    assert record["raw_label"] == record["normalized_label"] == "correct"
    assert record["case_id"] == "01"
    assert record["view"] == "bottom"
    assert record["capture_id"] == "01"


@pytest.mark.parametrize("raw_label,normalized", LABEL_MAP.items())
def test_every_supported_label(raw_label: str, normalized: str) -> None:
    case_id = "01" if raw_label == "correct" else "A01"
    directory = "normal" if raw_label == "correct" else raw_label
    filename = f"model08_step05_{raw_label}-{case_id}_front_01.jpg"
    record = parse_source_path(assembly_path(filename, directory))
    assert record["normalized_label"] == normalized
    assert record["parse_status"] == "valid"


def test_error_case_must_be_letter_prefixed() -> None:
    record = parse_source_path(assembly_path("model08_step05_missingpart-01_front_01.jpg", "missingpart"))
    assert record["parse_status"] == "invalid"
    assert "invalid_case_id_for_label" in record["anomalies"]


def test_correct_case_must_be_numeric() -> None:
    record = parse_source_path(assembly_path("model08_step05_correct-A01_front_01.jpg", "normal"))
    assert record["parse_status"] == "invalid"


@pytest.mark.parametrize("view", VIEWS)
def test_all_six_views(view: str) -> None:
    filename = f"model08_step05_wrongpart-A01_{view}_01.jpg"
    assert parse_source_path(assembly_path(filename, "wrongpart"))["view"] == view


def test_multiple_capture_and_copy_suffix() -> None:
    record = parse_source_path(assembly_path("model08_step05_extrapart-A01_right_02 (2).jpg", "extrapart"))
    assert record["capture_id"] == "02"
    assert record["copy_suffix"] == " (2)"


def test_malformed_extension_tolerant_and_strict() -> None:
    path = assembly_path("model08_step05_correct-01_back_01.jpg_", "normal")
    tolerant = parse_source_path(path)
    strict = parse_source_path(path, tolerant=False)
    assert tolerant["parse_status"] == "warning"
    assert tolerant["extension"] == ".jpg_"
    assert tolerant["anomalies"] == ["malformed_extension"]
    assert strict["parse_status"] == "invalid"


def test_invalid_filename_rejected() -> None:
    record = parse_source_path("raw_data/model08/normal/model08_step01/not-an-image.jpg")
    assert record["parse_status"] == "invalid"
    assert record["anomalies"] == ["malformed_filename"]


def test_directory_filename_mismatch() -> None:
    record = parse_source_path(assembly_path("model08_step05_missingpart-A01_front_01.jpg", "wrongpart"))
    assert record["parse_status"] == "invalid"
    assert "directory_filename_mismatch" in record["anomalies"]


def test_part_descriptor_parsing() -> None:
    record = parse_source_path("raw_data/parts/part_PIN_RED_SHORT_02.jpg")
    assert record["parse_status"] == "valid"
    assert record["source_kind"] == "part_image"
    assert record["part_descriptor"] == "PIN_RED_SHORT"
    assert record["capture_id"] == "02"
