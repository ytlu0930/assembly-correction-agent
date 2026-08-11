"""Deterministically resolve correct assembly references from dataset manifests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

CANONICAL_VIEWS = ("front", "back", "left", "right", "top", "bottom")
DEFAULT_CASE_SELECTION_RULE = "lexicographically_smallest_case_id"
SOP_PATHS = {
    "model03": "references/sop/3號車車組裝SOP.jpg",
    "model08": "references/sop/8號車車組裝SOP.jpg",
}


class ReferenceRepositoryError(Exception):
    """Base error for deterministic reference resolution failures."""


class ReferenceNotFoundError(ReferenceRepositoryError, LookupError):
    """Raised when a requested model, step, case, or view is not indexed."""


class ReferenceDataError(ReferenceRepositoryError, ValueError):
    """Raised when reference source manifests are inconsistent."""


@dataclass(frozen=True)
class ReferenceImage:
    record_id: str
    source_path: str
    view: str
    capture_id: str
    anomalies: tuple[str, ...]


@dataclass(frozen=True)
class ReferenceView:
    view: str
    captures: tuple[ReferenceImage, ...]

    @property
    def record_ids(self) -> tuple[str, ...]:
        return tuple(image.record_id for image in self.captures)

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(image.source_path for image in self.captures)


@dataclass(frozen=True)
class CatalogReference:
    path: str
    version: str


@dataclass(frozen=True)
class ReferenceCase:
    model_id: str
    step_id: str
    case_id: str
    case_key: str
    normalized_label: str
    views: tuple[ReferenceView, ...]
    available_views: tuple[str, ...]
    missing_views: tuple[str, ...]
    captures_per_view: tuple[tuple[str, tuple[str, ...]], ...]
    reference_image_record_ids: tuple[str, ...]
    reference_image_paths: tuple[str, ...]
    data_quality_flags: tuple[str, ...]

    def get_view(self, view: str) -> ReferenceView:
        for reference_view in self.views:
            if reference_view.view == view:
                return reference_view
        raise ReferenceNotFoundError(
            f"reference view not found: {self.model_id}/{self.step_id}/{self.case_id}/{view}"
        )


@dataclass(frozen=True)
class ReferencePackage:
    model_id: str
    step_id: str
    cases: tuple[ReferenceCase, ...]
    selected_case_id: str
    selected_case: ReferenceCase
    default_case_selection_rule: str
    sop_reference_path: str
    part_catalog: CatalogReference
    data_quality_flags: tuple[str, ...]


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as error:
        raise ReferenceDataError(f"cannot load reference manifest {path}: {error}") from error


class ReferenceRepository:
    """Read-only index backed exclusively by Dataset Manifest correct records."""

    def __init__(
        self,
        repository_root: str | Path,
        *,
        manifest_path: str | Path | None = None,
        case_manifest_path: str | Path | None = None,
        part_catalog_path: str | Path | None = None,
    ) -> None:
        self.repository_root = Path(repository_root).resolve()
        self.manifest_path = Path(manifest_path) if manifest_path else self.repository_root / "data/dataset_manifest.jsonl"
        self.case_manifest_path = (
            Path(case_manifest_path)
            if case_manifest_path
            else self.repository_root / "data/dataset_case_manifest.jsonl"
        )
        catalog_path = Path(part_catalog_path) if part_catalog_path else self.repository_root / "data/part_catalog.json"
        self._catalog_reference = self._load_catalog_reference(catalog_path)
        self._cases = self._build_index(_load_jsonl(self.manifest_path), _load_jsonl(self.case_manifest_path))

    def _load_catalog_reference(self, path: Path) -> CatalogReference:
        try:
            catalog = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ReferenceDataError(f"cannot load part catalog {path}: {error}") from error
        try:
            relative_path = path.resolve().relative_to(self.repository_root).as_posix()
        except ValueError:
            relative_path = path.resolve().as_posix()
        version = catalog.get("schema_version")
        if not isinstance(version, str) or not version:
            raise ReferenceDataError(f"part catalog has no schema_version: {path}")
        return CatalogReference(path=relative_path, version=version)

    @staticmethod
    def _build_index(
        records: Iterable[dict[str, Any]], case_records: Iterable[dict[str, Any]]
    ) -> dict[tuple[str, str], tuple[ReferenceCase, ...]]:
        correct_by_id: dict[str, dict[str, Any]] = {}
        all_record_ids: set[str] = set()
        for record in records:
            record_id = record.get("record_id")
            if not isinstance(record_id, str) or not record_id:
                raise ReferenceDataError("Dataset Manifest record is missing record_id")
            if record_id in all_record_ids:
                raise ReferenceDataError(f"duplicate Dataset Manifest record_id: {record_id}")
            all_record_ids.add(record_id)
            if record.get("normalized_label") == "correct":
                correct_by_id[record_id] = record

        grouped: dict[tuple[str, str], list[ReferenceCase]] = {}
        for case in case_records:
            if case.get("normalized_label") != "correct":
                continue
            source_ids = case.get("source_record_ids")
            if not isinstance(source_ids, list) or not source_ids:
                raise ReferenceDataError(f"correct case has no source records: {case.get('case_key')}")
            missing_ids = [record_id for record_id in source_ids if record_id not in correct_by_id]
            if missing_ids:
                raise ReferenceDataError(
                    f"correct case {case.get('case_key')} references missing or non-correct records: {missing_ids}"
                )
            images = [correct_by_id[record_id] for record_id in source_ids]
            images.sort(key=lambda item: (item["view"], item["capture_id"], item["source_path"], item["record_id"]))
            model_id = case.get("model_id")
            step_id = case.get("step_id")
            case_id = case.get("case_id")
            if not all(isinstance(value, str) and value for value in (model_id, step_id, case_id)):
                raise ReferenceDataError(f"invalid correct case identity: {case.get('case_key')}")
            for image in images:
                expected = (model_id, step_id, case_id, "correct")
                actual = (
                    image.get("model_id"), image.get("step_id"), image.get("case_id"), image.get("normalized_label")
                )
                if actual != expected:
                    raise ReferenceDataError(f"case/image identity mismatch for {image['record_id']}")

            reference_views: list[ReferenceView] = []
            for view in CANONICAL_VIEWS:
                view_images = [image for image in images if image["view"] == view]
                if view_images:
                    reference_views.append(ReferenceView(
                        view=view,
                        captures=tuple(ReferenceImage(
                            record_id=image["record_id"],
                            source_path=image["source_path"],
                            view=image["view"],
                            capture_id=image["capture_id"],
                            anomalies=tuple(image.get("anomalies", ())),
                        ) for image in view_images),
                    ))
            available_views = tuple(view.view for view in reference_views)
            missing_views = tuple(view for view in CANONICAL_VIEWS if view not in available_views)
            manifest_missing = tuple(case.get("missing_views", ()))
            if set(manifest_missing) != set(missing_views):
                raise ReferenceDataError(f"case missing_views mismatch: {case.get('case_key')}")
            flags = set(case.get("data_quality_flags", ()))
            for image in images:
                flags.update(image.get("anomalies", ()))
            reference_case = ReferenceCase(
                model_id=model_id,
                step_id=step_id,
                case_id=case_id,
                case_key=case["case_key"],
                normalized_label="correct",
                views=tuple(reference_views),
                available_views=available_views,
                missing_views=missing_views,
                captures_per_view=tuple(
                    (view.view, tuple(image.capture_id for image in view.captures)) for view in reference_views
                ),
                reference_image_record_ids=tuple(image["record_id"] for image in images),
                reference_image_paths=tuple(image["source_path"] for image in images),
                data_quality_flags=tuple(sorted(flags)),
            )
            grouped.setdefault((model_id, step_id), []).append(reference_case)

        return {
            key: tuple(sorted(cases, key=lambda item: (item.case_id, item.case_key)))
            for key, cases in sorted(grouped.items())
        }

    def get_reference_cases(self, model_id: str, step_id: str) -> tuple[ReferenceCase, ...]:
        try:
            return self._cases[(model_id, step_id)]
        except KeyError as error:
            raise ReferenceNotFoundError(f"reference not found: {model_id}/{step_id}") from error

    def get_reference_case(self, model_id: str, step_id: str, case_id: str) -> ReferenceCase:
        for case in self.get_reference_cases(model_id, step_id):
            if case.case_id == case_id:
                return case
        raise ReferenceNotFoundError(f"reference case not found: {model_id}/{step_id}/{case_id}")

    def get_reference_view(self, model_id: str, step_id: str, case_id: str, view: str) -> ReferenceView:
        if view not in CANONICAL_VIEWS:
            raise ReferenceNotFoundError(f"unsupported reference view: {view}")
        return self.get_reference_case(model_id, step_id, case_id).get_view(view)

    def get_sop_reference(self, model_id: str) -> str:
        try:
            path = SOP_PATHS[model_id]
        except KeyError as error:
            raise ReferenceNotFoundError(f"SOP reference not found: {model_id}") from error
        if not (self.repository_root / path).is_file():
            raise ReferenceDataError(f"mapped SOP reference does not exist: {path}")
        return path

    def get_reference(self, model_id: str, step_id: str) -> ReferencePackage:
        cases = self.get_reference_cases(model_id, step_id)
        selected = cases[0]
        flags = sorted({flag for case in cases for flag in case.data_quality_flags})
        return ReferencePackage(
            model_id=model_id,
            step_id=step_id,
            cases=cases,
            selected_case_id=selected.case_id,
            selected_case=selected,
            default_case_selection_rule=DEFAULT_CASE_SELECTION_RULE,
            sop_reference_path=self.get_sop_reference(model_id),
            part_catalog=self._catalog_reference,
            data_quality_flags=tuple(flags),
        )

    def indexed_model_steps(self) -> dict[str, tuple[str, ...]]:
        result: dict[str, list[str]] = {}
        for model_id, step_id in self._cases:
            result.setdefault(model_id, []).append(step_id)
        return {model_id: tuple(steps) for model_id, steps in sorted(result.items())}


_DEFAULT_REPOSITORY: ReferenceRepository | None = None


def default_repository() -> ReferenceRepository:
    global _DEFAULT_REPOSITORY
    if _DEFAULT_REPOSITORY is None:
        root = Path(__file__).resolve().parents[3]
        _DEFAULT_REPOSITORY = ReferenceRepository(root)
    return _DEFAULT_REPOSITORY


def get_reference(model_id: str, step_id: str) -> ReferencePackage:
    return default_repository().get_reference(model_id, step_id)


def get_reference_cases(model_id: str, step_id: str) -> tuple[ReferenceCase, ...]:
    return default_repository().get_reference_cases(model_id, step_id)


def get_reference_case(model_id: str, step_id: str, case_id: str) -> ReferenceCase:
    return default_repository().get_reference_case(model_id, step_id, case_id)


def get_reference_view(model_id: str, step_id: str, case_id: str, view: str) -> ReferenceView:
    return default_repository().get_reference_view(model_id, step_id, case_id, view)

