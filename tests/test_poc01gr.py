from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from assembly_agent.experiments import poc01gr


def test_constants_scaling_mask_and_morphology() -> None:
    assert poc01gr.working_scale(6928, 6928) == 1200 / 6928
    assert (poc01gr.LOWER_RED_1, poc01gr.UPPER_RED_1) == ((0, 80, 55), (10, 255, 255))
    assert (poc01gr.LOWER_RED_2, poc01gr.UPPER_RED_2) == ((168, 80, 55), (179, 255, 255))
    assert (poc01gr.OPEN_KERNEL_SIZE, poc01gr.CLOSE_KERNEL_SIZE) == ((3, 3), (5, 5))
    image = np.zeros((40, 80, 3), dtype=np.uint8)
    image[10:30, 20:60] = (0, 0, 255)
    assert poc01gr.red_mask(image)[15, 30] == 255


def test_generic_filters_ordering_and_original_xyxy(tmp_path: Path) -> None:
    assert not poc01gr.contour_is_candidate(299, 0, 0, 20, 20, 1200, 1200)
    assert not poc01gr.contour_is_candidate(40000, 0, 0, 200, 200, 1200, 1200)
    assert not poc01gr.contour_is_candidate(300, 0, 0, 30, 30, 1200, 1200)
    assert not poc01gr.contour_is_candidate(400, 0, 0, 301, 10, 1200, 1200)
    assert not poc01gr.contour_is_candidate(400, 0, 0, 10, 301, 1200, 1200)
    assert poc01gr.resized_xywh_to_original_xyxy(10, 20, 30, 40, 0.5) == (20, 40, 80, 120)
    image = np.zeros((1200, 1200, 3), dtype=np.uint8)
    cv2.rectangle(image, (100, 100), (139, 139), (0, 0, 255), -1)
    cv2.rectangle(image, (300, 300), (359, 359), (0, 0, 255), -1)
    path = tmp_path / "current.jpg"
    cv2.imwrite(str(path), image)
    proposals = poc01gr.propose(path, "front", "neutral_record")
    assert [item.candidate_id for item in proposals] == ["current_front_candidate_001", "current_front_candidate_002"]
    assert proposals[0].contour_area_working > proposals[1].contour_area_working
    assert all(item.bbox_coordinate_space == "original_image_xyxy" for item in proposals)


def test_fixed_six_view_reproduction_counts() -> None:
    root = Path(__file__).parents[1]
    current, _ = poc01gr._select_images(root)
    counts = {image.view: len(poc01gr.propose(image.path, image.view, image.record_id)) for image in current}
    assert counts == poc01gr.EXPECTED_COUNTS
    assert poc01gr.load_agent_descriptor(root) == "PIN_RED_SHORT"

