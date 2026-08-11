"""Open-vocabulary candidate detection using the official Transformers Grounding DINO model."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image


@dataclass(frozen=True)
class GroundingCandidate:
    candidate_id: str
    bbox: tuple[int, int, int, int]
    score: float
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GroundingResult:
    query: str
    threshold: float
    image_size: tuple[int, int]
    candidates: tuple[GroundingCandidate, ...]
    source: str

    def __post_init__(self) -> None:
        width, height = self.image_size
        ids = [item.candidate_id for item in self.candidates]
        if len(ids) != len(set(ids)) or any(not item for item in ids):
            raise ValueError("grounding candidate IDs must be non-empty and unique")
        for candidate in self.candidates:
            _validate_bbox(candidate.bbox, width, height)
            if not 0 <= candidate.score <= 1:
                raise ValueError("grounding score must be within 0..1")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_grounding_query(descriptor: str, catalog_description: str | None = None) -> str:
    """Build an object-only query without task/error/location hints."""
    name = descriptor.lower().replace("_", " ").strip()
    description = " ".join((catalog_description or "").lower().split())
    forbidden = ("extra", "wrong", "incorrect", "remove", "location", "left", "right", "top", "bottom")
    if any(word in name or word in description for word in forbidden):
        description = ""
    return f"{name}. {description}." if description else f"{name}."


def _validate_bbox(box: tuple[int, int, int, int], width: int, height: int) -> None:
    x1, y1, x2, y2 = box
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError("grounded bbox must be positive-area pixel xyxy within the source image")


class GroundingDinoDetector:
    """Lazy CPU-compatible adapter; model dependencies are optional until invoked."""

    def __init__(self, *, model_id: str = "IDEA-Research/grounding-dino-tiny", threshold: float = 0.18) -> None:
        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be within 0..1")
        self.model_id = model_id
        self.threshold = threshold
        self._processor = None
        self._model = None

    def _load(self):
        if self._processor is None:
            try:
                from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
            except ImportError as error:
                raise RuntimeError("Grounding DINO requires the optional grounding dependencies") from error
            self._processor = AutoProcessor.from_pretrained(self.model_id)
            self._model = AutoModelForZeroShotObjectDetection.from_pretrained(self.model_id)
            self._model.eval()
        return self._processor, self._model

    def detect_candidates(
        self, image_path: Path, target_descriptor: str, textual_description: str | None = None
    ) -> GroundingResult:
        import torch

        query = build_grounding_query(target_descriptor, textual_description)
        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        processor, model = self._load()
        inputs = processor(images=image, text=query, return_tensors="pt")
        with torch.inference_mode():
            outputs = model(**inputs)
        processed = processor.post_process_grounded_object_detection(
            outputs, inputs.input_ids, threshold=self.threshold, text_threshold=self.threshold,
            target_sizes=[(height, width)],
        )[0]
        raw = []
        for box, score in zip(processed["boxes"], processed["scores"], strict=True):
            coords = tuple(int(round(float(value))) for value in box.tolist())
            coords = (max(0, coords[0]), max(0, coords[1]), min(width, coords[2]), min(height, coords[3]))
            _validate_bbox(coords, width, height)
            raw.append((coords, float(score)))
        raw.sort(key=lambda item: (-item[1], item[0]))
        candidates = tuple(
            GroundingCandidate(f"grounded_{index:03d}", box, score, f"grounding_dino:{self.model_id}")
            for index, (box, score) in enumerate(raw, start=1)
        )
        return GroundingResult(query, self.threshold, (width, height), candidates, f"grounding_dino:{self.model_id}")
