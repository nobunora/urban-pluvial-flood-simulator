"""Portable, compressed archives for completed result review."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from floodsim.domain.manifest import RunManifest
from floodsim.domain.run_config import RunConfig
from floodsim.results.view import ResultViewError, load_normalized_arrays
from floodsim.storage.run_store import atomic_write_json

ARCHIVE_SCHEMA_VERSION = "1"
ARCHIVE_MANIFEST = "archive_manifest.json"
RUN_CONFIG = "run_config.json"
RUN_MANIFEST = "manifest.json"
RESULT_METADATA = "result_metadata.json"
NORMALIZED_ARRAYS = "normalized_arrays.npz"
EXPECTED_MEMBERS = {
    ARCHIVE_MANIFEST,
    RUN_CONFIG,
    RUN_MANIFEST,
    RESULT_METADATA,
    NORMALIZED_ARRAYS,
}
MAX_UNCOMPRESSED_ARCHIVE_BYTES = 16 * 1024**3


class ResultArchiveError(ValueError):
    """Raised when an imported result archive is unsafe or invalid."""


def create_result_archive(
    target: Path,
    *,
    config_path: Path,
    manifest_path: Path,
    metadata_path: Path,
    arrays_path: Path,
) -> None:
    descriptor = {
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "format": "urban-pluvial-flood-result",
    }
    with zipfile.ZipFile(
        target,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
        allowZip64=True,
    ) as archive:
        archive.writestr(ARCHIVE_MANIFEST, json.dumps(descriptor, sort_keys=True))
        archive.write(config_path, RUN_CONFIG)
        archive.write(manifest_path, RUN_MANIFEST)
        archive.write(metadata_path, RESULT_METADATA)
        archive.write(arrays_path, NORMALIZED_ARRAYS)


def import_result_archive(source: Path, destination: Path) -> tuple[RunConfig, RunManifest, dict[str, Any]]:
    try:
        with zipfile.ZipFile(source, "r") as archive:
            members = archive.infolist()
            names = {member.filename for member in members}
            if names != EXPECTED_MEMBERS or len(members) != len(EXPECTED_MEMBERS):
                raise ResultArchiveError("archive members do not match the result contract")
            if any(member.is_dir() or member.file_size < 0 for member in members):
                raise ResultArchiveError("archive contains an invalid member")
            if sum(member.file_size for member in members) > MAX_UNCOMPRESSED_ARCHIVE_BYTES:
                raise ResultArchiveError("archive expands beyond the supported size")

            descriptor = _read_json(archive, ARCHIVE_MANIFEST)
            if descriptor != {
                "format": "urban-pluvial-flood-result",
                "schema_version": ARCHIVE_SCHEMA_VERSION,
            }:
                raise ResultArchiveError("unsupported result archive schema")
            config = RunConfig.model_validate(_read_json(archive, RUN_CONFIG))
            manifest = RunManifest.model_validate(_read_json(archive, RUN_MANIFEST))
            metadata = _read_json(archive, RESULT_METADATA)
            if (
                manifest.analysis_area != config.analysis_area
                or manifest.requested_accuracy_mode != config.requested_accuracy_mode
            ):
                raise ResultArchiveError("archive configuration and manifest disagree")

            results_dir = destination / "results"
            results_dir.mkdir(parents=True, exist_ok=False)
            arrays_path = results_dir / NORMALIZED_ARRAYS
            with archive.open(NORMALIZED_ARRAYS) as source_handle, arrays_path.open("wb") as output:
                shutil.copyfileobj(source_handle, output, length=1024 * 1024)
    except (OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError, ValidationError) as exc:
        raise ResultArchiveError("result archive cannot be read") from exc

    # Loading is the authoritative structural check used by the result API.
    try:
        load_normalized_arrays(arrays_path)
    except (OSError, ResultViewError, ValueError) as exc:
        raise ResultArchiveError("normalized result arrays are invalid") from exc
    atomic_write_json(destination / RUN_CONFIG, config.model_dump(mode="json"))
    atomic_write_json(results_dir / RESULT_METADATA, metadata)
    return config, manifest, metadata


def _read_json(archive: zipfile.ZipFile, name: str) -> dict[str, Any]:
    value = json.loads(archive.read(name))
    if not isinstance(value, dict):
        raise ResultArchiveError(f"{name} must contain a JSON object")
    return value
