"""Area-weighted quantile classes with a compressed outlier tail."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import ROUND_CEILING, Decimal
from typing import Any

import numpy as np

_NICE = np.array([1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10])


@dataclass(frozen=True)
class AdaptiveScaleResult:
    breaks: tuple[float, ...]
    class_count: int
    mode: str
    active_area: float
    core_percentile: float
    core_threshold: float
    maximum: float
    outlier_ratio: float
    core_class_count: int
    tail_class_count: int
    snapping_applied: bool
    critical_thresholds_used: tuple[float, ...]

    def to_metadata(self) -> dict[str, Any]:
        return {**asdict(self), "boundary_labels": boundary_labels(self.breaks)}


def boundary_labels(edges: tuple[float, ...]) -> list[str]:
    """Readable labels that distinguish narrow bands and never understate max."""
    gaps = np.diff(edges)
    magnitude = max(abs(value) for value in edges)
    precision = 3
    if gaps.size and magnitude > 0:
        precision = max(
            3, min(15, int(np.ceil(np.log10(magnitude / np.min(gaps)))) + 2)
        )
    labels = [f"{value:.{precision}g}" for value in edges]
    if float(labels[-1]) < edges[-1]:
        maximum = Decimal(str(edges[-1]))
        quantum = Decimal(1).scaleb(maximum.adjusted() - precision + 1)
        labels[-1] = format(maximum.quantize(quantum, rounding=ROUND_CEILING), "f")
    return labels


def generate_adaptive_breaks(
    values: np.ndarray,
    areas: np.ndarray | None = None,
    *,
    N: int = 7,
    zero_epsilon: float = 1e-9,
    anchor_zero: bool = True,
    core_percentile: float = 0.95,
    core_fraction: float = 0.70,
    gamma: float = 1.0,
    tail_ratio_threshold: float = 2.0,
    snap_tolerance: float = 0.15,
    critical_thresholds: tuple[float, ...] = (),
) -> AdaptiveScaleResult:
    """Classify represented area; signed terrain uses its actual minimum.

    Elevation tail ratios and geometric spacing operate on offsets from the
    minimum, so translating a terrain datum does not alter class allocation.
    """
    if N < 1 or not 0 < core_percentile <= 1 or not 0 < gamma <= 1:
        raise ValueError("invalid adaptive scale configuration")
    if zero_epsilon < 0 or not 0 < core_fraction < 1 or snap_tolerance < 0:
        raise ValueError("invalid adaptive scale configuration")
    h = np.asarray(values, dtype=np.float64).ravel()
    a = (
        np.ones(h.shape)
        if areas is None
        else np.asarray(areas, dtype=np.float64).ravel()
    )
    if h.shape != a.shape:
        raise ValueError("values and areas must have matching shapes")
    valid = np.isfinite(h) & np.isfinite(a) & (a > 0)
    if anchor_zero:
        valid &= h > zero_epsilon
    h, a = h[valid], a[valid]
    if not h.size:
        return AdaptiveScaleResult(
            (0.0,), 0, "empty", 0, core_percentile, 0, 0, 0, 0, 0, False, ()
        )
    order = np.argsort(h, kind="stable")
    h, a = h[order], a[order]
    cumulative = np.cumsum(a / np.max(a))
    cumulative /= cumulative[-1]

    def quantile(p: float) -> float:
        return float(h[min(int(np.searchsorted(cumulative, p)), len(h) - 1)])

    lower = 0.0 if anchor_zero else float(h[0])
    maximum = float(h[-1])
    core = quantile(core_percentile)
    span = core - lower
    ratio = (maximum - lower) / max(span, zero_epsilon, np.finfo(float).tiny)
    count = min(N, len(np.unique(h)))
    hybrid = ratio > tail_ratio_threshold and span > zero_epsilon and count >= 5
    nc = min(count - 2, max(3, round(core_fraction * count))) if hybrid else count
    raw = [lower]
    for j in range(1, nc + 1):
        raw.append(
            quantile(core_percentile * (j / nc) ** (1 / gamma) if hybrid else j / nc)
        )
    if hybrid:
        for k in range(1, count - nc + 1):
            raw.append(
                lower
                + np.exp(
                    np.log(span)
                    + (np.log(maximum - lower) - np.log(span)) * k / (count - nc)
                )
            )
    raw[-1] = maximum
    # A repeated quantile is repaired using a genuine, unused sample boundary.
    unique = np.unique(h)
    for i in range(1, len(raw) - 1):
        if raw[i] <= raw[i - 1]:
            candidates = unique[(unique > raw[i - 1]) & (unique < maximum)]
            if candidates.size:
                raw[i] = float(candidates[0])
    raw = sorted(set(raw))
    # Preserve the requested count when repeated quantiles hide real levels.
    candidates = unique[(unique > lower) & (unique < maximum)]
    while len(raw) < count + 1 and candidates.size:
        unused = candidates[~np.isin(candidates, raw)]
        if not unused.size:
            break
        gaps = np.diff(raw)
        widest = int(np.argmax(gaps))
        midpoint = (raw[widest] + raw[widest + 1]) / 2
        raw.append(float(unused[np.argmin(np.abs(unused - midpoint))]))
        raw.sort()
    used: list[float] = []
    for threshold in critical_thresholds:
        if (
            not np.isfinite(threshold)
            or not lower < threshold < maximum
            or len(raw) < 3
        ):
            continue
        i = min(range(1, len(raw) - 1), key=lambda j: abs(raw[j] - threshold))
        tolerance = max(abs(threshold), zero_epsilon, np.finfo(float).tiny)
        if abs(raw[i] - threshold) / tolerance < snap_tolerance and min(
            threshold - raw[i - 1], raw[i + 1] - threshold
        ) >= 0.01 * min(raw[i] - raw[i - 1], raw[i + 1] - raw[i]):
            raw[i] = threshold
            used.append(threshold)
    edges = [raw[0]]
    snapped = False
    for i, value in enumerate(raw[1:-1], 1):
        candidate = value
        if value != 0 and value not in used:
            exponent = np.floor(np.log10(abs(value)))
            nice = np.unique(
                np.concatenate([_NICE * 10.0 ** (exponent + d) for d in (-1, 0, 1)])
            )
            nice *= np.sign(value)
            nice = nice[np.argsort(np.abs(nice - value))]
            allowed = nice[
                (nice > edges[-1])
                & (nice < raw[i + 1])
                & (
                    np.abs(nice - value)
                    / max(abs(value - lower), zero_epsilon, np.finfo(float).tiny)
                    <= snap_tolerance
                )
            ]
            candidate = float(allowed[0]) if allowed.size else float(f"{value:.2g}")
        if not edges[-1] < candidate < raw[i + 1]:
            candidate = value
        if candidate > edges[-1]:
            edges.append(candidate)
            snapped |= candidate != value
    if maximum > edges[-1]:
        edges.append(maximum)
    effective = len(edges) - 1
    # Constant signed fields have one color, with no fabricated interval.
    if effective == 0:
        effective = 1
    tail_count = sum(1 for edge in raw[1:] if edge > core) if hybrid else 0
    return AdaptiveScaleResult(
        tuple(edges),
        effective,
        "hybrid" if hybrid else "quantile",
        float(np.sum(a)),
        core_percentile,
        core,
        maximum,
        ratio,
        effective - tail_count,
        tail_count,
        bool(snapped),
        tuple(used),
    )


def scale_legend(
    scale: AdaptiveScaleResult, colors: tuple, unit: str = "m"
) -> list[dict[str, Any]]:
    """Use the exact same class endpoints as the renderer."""
    edges = scale.breaks
    labels = boundary_labels(edges)
    return [
        {
            "label": (
                f"{labels[0]} {unit}"
                if len(edges) == 1
                else f"{labels[i]}–{labels[i + 1]} {unit}"
            ),
            "min_m": edges[i],
            "max_m": edges[min(i + 1, len(edges) - 1)],
            "color": "#{:02X}{:02X}{:02X}".format(*colors[min(i, len(colors) - 1)][:3]),
        }
        for i in range(scale.class_count)
    ]


def color_indices(values: np.ndarray, scale: AdaptiveScaleResult) -> np.ndarray:
    return np.clip(
        np.searchsorted(scale.breaks[1:-1], values, side="left"),
        0,
        max(0, scale.class_count - 1),
    )
