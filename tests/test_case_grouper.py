from __future__ import annotations

from assembly_agent.dataset.case_grouper import group_cases


def record(view: str, capture: str = "01", *, record_id: str | None = None, digest: str | None = None):
    return {
        "record_id": record_id or f"record-{view}-{capture}",
        "source_path": f"raw_data/{view}-{capture}.jpg",
        "source_kind": "assembly_image",
        "parse_status": "valid",
        "case_key": "model08|step05|missing_part|A01",
        "view": view,
        "capture_id": capture,
        "sha256": digest or f"hash-{view}-{capture}",
        "anomalies": [],
    }


def test_case_grouping_and_incomplete_views() -> None:
    cases, collisions = group_cases([record("front"), record("left")])
    assert collisions == []
    assert len(cases) == 1
    assert cases[0]["available_views"] == ["front", "left"]
    assert cases[0]["missing_views"] == ["back", "bottom", "right", "top"]
    assert "incomplete_views" in cases[0]["data_quality_flags"]


def test_multiple_captures_per_view() -> None:
    cases, _ = group_cases([record("back", "01"), record("back", "02")])
    assert cases[0]["captures_per_view"]["back"] == ["01", "02"]


def test_semantic_key_collision_is_reported_without_overwrite() -> None:
    records = [record("front", record_id="one", digest="hash-one"), record("front", record_id="two", digest="hash-two")]
    cases, collisions = group_cases(records)
    assert collisions == [{
        "semantic_image_key": "model08|step05|missing_part|A01|front|01",
        "record_ids": ["one", "two"],
    }]
    assert cases[0]["source_record_ids"] == ["one", "two"]
    assert "semantic_key_collision" in cases[0]["data_quality_flags"]


def test_duplicate_content_across_views() -> None:
    cases, _ = group_cases([record("front", digest="same"), record("back", digest="same")])
    assert "duplicate_content_across_views" in cases[0]["data_quality_flags"]
