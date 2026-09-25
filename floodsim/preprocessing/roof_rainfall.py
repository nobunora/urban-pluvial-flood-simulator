"""Mass-conserving roof-rainfall allocation for the Full 1 m grid."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import (  # type: ignore[import-untyped]
    binary_dilation,
    find_objects,
    label,
)


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
    active_mask: np.ndarray | None = None,
    cell_area_m2: float = 1.0,
    max_distance_cells: int = 5,
    tolerance: float = 1e-9,
    progress_callback: Callable[[int, int], None] | None = None,
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

    active = np.ones(mask.shape, dtype=bool) if active_mask is None else np.asarray(active_mask, dtype=bool)
    if active.shape != mask.shape:
        raise ValueError("active_mask must match building_mask")
    weights = active.astype(np.float64)
    weights[mask] = 0.0
    components, count = label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    component_slices = find_objects(components)
    redistributed = 0
    if progress_callback is not None:
        progress_callback(0, int(count))
    callback_step = max(1, int(count) // 20) if count else 1

    height, width = mask.shape
    for component_id in range(1, count + 1):
        component_slice = component_slices[component_id - 1]
        if component_slice is None:
            continue
        rows, cols = component_slice
        row0 = max(0, rows.start - max_distance_cells)
        row1 = min(height, rows.stop + max_distance_cells)
        col0 = max(0, cols.start - max_distance_cells)
        col1 = min(width, cols.stop + max_distance_cells)
        local_labels = components[row0:row1, col0:col1]
        component = local_labels == component_id
        roof_cells = int(component.sum())
        if roof_cells == 0:
            continue
        local_mask = mask[row0:row1, col0:col1]
        recipients: np.ndarray | None = None
        for distance in range(1, max_distance_cells + 1):
            expanded = binary_dilation(
                component,
                structure=np.ones((3, 3), dtype=bool),
                iterations=distance,
            )
            candidates = expanded & ~local_mask & active[row0:row1, col0:col1]
            if np.any(candidates):
                recipients = candidates
                break
        if recipients is None:
            raise RoofRunoffNoRecipient(
                f"building component {component_id} has no ground recipient within "
                f"{max_distance_cells} cells"
            )
        recipient_count = int(recipients.sum())
        local_weights = weights[row0:row1, col0:col1]
        local_weights[recipients] += roof_cells / recipient_count
        redistributed += roof_cells
        if progress_callback is not None and (
            component_id == count or component_id % callback_step == 0
        ):
            progress_callback(component_id, int(count))

    meteorological_area = float(np.count_nonzero(active)) * cell_area_m2
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
