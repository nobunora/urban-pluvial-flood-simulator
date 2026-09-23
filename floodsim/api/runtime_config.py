"""Deployment-mode settings shared by API routes and the web client."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, HttpUrl

DEFAULT_DOWNLOAD_URL = (
    "https://github.com/nobunora/urban-pluvial-flood-simulator/releases/latest"
)
DEMO_EVENT_IDS = (
    "2025-yokkaichi",
    "2026-chiba",
    "2019-saga",
    "2026-nagoya",
    "2000-nagoya",
)


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: Literal["local", "demo"]
    allow_run: bool
    allow_result_import: bool
    download_url: HttpUrl
    demo_results_dir: Path | None


def runtime_config() -> RuntimeConfig:
    mode_text = os.environ.get("FLOODSIM_APP_MODE", "local").strip().lower()
    mode: Literal["local", "demo"] = "demo" if mode_text == "demo" else "local"
    directory_text = os.environ.get("FLOODSIM_DEMO_RESULTS_DIR", "").strip()
    return RuntimeConfig(
        mode=mode,
        allow_run=mode == "local",
        allow_result_import=mode == "local",
        download_url=HttpUrl(
            os.environ.get("FLOODSIM_DOWNLOAD_URL", DEFAULT_DOWNLOAD_URL)
        ),
        demo_results_dir=Path(directory_text).resolve() if directory_text else None,
    )


def available_demo_event_ids(config: RuntimeConfig | None = None) -> list[str]:
    current = config or runtime_config()
    directory = current.demo_results_dir
    if directory is None:
        return []
    return [
        event_id
        for event_id in DEMO_EVENT_IDS
        if (directory / f"{event_id}.zip").is_file()
    ]


def demo_archive_path(
    event_id: str, config: RuntimeConfig | None = None
) -> Path | None:
    current = config or runtime_config()
    if event_id not in DEMO_EVENT_IDS or current.demo_results_dir is None:
        return None
    candidate = current.demo_results_dir / f"{event_id}.zip"
    return candidate if candidate.is_file() else None
