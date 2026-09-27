"""Bounded cache accounting for regular-grid result viewport reads."""

from dataclasses import dataclass

GIB = 1024**3


@dataclass(frozen=True)
class CacheBudget:
    available_bytes: int
    safety_headroom_bytes: int
    budget_bytes: int


def cache_budget_from_memory(
    *,
    available_bytes: int,
    total_bytes: int,
    ceiling_bytes: int = 4 * GIB,
) -> CacheBudget:
    """Return a conservative decoded-result cache budget for this host.

    The calculation deliberately permits a zero cache: rendering can then
    stream one NetCDF chunk without competing with the operating system.
    """
    if available_bytes < 0 or total_bytes <= 0 or ceiling_bytes < 0:
        raise ValueError("memory sizes must be non-negative and total must be positive")
    headroom = max(2 * GIB, total_bytes // 5)
    usable = max(0, available_bytes - headroom)
    return CacheBudget(
        available_bytes=available_bytes,
        safety_headroom_bytes=headroom,
        budget_bytes=min(ceiling_bytes, (usable * 35) // 100),
    )
