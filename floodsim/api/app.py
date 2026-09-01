"""FastAPI application wiring for the local application skeleton."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from floodsim import __version__
from floodsim.api.routes_health import router as health_router

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"

app = FastAPI(
    title="Urban Pluvial Flood Simulator",
    version=__version__,
)
app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="spa")
