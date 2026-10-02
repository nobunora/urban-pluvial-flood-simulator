"""Normalized result metadata, rendering, and native inspection API."""

from __future__ import annotations

import os
import tempfile
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import UUID

import numpy as np
from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.background import BackgroundTask

from floodsim.api.errors import ApiContractError
from floodsim.api.routes_runs import coordinator
from floodsim.api.runtime_config import demo_archive_path, runtime_config
from floodsim.api.schemas import (
    ElevationPreviewRequest,
    ElevationPreviewResponse,
    PointInspectionResponse,
    ResultImportResponse,
    ResultMetadataResponse,
)
from floodsim.domain.geometry import AnalysisArea
from floodsim.orchestration.run_coordinator import ResultNotReady, RunNotFound
from floodsim.providers.common import ProviderError
from floodsim.results.adaptive_scale import generate_adaptive_breaks
from floodsim.results.archive import ResultArchiveError, create_result_archive
from floodsim.results.elevation_preview import ElevationPreviewStore
from floodsim.results.regular_flow import regular_flow_viewport
from floodsim.results.regular_netcdf_source import (
    RegularNetcdfSourceError,
    load_regular_netcdf_descriptor,
    regular_speed_reference,
    regular_window_arrays,
)
from floodsim.results.regular_queries import (
    inspect_regular_point,
    regular_elevation_png,
    regular_grid_png,
    saved_speed_scale,
)
from floodsim.results.vector_viewport import flow_vectors_viewport_geojson
from floodsim.results.view import (
    PointOutsideResult,
    ResultArrays,
    ResultTimeIndexInvalid,
    ResultViewError,
    depth_legend_metadata,
    elevation_legend_metadata,
    inspect_native_point,
    load_normalized_arrays,
    maximum_depth_location,
    render_elevation_values_png,
    render_grid_resolution_png,
    render_max_depth_png,
    render_terrain_elevation_png,
    render_time_depth_png,
    terrain_elevation_range,
)

router = APIRouter()
MAX_ARCHIVE_UPLOAD_BYTES = 8 * 1024**3
_demo_result_runs: dict[str, UUID] = {}
_demo_result_lock = Lock()
_elevation_previews = ElevationPreviewStore()


def _map_result_error(exc: Exception) -> ApiContractError:
    if isinstance(exc, RunNotFound):
        return ApiContractError(404, exc.code, "指定された計算が見つかりません。")
    if isinstance(exc, ResultNotReady):
        return ApiContractError(409, exc.code, "計算結果はまだ利用できません。")
    if isinstance(exc, PointOutsideResult):
        return ApiContractError(404, exc.code, "指定地点は計算結果の範囲外です。")
    if isinstance(exc, ResultTimeIndexInvalid):
        return ApiContractError(400, exc.code, "指定された結果時刻を利用できません。")
    if isinstance(exc, ResultViewError):
        return ApiContractError(500, exc.code, "計算結果を表示用に読み込めません。")
    return ApiContractError(500, "RESULT_VIEW_FAILED", "計算結果を表示できません。")


@lru_cache(maxsize=16)
def _load_arrays_cached(path_text: str, mtime_ns: int) -> ResultArrays:
    del mtime_ns
    return load_normalized_arrays(Path(path_text))


@lru_cache(maxsize=512)
def _render_time_depth_cached(
    path_text: str,
    mtime_ns: int,
    time_index: int,
    max_px: int,
) -> bytes:
    arrays = _load_arrays_cached(path_text, mtime_ns)
    return render_time_depth_png(arrays, time_index=time_index, max_px=max_px)


@lru_cache(maxsize=512)
def _flow_viewport_cached(
    path_text: str,
    mtime_ns: int,
    area_json: str,
    time_index: int,
    west: float,
    south: float,
    east: float,
    north: float,
    stride: int,
) -> dict[str, Any]:
    arrays = _load_arrays_cached(path_text, mtime_ns)
    return flow_vectors_viewport_geojson(
        arrays,
        area=AnalysisArea.model_validate_json(area_json),
        time_index=time_index,
        west=west,
        south=south,
        east=east,
        north=north,
        stride=stride,
    )


def _arrays_path_for_run(run_id: UUID) -> tuple[Path, int]:
    path = coordinator.result_arrays_path(run_id)
    return path, path.stat().st_mtime_ns


def _arrays_for_run(run_id: UUID) -> ResultArrays:
    try:
        try:
            path, mtime_ns = _arrays_path_for_run(run_id)
            return _load_arrays_cached(str(path), mtime_ns)
        except ResultNotReady:
            source_path = coordinator.result_source_path(run_id)
            source = load_regular_netcdf_descriptor(source_path)
            return regular_window_arrays(
                source,
                model_dir=coordinator.store.run_dir(run_id) / "model",
                time_index=0,
            )
    except (RunNotFound, ResultNotReady, ResultViewError, RegularNetcdfSourceError, OSError) as exc:
        raise _map_result_error(exc) from exc


def _source_arrays_for_run(run_id: UUID, time_index: int) -> ResultArrays | None:
    """Return a single-frame source-backed regular result, or None for NPZ runs."""
    try:
        source_path = coordinator.result_source_path(run_id)
    except ResultNotReady:
        return None
    source = load_regular_netcdf_descriptor(source_path)
    return regular_window_arrays(
        source,
        model_dir=coordinator.store.run_dir(run_id) / "model",
        time_index=time_index,
    )


@lru_cache(maxsize=16)
def _source_speed_scale_cached(path_text: str, mtime_ns: int, model_dir: str) -> dict[str, Any]:
    del mtime_ns
    descriptor = load_regular_netcdf_descriptor(path_text)
    return regular_speed_reference(descriptor, model_dir=model_dir).to_metadata()


LAYER_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=31536000, immutable",
}
PREVIEW_CACHE_HEADERS = {"Cache-Control": "private, max-age=300"}


@router.get("/runs/{run_id}/result-metadata", response_model=ResultMetadataResponse)
def result_metadata(run_id: UUID) -> ResultMetadataResponse:
    try:
        metadata = coordinator.result_metadata(run_id)
    except (RunNotFound, ResultNotReady) as exc:
        raise _map_result_error(exc) from exc
    arrays = _arrays_for_run(run_id)
    metadata["max_depth_summary"] = {
        **metadata["max_depth_summary"],
        **maximum_depth_location(arrays, area=coordinator.get(run_id).config.analysis_area),
    }
    metadata["depth_legend"] = depth_legend_metadata(scale=arrays.depth_scale)
    minimum_m, maximum_m = terrain_elevation_range(arrays)
    metadata["elevation_legend"] = elevation_legend_metadata(minimum_m, maximum_m, scale=arrays.elevation_scale)
    metadata["display_scales"] = {"depth": arrays.depth_scale.to_metadata(), "elevation": arrays.elevation_scale.to_metadata()}
    return ResultMetadataResponse.model_validate(metadata)


@router.post("/elevation-previews", response_model=ElevationPreviewResponse)
def create_elevation_preview(request: ElevationPreviewRequest) -> ElevationPreviewResponse:
    if not runtime_config().allow_run:
        raise ApiContractError(
            403,
            "ELEVATION_PREVIEW_DISABLED_IN_DEMO",
            "Webデモ版では新しい標高を取得できません。",
        )
    try:
        product = coordinator.elevation_provider.acquire(
            request.analysis_area,
            grid_m=float(request.grid_cell_size_m),
            cache_dir=coordinator.store.root.parent / "cache",
        )
        active = product.uncovered_boundary_mask
        active_mask = (
            np.isfinite(product.z)
            if active is None
            else np.isfinite(product.z) & ~active
        )
        if not np.any(active_mask):
            raise ResultViewError("取得した標高に表示可能なセルがありません。")
        minimum_m = float(np.min(product.z[active_mask]))
        maximum_m = float(np.max(product.z[active_mask]))
        png = render_elevation_values_png(product.z, active_mask)
        counts = {
            str(key): int(value)
            for key, value in product.provenance.source_details.get(
                "provider_counts", {}
            ).items()
        }
        metadata = {
            "bounds": request.analysis_area.bounds.model_dump(),
            "grid_cell_size_m": request.grid_cell_size_m,
            "width_samples": int(product.z.shape[1]),
            "height_samples": int(product.z.shape[0]),
            "elevation_legend": elevation_legend_metadata(minimum_m, maximum_m, scale=generate_adaptive_breaks(product.z[active_mask], anchor_zero=False)),
            "provider_counts": counts,
            "nearest_filled_cells": int(product.nearest_filled),
        }
        preview = _elevation_previews.add(png, metadata)
    except ProviderError as exc:
        raise ApiContractError(
            502,
            exc.code,
            "標高データを取得できません。時間を置いて再試行してください。",
            retryable=exc.retryable,
        ) from exc
    except (ValueError, ResultViewError) as exc:
        raise ApiContractError(
            500,
            "ELEVATION_PREVIEW_FAILED",
            "標高プレビューを作成できません。",
        ) from exc
    return ElevationPreviewResponse.model_validate(
        {
            "preview_id": preview.preview_id,
            **preview.metadata,
            "image_url": f"/api/v1/elevation-previews/{preview.preview_id}.png",
        }
    )


@router.get("/elevation-previews/{preview_id}.png", include_in_schema=False)
def elevation_preview_png(preview_id: UUID) -> Response:
    preview = _elevation_previews.get(preview_id)
    if preview is None:
        raise ApiContractError(
            404,
            "ELEVATION_PREVIEW_NOT_FOUND",
            "標高プレビューの有効期限が切れています。もう一度取得してください。",
        )
    return Response(content=preview.png, media_type="image/png", headers=PREVIEW_CACHE_HEADERS)


@router.get("/runs/{run_id}/export")
def export_result(run_id: UUID) -> FileResponse:
    archive_path: Path | None = None
    try:
        run_dir = coordinator.store.run_dir(run_id)
        fd, temporary_name = tempfile.mkstemp(prefix=f"flood-result-{run_id}-", suffix=".zip")
        os.close(fd)
        archive_path = Path(temporary_name)
        common_paths = {
            "config_path": run_dir / "run_config.json",
            "manifest_path": run_dir / "manifest.json",
            "metadata_path": run_dir / "results" / "result_metadata.json",
        }
        try:
            arrays_path = coordinator.result_arrays_path(run_id)
            create_result_archive(archive_path, arrays_path=arrays_path, **common_paths)
        except ResultNotReady:
            descriptor_path = coordinator.result_source_path(run_id)
            descriptor = load_regular_netcdf_descriptor(descriptor_path)
            source_path = run_dir / "model" / descriptor.source_filename
            create_result_archive(
                archive_path,
                descriptor_path=descriptor_path,
                source_path=source_path,
                **common_paths,
            )
    except (RunNotFound, ResultNotReady, OSError) as exc:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)
        raise _map_result_error(exc) from exc
    assert archive_path is not None
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=f"flood-result-{run_id}.zip",
        background=BackgroundTask(archive_path.unlink, missing_ok=True),
    )


@router.post("/results/import", response_model=ResultImportResponse)
async def import_result(request: Request) -> ResultImportResponse:
    if not runtime_config().allow_result_import:
        raise ApiContractError(
            403,
            "RESULT_IMPORT_DISABLED_IN_DEMO",
            "Webデモ版では任意の解析結果を読み込めません。",
        )
    media_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if media_type not in {"application/zip", "application/octet-stream"}:
        raise ApiContractError(415, "RESULT_ARCHIVE_CONTENT_TYPE", "ZIP形式の解析結果を指定してください。")
    fd, temporary_name = tempfile.mkstemp(prefix="flood-result-import-", suffix=".zip")
    size = 0
    try:
        with os.fdopen(fd, "wb") as handle:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_ARCHIVE_UPLOAD_BYTES:
                    raise ApiContractError(413, "RESULT_ARCHIVE_TOO_LARGE", "解析結果ファイルが大きすぎます。")
                handle.write(chunk)
        if size == 0:
            raise ApiContractError(400, "RESULT_ARCHIVE_EMPTY", "解析結果ファイルが空です。")
        record = coordinator.import_result(Path(temporary_name))
        return ResultImportResponse(run_id=record.run_id)
    except ResultArchiveError as exc:
        raise ApiContractError(400, "RESULT_ARCHIVE_INVALID", "解析結果ファイルを読み込めません。") from exc
    finally:
        Path(temporary_name).unlink(missing_ok=True)


@router.post("/demo-results/{event_id}/open", response_model=ResultImportResponse)
def open_demo_result(event_id: str) -> ResultImportResponse:
    archive_path = demo_archive_path(event_id)
    if archive_path is None:
        raise ApiContractError(
            404,
            "DEMO_RESULT_NOT_FOUND",
            "この豪雨条件の解析済みデモ結果はまだ用意されていません。",
        )
    with _demo_result_lock:
        existing = _demo_result_runs.get(event_id)
        if existing is not None:
            try:
                coordinator.get(existing)
                return ResultImportResponse(run_id=existing)
            except RunNotFound:
                _demo_result_runs.pop(event_id, None)
        try:
            record = coordinator.import_result(archive_path)
        except ResultArchiveError as exc:
            raise ApiContractError(
                500,
                "DEMO_RESULT_INVALID",
                "解析済みデモ結果を読み込めません。",
            ) from exc
        _demo_result_runs[event_id] = record.run_id
        return ResultImportResponse(run_id=record.run_id)


@router.get("/runs/{run_id}/layers/max-depth.png")
def max_depth_layer(run_id: UUID, max_px: int = 4096) -> Response:
    arrays = _arrays_for_run(run_id)
    try:
        content = render_max_depth_png(arrays, max_px=max_px)
    except ResultViewError as exc:
        raise _map_result_error(exc) from exc
    return Response(content=content, media_type="image/png", headers=LAYER_CACHE_HEADERS)


@router.get("/runs/{run_id}/layers/depth.png")
def time_depth_layer(
    run_id: UUID,
    time_index: int,
    max_px: int = 4096,
) -> Response:
    try:
        source_arrays = _source_arrays_for_run(run_id, time_index)
        if source_arrays is not None:
            content = render_time_depth_png(source_arrays, time_index=0, max_px=max_px)
        else:
            path, mtime_ns = _arrays_path_for_run(run_id)
            content = _render_time_depth_cached(str(path), mtime_ns, time_index, max_px)
    except (RunNotFound, ResultNotReady, ResultViewError, RegularNetcdfSourceError, OSError) as exc:
        raise _map_result_error(exc) from exc
    return Response(
        content=content,
        media_type="image/png",
        headers=LAYER_CACHE_HEADERS,
    )


@router.get("/runs/{run_id}/layers/grid-resolution.png")
def grid_resolution_layer(run_id: UUID, max_px: int = 4096) -> Response:
    try:
        try:
            source_path = coordinator.result_source_path(run_id)
        except ResultNotReady:
            source_path = None
        if source_path is not None:
            content = regular_grid_png(load_regular_netcdf_descriptor(source_path),
                coordinator.store.run_dir(run_id) / "model", max_px)
        else:
            content = render_grid_resolution_png(_arrays_for_run(run_id), max_px=max_px)
    except (RunNotFound, ResultViewError, RegularNetcdfSourceError, OSError) as exc:
        raise _map_result_error(exc) from exc
    return Response(content=content, media_type="image/png", headers=LAYER_CACHE_HEADERS)


@router.get("/runs/{run_id}/layers/elevation.png")
def elevation_layer(run_id: UUID, max_px: int = 4096) -> Response:
    try:
        try:
            source_path = coordinator.result_source_path(run_id)
        except ResultNotReady:
            source_path = None
        if source_path is not None:
            content = regular_elevation_png(load_regular_netcdf_descriptor(source_path),
                coordinator.store.run_dir(run_id) / "model", max_px)
        else:
            content = render_terrain_elevation_png(_arrays_for_run(run_id), max_px=max_px)
    except (RunNotFound, ResultViewError, RegularNetcdfSourceError, OSError) as exc:
        raise _map_result_error(exc) from exc
    return Response(content=content, media_type="image/png", headers=LAYER_CACHE_HEADERS)



@router.get(
    "/runs/{run_id}/layers/flow-vectors.geojson",
    include_in_schema=False,
)
def flow_vectors_geojson_layer(
    run_id: UUID,
    time_index: int = Query(ge=0),
    west: float = Query(ge=-180, le=180),
    south: float = Query(ge=-90, le=90),
    east: float = Query(ge=-180, le=180),
    north: float = Query(ge=-90, le=90),
    stride: int = Query(default=8, ge=1, le=4096),
) -> JSONResponse:
    try:
        record = coordinator.get(run_id)
        try:
            source_path = coordinator.result_source_path(run_id)
        except ResultNotReady:
            source_path = None
        if source_path is not None:
            source = load_regular_netcdf_descriptor(source_path)
            model_dir = coordinator.store.run_dir(run_id) / "model"
            speed_scale = saved_speed_scale(source, model_dir) or _source_speed_scale_cached(
                str(source_path), source_path.stat().st_mtime_ns, str(model_dir)
            )
            payload = regular_flow_viewport(
                source, model_dir=model_dir,
                area=record.config.analysis_area,
                time_index=time_index,
                west=west,
                south=south,
                east=east,
                north=north,
                stride=stride,
                speed_scale=speed_scale,
            )
        else:
            path, mtime_ns = _arrays_path_for_run(run_id)
            payload = _flow_viewport_cached(
                str(path),
                mtime_ns,
                record.config.analysis_area.model_dump_json(),
                time_index,
                west,
                south,
                east,
                north,
                stride,
            )
    except (RunNotFound, ResultNotReady, ResultViewError, RegularNetcdfSourceError, OSError) as exc:
        raise _map_result_error(exc) from exc
    return JSONResponse(content=payload, headers=LAYER_CACHE_HEADERS)


@router.get("/runs/{run_id}/inspect", response_model=PointInspectionResponse)
def inspect_result(
    run_id: UUID,
    lon: float = Query(ge=-180, le=180),
    lat: float = Query(ge=-90, le=90),
    time_index: int | None = Query(default=None, ge=0),
) -> PointInspectionResponse:
    try:
        record = coordinator.get(run_id)
        try:
            source_path = coordinator.result_source_path(run_id)
        except ResultNotReady:
            source_path = None
        if source_path is not None:
            return PointInspectionResponse.model_validate(inspect_regular_point(
                load_regular_netcdf_descriptor(source_path),
                model_dir=coordinator.store.run_dir(run_id) / "model",
                area=record.config.analysis_area, lon=lon, lat=lat, time_index=time_index,
            ))
        arrays = _arrays_for_run(run_id)
        payload = inspect_native_point(
            arrays,
            area=record.config.analysis_area,
            lon_deg=lon,
            lat_deg=lat,
            time_index=time_index,
        )
    except (RunNotFound, ResultViewError, RegularNetcdfSourceError) as exc:
        raise _map_result_error(exc) from exc
    return PointInspectionResponse.model_validate(payload)
