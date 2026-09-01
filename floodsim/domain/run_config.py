"""Run configuration contract."""

from enum import Enum

from pydantic import BaseModel, ConfigDict

from floodsim.domain.geometry import AnalysisArea
from floodsim.domain.rainfall import RainfallScenario


class AccuracyMode(str, Enum):
    FULL_1M = "full_1m"
    ADAPTIVE = "adaptive"


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_area: AnalysisArea
    requested_accuracy_mode: AccuracyMode
    rainfall: RainfallScenario
