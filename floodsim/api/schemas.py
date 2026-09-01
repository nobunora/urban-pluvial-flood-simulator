"""API response schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class EngineSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required: Literal["SFINCS 2.4.0 Galibier"] = "SFINCS 2.4.0 Galibier"


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"
    api_version: Literal["v1"] = "v1"
    application_version: str
    engine: EngineSummary
