"""Deterministic correction policy for Demo Sprint 01."""

from dataclasses import dataclass

from assembly_agent.vision.localization import StageAAnalysis, StageBLocalization
from assembly_agent.vision.schemas import VisionAnalysis


@dataclass(frozen=True)
class CorrectionAction:
    action: str
    target_descriptor: str


def plan_demo01_correction(analysis: VisionAnalysis) -> CorrectionAction | None:
    if analysis.status == "error" and analysis.error_type == "extra_part" and analysis.actual_part.descriptor:
        return CorrectionAction(action="REMOVE", target_descriptor=analysis.actual_part.descriptor)
    return None


def plan_verified_localization_correction(
    diagnosis: StageAAnalysis, localization: StageBLocalization
) -> CorrectionAction | None:
    candidate = localization.selected_candidate
    if (
        diagnosis.status == "error"
        and diagnosis.error_type == "extra_part"
        and diagnosis.target_part_descriptor
        and localization.target_descriptor == diagnosis.target_part_descriptor
        and localization.localization_status == "verified"
        and candidate is not None
        and candidate.comparison_result == "current_only"
    ):
        return CorrectionAction("REMOVE", diagnosis.target_part_descriptor)
    return None
