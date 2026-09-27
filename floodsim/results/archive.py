"""Portable, compressed archives for completed result review."""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from floodsim.domain.manifest import RunManifest
from floodsim.domain.run_config import RunConfig
from floodsim.results.regular_netcdf_source import (
    RegularNetcdfSourceError,
    inspect_regular_netcdf_source,
    load_regular_netcdf_descriptor,
    validate_source_identity,
)
from floodsim.results.view import ResultViewError, load_normalized_arrays
from floodsim.storage.run_store import atomic_write_json

ARCHIVE_SCHEMA_VERSION = "1"
REGULAR_ARCHIVE_SCHEMA_VERSION = "2"
ARCHIVE_MANIFEST = "archive_manifest.json"
RUN_CONFIG = "run_config.json"
RUN_MANIFEST = "manifest.json"
RESULT_METADATA = "result_metadata.json"
NORMALIZED_ARRAYS = "normalized_arrays.npz"
REGULAR_DESCRIPTOR = "regular_netcdf_source.json"
REGULAR_NETCDF = "sfincs_map.nc"
EXPECTED_MEMBERS = {
    ARCHIVE_MANIFEST,
    RUN_CONFIG,
    RUN_MANIFEST,
    RESULT_METADATA,
    NORMALIZED_ARRAYS,
}
EXPECTED_REGULAR_MEMBERS = {
    ARCHIVE_MANIFEST,
    RUN_CONFIG,
    RUN_MANIFEST,
    RESULT_METADATA,
    REGULAR_DESCRIPTOR,
    REGULAR_NETCDF,
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
    arrays_path: Path | None = None,
    descriptor_path: Path | None = None,
    source_path: Path | None = None,
) -> None:
    is_regular = descriptor_path is not None or source_path is not None
    if is_regular != (descriptor_path is not None and source_path is not None):
        raise ResultArchiveError("regular archive requires both descriptor and NetCDF source")
    if is_regular == (arrays_path is not None):
        raise ResultArchiveError("archive requires exactly one result storage format")
    descriptor = {
        "schema_version": REGULAR_ARCHIVE_SCHEMA_VERSION if is_regular else ARCHIVE_SCHEMA_VERSION,
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
        if is_regular:
            assert descriptor_path is not None and source_path is not None
            archive.write(descriptor_path, REGULAR_DESCRIPTOR)
            archive.write(source_path, REGULAR_NETCDF)
        else:
            assert arrays_path is not None
            archive.write(arrays_path, NORMALIZED_ARRAYS)


def import_result_archive(source: Path, destination: Path) -> tuple[RunConfig, RunManifest, dict[str, Any]]:
    try:
        with zipfile.ZipFile(source, "r") as archive:
            members = archive.infolist()
            names = {member.filename for member in members}
            descriptor = _read_json(archive, ARCHIVE_MANIFEST)
            schema_version = descriptor.get("schema_version")
            expected = (
                EXPECTED_REGULAR_MEMBERS
                if schema_version == REGULAR_ARCHIVE_SCHEMA_VERSION
                else EXPECTED_MEMBERS
            )
            if names != expected or len(members) != len(expected):
                raise ResultArchiveError("archive members do not match the result contract")
            if any(member.is_dir() or member.file_size < 0 for member in members):
                raise ResultArchiveError("archive contains an invalid member")
            if sum(member.file_size for member in members) > MAX_UNCOMPRESSED_ARCHIVE_BYTES:
                raise ResultArchiveError("archive expands beyond the supported size")

            if descriptor != {
                "format": "urban-pluvial-flood-result",
                "schema_version": schema_version,
            } or schema_version not in {ARCHIVE_SCHEMA_VERSION, REGULAR_ARCHIVE_SCHEMA_VERSION}:
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
            if schema_version == ARCHIVE_SCHEMA_VERSION:
                arrays_path = results_dir / NORMALIZED_ARRAYS
                _extract_member(archive, NORMALIZED_ARRAYS, arrays_path)
            else:
                model_dir = destination / "model"
                model_dir.mkdir(parents=True, exist_ok=False)
                descriptor_path = results_dir / REGULAR_DESCRIPTOR
                source_path = model_dir / REGULAR_NETCDF
                _extract_member(archive, REGULAR_DESCRIPTOR, descriptor_path)
                regular_descriptor = load_regular_netcdf_descriptor(descriptor_path)
                if regular_descriptor.source_filename != REGULAR_NETCDF:
                    raise ResultArchiveError("regular archive descriptor has an invalid source name")
                netcdf_member = archive.getinfo(REGULAR_NETCDF)
                if netcdf_member.file_size != regular_descriptor.source_size_bytes:
                    raise ResultArchiveError("regular archive source identity is invalid")
                _extract_member(archive, REGULAR_NETCDF, source_path)
                os.utime(
                    source_path,
                    ns=(regular_descriptor.source_mtime_ns, regular_descriptor.source_mtime_ns),
                )
    except (OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError, ValidationError) as exc:
        raise ResultArchiveError("result archive cannot be read") from exc

    # Loading is the authoritative structural check used by the result API.
    try:
        if schema_version == ARCHIVE_SCHEMA_VERSION:
            load_normalized_arrays(arrays_path)
        else:
            validate_source_identity(regular_descriptor, model_dir=model_dir)
            inspected = inspect_regular_netcdf_source(
                source_path,
                model_dir=model_dir,
                bounds=regular_descriptor.bounds,
                block_size_m=regular_descriptor.block_size_m,
            )
            if (
                inspected.height != regular_descriptor.height
                or inspected.width != regular_descriptor.width
                or inspected.time_values != regular_descriptor.time_values
                or inspected.variable_names != regular_descriptor.variable_names
            ):
                raise ResultArchiveError("regular archive descriptor does not match its NetCDF source")
    except (OSError, ResultViewError, RegularNetcdfSourceError, ValueError) as exc:
        raise ResultArchiveError("result archive data is invalid") from exc
    atomic_write_json(destination / RUN_CONFIG, config.model_dump(mode="json"))
    atomic_write_json(results_dir / RESULT_METADATA, metadata)
    return config, manifest, metadata


def _extract_member(archive: zipfile.ZipFile, name: str, target: Path) -> None:
    with archive.open(name) as source_handle, target.open("wb") as output:
        shutil.copyfileobj(source_handle, output, length=1024 * 1024)


def _read_json(archive: zipfile.ZipFile, name: str) -> dict[str, Any]:
    value = json.loads(archive.read(name))
    if not isinstance(value, dict):
        raise ResultArchiveError(f"{name} must contain a JSON object")
    return value
