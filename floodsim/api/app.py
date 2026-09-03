"""FastAPI application wiring for the local application skeleton."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from floodsim import __version__
from floodsim.api.errors import ApiContractError
from floodsim.api.routes_geocode import router as geocode_router
from floodsim.api.routes_health import router as health_router
from floodsim.api.routes_rainfall import router as rainfall_router

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"

app = FastAPI(
    title="Urban Pluvial Flood Simulator",
    version=__version__,
)


@app.exception_handler(ApiContractError)
async def api_contract_error_handler(_: Request, exc: ApiContractError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "stage": exc.stage,
                "retryable": exc.retryable,
            }
        },
    )


app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(geocode_router, prefix="/api/v1", tags=["geocode"])
app.include_router(rainfall_router, prefix="/api/v1", tags=["rainfall"])
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="spa")
