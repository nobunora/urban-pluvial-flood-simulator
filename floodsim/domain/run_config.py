"""Run configuration contract."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from floodsim.domain.geometry import AnalysisArea
from floodsim.domain.rainfall import RainfallScenario


class AccuracyMode(str, Enum):
    FULL_1M = "full_1m"
    UNIFORM = "uniform"
    ADAPTIVE = "adaptive"


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_area: AnalysisArea
    requested_accuracy_mode: AccuracyMode
    grid_cell_size_m: Literal[1, 2, 4] = 1
    adaptive_max_block_size_m: Literal[1, 2, 4] = 4
    rainfall: RainfallScenario
