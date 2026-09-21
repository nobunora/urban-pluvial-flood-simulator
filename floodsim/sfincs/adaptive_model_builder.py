"""Backward-compatible import for the canonical Adaptive model builder."""

from floodsim.sfincs.model_builder import AdaptiveSfincsModelBuilder

SfincsAdaptiveModelBuilder = AdaptiveSfincsModelBuilder

__all__ = ["SfincsAdaptiveModelBuilder"]
