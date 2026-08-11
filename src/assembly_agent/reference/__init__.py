"""Deterministic correct-state reference repository."""

from .repository import (
    CANONICAL_VIEWS,
    DEFAULT_CASE_SELECTION_RULE,
    CatalogReference,
    ReferenceCase,
    ReferenceDataError,
    ReferenceImage,
    ReferenceNotFoundError,
    ReferencePackage,
    ReferenceRepository,
    ReferenceRepositoryError,
    ReferenceView,
    default_repository,
    get_reference,
    get_reference_case,
    get_reference_cases,
    get_reference_view,
)

__all__ = [
    "CANONICAL_VIEWS",
    "DEFAULT_CASE_SELECTION_RULE",
    "CatalogReference",
    "ReferenceCase",
    "ReferenceDataError",
    "ReferenceImage",
    "ReferenceNotFoundError",
    "ReferencePackage",
    "ReferenceRepository",
    "ReferenceRepositoryError",
    "ReferenceView",
    "default_repository",
    "get_reference",
    "get_reference_case",
    "get_reference_cases",
    "get_reference_view",
]

