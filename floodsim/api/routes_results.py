"""Normalized Phase 3 result metadata API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from floodsim.api.errors import ApiContractError
from floodsim.api.routes_runs import coordinator
from floodsim.api.schemas import ResultMetadataResponse
from floodsim.orchestration.run_coordinator import ResultNotReady, RunNotFound

router = APIRouter()


@router.get("/runs/{run_id}/result-metadata", response_model=ResultMetadataResponse)
def result_metadata(run_id: UUID) -> ResultMetadataResponse:
    try:
        metadata = coordinator.result_metadata(run_id)
    except RunNotFound as exc:
        raise ApiContractError(404, exc.code, "指定された計算が見つかりません。") from exc
    except ResultNotReady as exc:
        raise ApiContractError(409, exc.code, "計算結果はまだ利用できません。") from exc
    return ResultMetadataResponse.model_validate(metadata)
