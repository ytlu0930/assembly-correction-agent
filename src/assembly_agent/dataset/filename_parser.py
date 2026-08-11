"""Parse immutable dataset source paths into deterministic metadata."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = "1.0"
VIEWS = ("front", "back", "left", "right", "top", "bottom")
LABEL_MAP = {
    "correct": "correct",
    "extrapart": "extra_part",
    "missingpart": "missing_part",
    "wrongpart": "wrong_part",
    "positionerror": "position_error",
    "criticalerror": "composite_error",
}
DIRECTORY_LABELS = {"correct": "normal", **{k: k for k in LABEL_MAP if k != "correct"}}

_ASSEMBLY_RE = re.compile(
    r"^(?P<model_id>model\d{2})_(?P<step_id>step\d{2})_"
    r"(?P<raw_label>correct|extrapart|missingpart|wrongpart|positionerror|criticalerror)-"
    r"(?P<case_id>[A-Z]?\d{2})_(?P<view>front|back|left|right|top|bottom)_"
    r"(?P<capture_id>\d{2})(?P<copy_suffix> \(\d+\))?"
    r"(?P<extension>\.jpg|\.jpg_)$"
)
_PART_RE = re.compile(
    r"^part_(?P<part_descriptor>[A-Z0-9]+(?:_[A-Z0-9]+)*)_"
    r"(?P<capture_id>\d{2})(?P<extension>\.jpg)$"
)


def _blank(source_path: str) -> dict[str, Any]:
    path = PurePosixPath(source_path)
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": None,
        "source_path": source_path,
        "source_filename": path.name,
        "source_kind": None,
        "model_id": None,
        "step_id": None,
        "directory_label": None,
        "raw_label": None,
        "normalized_label": None,
        "case_id": None,
        "case_key": None,
        "view": None,
        "capture_id": None,
        "copy_suffix": None,
        "part_descriptor": None,
        "extension": path.suffix,
        "file_size_bytes": None,
        "sha256": None,
        "parse_status": "invalid",
        "anomalies": [],
    }


def parse_source_path(source_path: str | Path, *, tolerant: bool = True) -> dict[str, Any]:
    """Parse a path relative to the repository, without accessing or changing it."""
    source = Path(source_path).as_posix()
    record = _blank(source)
    parts = PurePosixPath(source).parts
    match = _ASSEMBLY_RE.match(record["source_filename"])
    if match:
        values = match.groupdict()
        record.update(values)
        record["source_kind"] = "assembly_image"
        record["normalized_label"] = LABEL_MAP[values["raw_label"]]
        record["case_key"] = "|".join(
            (values["model_id"], values["step_id"], record["normalized_label"], values["case_id"])
        )
        anomalies: list[str] = []
        if values["extension"] == ".jpg_":
            if not tolerant:
                record["anomalies"] = ["malformed_extension"]
                return record
            anomalies.append("malformed_extension")
        expected_case = r"\d{2}" if values["raw_label"] == "correct" else r"[A-Z]\d{2}"
        if not re.fullmatch(expected_case, values["case_id"]):
            anomalies.append("invalid_case_id_for_label")
        if len(parts) < 4 or parts[-4] != values["model_id"]:
            anomalies.append("directory_filename_mismatch")
        expected_directory = DIRECTORY_LABELS[values["raw_label"]]
        record["directory_label"] = parts[-3] if len(parts) >= 3 else None
        if record["directory_label"] != expected_directory:
            anomalies.append("directory_filename_mismatch")
        if len(parts) < 2 or parts[-2] != f"{values['model_id']}_{values['step_id']}":
            anomalies.append("directory_filename_mismatch")
        record["anomalies"] = sorted(set(anomalies))
        fatal = {"directory_filename_mismatch", "invalid_case_id_for_label"}
        record["parse_status"] = "invalid" if fatal.intersection(anomalies) else ("warning" if anomalies else "valid")
        return record

    match = _PART_RE.match(record["source_filename"])
    if match:
        values = match.groupdict()
        record.update(values)
        record["source_kind"] = "part_image"
        record["directory_label"] = parts[-2] if len(parts) >= 2 else None
        anomalies = [] if len(parts) >= 2 and parts[-2] == "parts" else ["directory_filename_mismatch"]
        record["anomalies"] = anomalies
        record["parse_status"] = "valid" if not anomalies else "invalid"
        return record

    record["anomalies"] = ["malformed_filename"]
    return record
