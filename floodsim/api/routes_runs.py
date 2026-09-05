"""Run lifecycle and resource-estimate API routes."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Iterator
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from floodsim.api.errors import ApiContractError
from floodsim.api.schemas import (
    CancelRunResponse,
    ResourceEstimateRequest,
    ResourceEstimateResponse,
    RunCreateResponse,
    RunStatusResponse,
)
from floodsim.domain.run_config import RunConfig
from floodsim.domain.run_state import RunState
from floodsim.orchestration.run_coordinator import (
    STAGE_LABELS,
    AdaptiveNotAvailable,
    ResultNotReady,
    RunAlreadyActive,
    RunCoordinator,
    RunNotFound,
)

router = APIRouter()
coordinator = RunCoordinator()


def _require_json(request: Request) -> None:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise ApiContractError(
            415,
            "INPUT_UNSUPPORTED_CONTENT_TYPE",
            "Content-Type は application/json を指定してください。",
        )


def _map_coordinator_error(error: RuntimeError) -> ApiContractError:
    if isinstance(error, RunAlreadyActive):
        return ApiContractError(409, error.code, "別の計算が実行中です。")
    if isinstance(error, RunNotFound):
        return ApiContractError(404, error.code, "指定された計算が見つかりません。")
    if isinstance(error, AdaptiveNotAvailable):
        return ApiContractError(400, error.code, "Adaptive モードはまだ利用できません。")
    if isinstance(error, ResultNotReady):
        return ApiContractError(409, error.code, "計算結果はまだ利用できません。")
    return ApiContractError(500, "INTERNAL_RUN_COORDINATOR_ERROR", "計算状態を処理できませんでした。")


def _resource_class(cells: int) -> str:
    if cells <= 250_000:
        return "small"
    if cells <= 1_000_000:
        return "medium"
    if cells <= 4_000_000:
        return "heavy"
    return "very_heavy"


@router.post("/estimate", response_model=ResourceEstimateResponse)
def estimate_resources(request: Request, payload: ResourceEstimateRequest) -> ResourceEstimateResponse:
    _require_json(request)
    cells = int(math.ceil(payload.analysis_area.width_m) * math.ceil(payload.analysis_area.height_m))
    classification = _resource_class(cells)
    warnings: list[str] = []
    preliminary_adaptive: int | None = None
    if payload.accuracy_mode == "adaptive":
        warnings.append("Adaptive のセル数は Phase 4 の実格子構築まで確定しません。")
    if classification in {"heavy", "very_heavy"}:
        warnings.append("Full 1 m は大規模計算です。メモリとディスク使用量を確認してください。")
    return ResourceEstimateResponse(
        full_1m_equivalent_cells=cells,
        preliminary_adaptive_cells=preliminary_adaptive,
        estimated_memory_class=classification,  # type: ignore[arg-type]
        estimated_disk_class=classification,  # type: ignore[arg-type]
        runtime_class=classification,  # type: ignore[arg-type]
        warnings=warnings,
    )


@router.post("/runs", response_model=RunCreateResponse, status_code=202)
def create_run(request: Request, config: RunConfig) -> RunCreateResponse:
    _require_json(request)
    try:
        record = coordinator.create_run(config)
    except (RunAlreadyActive, AdaptiveNotAvailable) as exc:
        raise _map_coordinator_error(exc) from exc
    return RunCreateResponse(run_id=record.run_id)


@router.get("/runs/{run_id}", response_model=RunStatusResponse)
def get_run(run_id: UUID) -> RunStatusResponse:
    try:
        record = coordinator.get(run_id)
    except RunNotFound as exc:
        raise _map_coordinator_error(exc) from exc
    with record.lock:
        state = record.machine.state
        return RunStatusResponse(
            run_id=record.run_id,
            state=state,
            stage_code=state.value,
            stage_label=STAGE_LABELS[state],
            failure_code=record.failure_code,
            failure_message="計算に失敗しました。" if record.failure_code else None,
        )


@router.post("/runs/{run_id}/cancel", response_model=CancelRunResponse)
def cancel_run(request: Request, run_id: UUID) -> CancelRunResponse:
    _require_json(request)
    try:
        record = coordinator.cancel(run_id)
    except RunNotFound as exc:
        raise _map_coordinator_error(exc) from exc
    return CancelRunResponse(run_id=record.run_id, state=record.machine.state)


def _sse_stream(run_id: UUID, after: int) -> Iterator[str]:
    sequence = max(0, after)
    while True:
        try:
            events = coordinator.events_after(run_id, sequence)
            record = coordinator.get(run_id)
        except RunNotFound:
            return
        for event in events:
            sequence = event.sequence
            payload = json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":"))
            yield f"id: {event.sequence}\nevent: run-state\ndata: {payload}\n\n"
        with record.lock:
            terminal = record.machine.state in {RunState.COMPLETE, RunState.FAILED, RunState.CANCELLED}
        if terminal and not coordinator.events_after(run_id, sequence):
            return
        time.sleep(0.25)


@router.get("/runs/{run_id}/events")
def run_events(run_id: UUID, after: int = 0) -> StreamingResponse:
    try:
        coordinator.get(run_id)
    except RunNotFound as exc:
        raise _map_coordinator_error(exc) from exc
    return StreamingResponse(
        _sse_stream(run_id, after),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
