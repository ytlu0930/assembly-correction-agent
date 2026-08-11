"""Grounded candidate detection and constrained candidate verification."""

from .grounding import GroundingCandidate, GroundingDinoDetector, GroundingResult, build_grounding_query
from .matching import CandidateAssessment, GroundedLocalization, classify_localization

__all__ = [
    "CandidateAssessment", "GroundedLocalization", "GroundingCandidate",
    "GroundingDinoDetector", "GroundingResult", "build_grounding_query",
    "classify_localization",
]
