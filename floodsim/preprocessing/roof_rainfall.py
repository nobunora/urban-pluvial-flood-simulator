"""Mass-conserving roof-rainfall allocation for the Full 1 m grid."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import binary_dilation, label  # type: ignore[import-untyped]


class RoofRunoffNoRecipient(RuntimeError):
    """Raised when a building has no eligible surface recipient within 5 m."""

    code = "ROOF_RUNOFF_NO_RECIPIENT"


@dataclass(frozen=True)
class RoofRainAllocation:
    rain_weight: np.ndarray
    meteorological_area_m2: float
    hydraulic_weighted_area_m2: float
    relative_mass_error: float
    building_components: int
    redistributed_roof_cells: int


def allocate_roof_rainfall(
    building_mask: np.ndarray,
    *,
    cell_area_m2: float = 1.0,
    max_distance_cells: int = 5,
    tolerance: float = 1e-9,
) -> RoofRainAllocation:
    """Redistribute blocked-roof rainfall to nearest eligible ground cells.

    `building_mask` is indexed south-to-north by rows. Every building cell has
    allocation weight zero. The removed unit rainfall volume is added uniformly
    to the first Chebyshev ring (8-neighbour expansion) containing ground cells,
    up to five 1 m cells away.
    """
    mask = np.asarray(building_mask, dtype=bool)
    if mask.ndim != 2 or mask.size == 0:
        raise ValueError("building_mask must be a non-empty 2D array")
    if not np.isfinite(cell_area_m2) or cell_area_m2 <= 0:
        raise ValueError("cell_area_m2 must be finite and positive")
    if max_distance_cells < 1:
        raise ValueError("max_distance_cells must be at least one")

    weights = np.ones(mask.shape, dtype=np.float64)
    weights[mask] = 0.0
    components, count = label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    redistributed = 0

    for component_id in range(1, count + 1):
        component = components == component_id
        roof_cells = int(component.sum())
        if roof_cells == 0:
            continue
        recipients: np.ndarray | None = None
        for distance in range(1, max_distance_cells + 1):
            expanded = binary_dilation(
                component,
                structure=np.ones((3, 3), dtype=bool),
                iterations=distance,
            )
            candidates = expanded & ~mask
            if np.any(candidates):
                recipients = candidates
                break
        if recipients is None:
            raise RoofRunoffNoRecipient(
                f"building component {component_id} has no ground recipient within "
                f"{max_distance_cells} cells"
            )
        recipient_count = int(recipients.sum())
        weights[recipients] += roof_cells / recipient_count
        redistributed += roof_cells

    meteorological_area = float(mask.size) * cell_area_m2
    hydraulic_area = float(np.sum(weights) * cell_area_m2)
    relative_error = abs(hydraulic_area - meteorological_area) / meteorological_area
    if relative_error > tolerance:
        raise RuntimeError(
            f"roof rainfall mass error {relative_error:.3e} exceeds tolerance {tolerance:.3e}"
        )

    return RoofRainAllocation(
        rain_weight=weights,
        meteorological_area_m2=meteorological_area,
        hydraulic_weighted_area_m2=hydraulic_area,
        relative_mass_error=relative_error,
        building_components=int(count),
        redistributed_roof_cells=redistributed,
    )
