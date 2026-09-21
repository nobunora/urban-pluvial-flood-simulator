"""Normalized result metadata, rendering, and native inspection API."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response

from floodsim.api.errors import ApiContractError
from floodsim.api.routes_runs import coordinator
from floodsim.api.schemas import PointInspectionResponse, ResultMetadataResponse
from floodsim.domain.geometry import AnalysisArea
from floodsim.orchestration.run_coordinator import ResultNotReady, RunNotFound
from floodsim.results.view import (
    PointOutsideResult,
    ResultArrays,
    ResultTimeIndexInvalid,
    ResultViewError,
    flow_vectors_geojson,
    inspect_native_point,
    load_normalized_arrays,
    render_grid_resolution_png,
    render_max_depth_png,
    render_time_depth_png,
)

router = APIRouter()


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


@lru_cache(maxsize=256)
def _flow_geojson_cached(
    path_text: str,
    mtime_ns: int,
    area_json: str,
    time_index: int,
    max_vectors: int,
) -> dict[str, Any]:
    arrays = _load_arrays_cached(path_text, mtime_ns)
    return flow_vectors_geojson(
        arrays,
        area=AnalysisArea.model_validate_json(area_json),
        time_index=time_index,
        max_vectors=max_vectors,
    )


def _arrays_path_for_run(run_id: UUID) -> tuple[Path, int]:
    path = coordinator.result_arrays_path(run_id)
    return path, path.stat().st_mtime_ns


def _arrays_for_run(run_id: UUID) -> ResultArrays:
    try:
        path, mtime_ns = _arrays_path_for_run(run_id)
        return _load_arrays_cached(str(path), mtime_ns)
    except (RunNotFound, ResultNotReady, ResultViewError, OSError) as exc:
        raise _map_result_error(exc) from exc


LAYER_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=31536000, immutable",
}


@router.get("/runs/{run_id}/result-metadata", response_model=ResultMetadataResponse)
def result_metadata(run_id: UUID) -> ResultMetadataResponse:
    try:
        metadata = coordinator.result_metadata(run_id)
    except (RunNotFound, ResultNotReady) as exc:
        raise _map_result_error(exc) from exc
    return ResultMetadataResponse.model_validate(metadata)


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
        path, mtime_ns = _arrays_path_for_run(run_id)
        content = _render_time_depth_cached(
            str(path),
            mtime_ns,
            time_index,
            max_px,
        )
    except (RunNotFound, ResultNotReady, ResultViewError, OSError) as exc:
        raise _map_result_error(exc) from exc
    return Response(
        content=content,
        media_type="image/png",
        headers=LAYER_CACHE_HEADERS,
    )


@router.get("/runs/{run_id}/layers/grid-resolution.png")
def grid_resolution_layer(run_id: UUID, max_px: int = 4096) -> Response:
    arrays = _arrays_for_run(run_id)
    try:
        content = render_grid_resolution_png(arrays, max_px=max_px)
    except ResultViewError as exc:
        raise _map_result_error(exc) from exc
    return Response(content=content, media_type="image/png", headers=LAYER_CACHE_HEADERS)



@router.get(
    "/runs/{run_id}/layers/flow-vectors.geojson",
    include_in_schema=False,
)
def flow_vectors_geojson_layer(
    run_id: UUID,
    time_index: int,
    max_vectors: int = Query(default=900, ge=1, le=2500),
) -> JSONResponse:
    try:
        path, mtime_ns = _arrays_path_for_run(run_id)
        record = coordinator.get(run_id)
        payload = _flow_geojson_cached(
            str(path),
            mtime_ns,
            record.config.analysis_area.model_dump_json(),
            time_index,
            max_vectors,
        )
    except (RunNotFound, ResultNotReady, ResultViewError, OSError) as exc:
        raise _map_result_error(exc) from exc
    return JSONResponse(content=payload, headers=LAYER_CACHE_HEADERS)


@router.get("/runs/{run_id}/inspect", response_model=PointInspectionResponse)
def inspect_result(
    run_id: UUID,
    lon: float = Query(ge=-180, le=180),
    lat: float = Query(ge=-90, le=90),
    time_index: int | None = Query(default=None, ge=0),
) -> PointInspectionResponse:
    arrays = _arrays_for_run(run_id)
    try:
        record = coordinator.get(run_id)
        payload = inspect_native_point(
            arrays,
            area=record.config.analysis_area,
            lon_deg=lon,
            lat_deg=lat,
            time_index=time_index,
        )
    except (RunNotFound, ResultViewError) as exc:
        raise _map_result_error(exc) from exc
    return PointInspectionResponse.model_validate(payload)
