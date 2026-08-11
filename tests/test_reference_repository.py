from __future__ import annotations

import json
from pathlib import Path

import pytest

from assembly_agent.reference import (
    DEFAULT_CASE_SELECTION_RULE,
    ReferenceNotFoundError,
    ReferenceRepository,
)


@pytest.fixture(scope="module")
def repository() -> ReferenceRepository:
    return ReferenceRepository(Path(__file__).parents[1])


def test_indexed_model_steps_and_sop_mapping_are_deterministic(repository: ReferenceRepository) -> None:
    assert repository.indexed_model_steps() == {
        "model03": ("step01", "step02", "step03"),
        "model08": ("step01", "step02", "step03", "step04", "step05"),
    }
    assert repository.get_sop_reference("model03") == "references/sop/3號車車組裝SOP.jpg"
    assert repository.get_sop_reference("model08") == "references/sop/8號車車組裝SOP.jpg"


def test_only_correct_manifest_images_enter_repository(repository: ReferenceRepository) -> None:
    root = Path(__file__).parents[1]
    records = [json.loads(line) for line in (root / "data/dataset_manifest.jsonl").read_text().splitlines()]
    by_id = {record["record_id"]: record for record in records}
    returned_ids: list[str] = []
    for model_id, steps in repository.indexed_model_steps().items():
        for step_id in steps:
            for case in repository.get_reference_cases(model_id, step_id):
                returned_ids.extend(case.reference_image_record_ids)
                assert case.normalized_label == "correct"
                assert all(by_id[record_id]["normalized_label"] == "correct" for record_id in case.reference_image_record_ids)
                assert case.reference_image_paths == tuple(by_id[record_id]["source_path"] for record_id in case.reference_image_record_ids)
    expected = {record["record_id"] for record in records if record["normalized_label"] == "correct"}
    assert set(returned_ids) == expected
    assert len(returned_ids) == len(set(returned_ids))


def test_multiple_correct_cases_are_explicit_and_default_is_disclosed(repository: ReferenceRepository) -> None:
    cases = repository.get_reference_cases("model08", "step01")
    assert [case.case_id for case in cases] == ["01", "02", "03"]
    package = repository.get_reference("model08", "step01")
    assert package.cases == cases
    assert package.selected_case_id == "01"
    assert package.selected_case is cases[0]
    assert package.default_case_selection_rule == DEFAULT_CASE_SELECTION_RULE


def test_missing_views_multiple_captures_and_warnings_are_preserved(repository: ReferenceRepository) -> None:
    incomplete = repository.get_reference_case("model08", "step01", "01")
    assert incomplete.available_views == ("front", "left", "top")
    assert incomplete.missing_views == ("back", "right", "bottom")
    assert "incomplete_views" in incomplete.data_quality_flags

    multiple = repository.get_reference_case("model03", "step03", "01")
    assert dict(multiple.captures_per_view)["back"] == ("01", "02", "03")
    assert len(repository.get_reference_view("model03", "step03", "01", "back").captures) == 3

    anomalous = repository.get_reference_case("model08", "step01", "03")
    assert "malformed_extension" in anomalous.data_quality_flags


def test_reference_package_contains_traceability_sources(repository: ReferenceRepository) -> None:
    package = repository.get_reference("model03", "step03")
    assert package.model_id == "model03"
    assert package.step_id == "step03"
    assert package.sop_reference_path == "references/sop/3號車車組裝SOP.jpg"
    assert package.part_catalog.path == "data/part_catalog.json"
    assert package.part_catalog.version == "1.0"
    assert len(package.selected_case.reference_image_record_ids) == 8
    assert len(package.selected_case.reference_image_paths) == 8


@pytest.mark.parametrize(
    "operation",
    [
        lambda repository: repository.get_reference("model99", "step01"),
        lambda repository: repository.get_reference("model03", "step99"),
        lambda repository: repository.get_reference_case("model03", "step03", "99"),
        lambda repository: repository.get_reference_view("model08", "step01", "01", "back"),
        lambda repository: repository.get_reference_view("model03", "step03", "01", "diagonal"),
    ],
)
def test_unsupported_reference_requests_are_explicit(repository: ReferenceRepository, operation) -> None:
    with pytest.raises(ReferenceNotFoundError):
        operation(repository)


def test_repeated_resolution_is_identical(repository: ReferenceRepository) -> None:
    assert repository.get_reference("model08", "step01") == repository.get_reference("model08", "step01")
    assert repository.get_reference_cases("model03", "step03") == repository.get_reference_cases("model03", "step03")
