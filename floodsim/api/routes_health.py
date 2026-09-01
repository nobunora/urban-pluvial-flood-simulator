"""Health endpoint."""

from fastapi import APIRouter

from floodsim import __version__
from floodsim.api.schemas import EngineSummary, HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return readiness information without probing or launching SFINCS."""
    return HealthResponse(
        application_version=__version__,
        engine=EngineSummary(),
    )
