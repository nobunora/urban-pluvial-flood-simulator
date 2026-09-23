"""Public deployment capabilities used to keep one UI build for all modes."""

from fastapi import APIRouter

from floodsim.api.runtime_config import available_demo_event_ids, runtime_config
from floodsim.api.schemas import AppConfigResponse

router = APIRouter()


@router.get("/app-config", response_model=AppConfigResponse)
def app_config() -> AppConfigResponse:
    config = runtime_config()
    return AppConfigResponse(
        mode=config.mode,
        allow_run=config.allow_run,
        allow_result_import=config.allow_result_import,
        download_url=str(config.download_url),
        demo_result_event_ids=available_demo_event_ids(config),
    )
