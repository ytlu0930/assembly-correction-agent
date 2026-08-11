from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from assembly_agent.vision.gemini import (
    GeminiRequest,
    GeminiVisionAdapter,
    InlineImage,
    VisionProviderError,
    build_gemini_request,
)
from assembly_agent.vision.schemas import COORDINATE_SPACE, VisionAnalysis


DESCRIPTORS = {"PIN_RED_SHORT", "EYE_BALL"}


def payload(**overrides):
    value = {
        "status": "error", "error_type": "extra_part",
        "actual_part": {"descriptor": "PIN_RED_SHORT", "description": "a red pin"},
        "location": {"coordinate_space": COORDINATE_SPACE, "region": "center", "bbox": [100, 200, 300, 400], "point": [200, 300]},
        "confidence": 0.9, "evidence_summary": "Visible only in the current image.",
    }
    value.update(overrides)
    return value


def test_schema_accepts_valid_response_and_rejects_invented_descriptor() -> None:
    analysis = VisionAnalysis.from_dict(payload(), DESCRIPTORS)
    assert analysis.location.bbox == (100, 200, 300, 400)
    invented = payload(actual_part={"descriptor": "INVENTED_PART", "description": None})
    with pytest.raises(ValueError, match="candidate vocabulary"):
        VisionAnalysis.from_dict(invented, DESCRIPTORS)


@pytest.mark.parametrize("bbox", [[-1, 0, 2, 3], [20, 20, 10, 30], [0, 0, 1001, 20]])
def test_schema_rejects_invalid_coordinates(bbox) -> None:
    value = payload()
    value["location"] = {**value["location"], "bbox": bbox}
    with pytest.raises(ValueError, match="bbox"):
        VisionAnalysis.from_dict(value, DESCRIPTORS)


def test_request_contains_only_neutral_metadata_and_full_candidate_vocabulary(tmp_path: Path) -> None:
    paths = []
    for name in ("current", "reference", "part_a", "part_b"):
        path = tmp_path / f"{name}.jpg"
        Image.new("RGB", (4, 4), "white").save(path)
        paths.append(path)
    request = build_gemini_request(paths[0], paths[1], [("PIN_RED_SHORT", paths[2]), ("EYE_BALL", paths[3])])
    serialized_metadata = repr(request.metadata).lower()
    assert "extrapart" not in request.prompt.lower()
    assert "extra_part" not in request.prompt.lower()
    assert "raw_data" not in request.prompt and "raw_data" not in serialized_metadata
    assert request.part_descriptors == ("EYE_BALL", "PIN_RED_SHORT")
    assert request.prompt.count("PIN_RED_SHORT") == 1
    assert set(request.metadata) == {"current_image_id", "reference_image_id", "part_reference_ids"}
    assert "bbox" not in request.prompt.lower()
    assert "normalized_0_1000" not in request.prompt.lower()
    assert "x_min" not in request.prompt.lower()
    assert "left hole" not in request.prompt.lower()
    assert "target location" not in request.prompt.lower()


def adapter_request() -> GeminiRequest:
    image = InlineImage("neutral_image", "image/jpeg", b"image")
    return GeminiRequest(
        prompt="compare",
        current_image=image,
        reference_image=image,
        part_images=(),
        part_descriptors=("PIN_RED_SHORT",),
        metadata={},
    )


def test_sync_client_stays_open_through_request_and_closes_afterward(monkeypatch) -> None:
    from google import genai

    events = []

    class Models:
        def generate_content(self, **kwargs):
            events.append("generate")
            assert events == ["create", "generate"]
            return type("Response", (), {"parsed": payload(), "text": None})()

    class Client:
        def __init__(self, **kwargs):
            events.append("create")
            self.models = Models()

        def close(self):
            events.append("close")

    monkeypatch.setattr(genai, "Client", Client)
    result = GeminiVisionAdapter("test-key", "test-model").analyze(adapter_request())

    assert result.error_type == "extra_part"
    assert events == ["create", "generate", "close"]


def test_sync_client_closes_after_request_exception(monkeypatch) -> None:
    from google import genai

    events = []

    class Models:
        def generate_content(self, **kwargs):
            events.append("generate")
            raise RuntimeError("provider failure")

    class Client:
        def __init__(self, **kwargs):
            events.append("create")
            self.models = Models()

        def close(self):
            events.append("close")

    monkeypatch.setattr(genai, "Client", Client)
    with pytest.raises(VisionProviderError, match="provider failure"):
        GeminiVisionAdapter("test-key", "test-model").analyze(adapter_request())

    assert events == ["create", "generate", "close"]


