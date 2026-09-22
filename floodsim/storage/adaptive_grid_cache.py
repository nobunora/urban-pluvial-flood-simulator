"""Persistent cache for deterministic Adaptive grid classification."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

import numpy as np

from floodsim.preprocessing.adaptive_grid import (
    ADAPTIVE_THRESHOLD_IDENTITY,
    AdaptiveGridPolicy,
    AdaptiveGridProduct,
)
from floodsim.storage.run_store import atomic_write_json

_SCHEMA = "adaptive-grid-classification-v1"


class AdaptiveGridCache:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root) / "adaptive_grid"

    @staticmethod
    def key_for(prepared_grid_key: str, policy: AdaptiveGridPolicy) -> str:
        payload = {
            "schema": _SCHEMA,
            "prepared_grid_key": prepared_grid_key,
            "threshold_identity": ADAPTIVE_THRESHOLD_IDENTITY,
            "policy": asdict(policy),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()[:24]

    def load(
        self,
        prepared_grid_key: str,
        policy: AdaptiveGridPolicy,
    ) -> tuple[str, AdaptiveGridProduct] | None:
        key = self.key_for(prepared_grid_key, policy)
        entry = self.root / key
        arrays_path = entry / "adaptive_grid.npz"
        metadata_path = entry / "metadata.json"
        if not arrays_path.is_file() or not metadata_path.is_file():
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("schema") != _SCHEMA or metadata.get("key") != key:
                return None
            with np.load(arrays_path, allow_pickle=False) as archive:
                resolution = np.asarray(archive["resolution_m"], dtype=np.int16)
                level = np.asarray(archive["level"], dtype=np.int8)
                reason = np.asarray(archive["refinement_reason"], dtype="<U32")
            if resolution.ndim != 2 or level.shape != resolution.shape or reason.shape != resolution.shape:
                return None
            product = AdaptiveGridProduct(
                resolution_m=resolution,
                level=level,
                refinement_reason=reason,
                plane_fit_metrics={},
                cell_count_by_level={str(k): int(v) for k, v in metadata["cell_count_by_level"].items()},
                total_hydraulic_cells=int(metadata["total_hydraulic_cells"]),
                full_1m_equivalent_cells=int(metadata["full_1m_equivalent_cells"]),
                reduction_ratio=float(metadata["reduction_ratio"]),
                threshold_identity=str(metadata["threshold_identity"]),
                active_levels_m=tuple(int(v) for v in metadata["active_levels_m"]),
                protection_counts={str(k): int(v) for k, v in metadata["protection_counts"].items()},
                hard_boundary_preserved=bool(metadata["hard_boundary_preserved"]),
            )
            return key, product
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def save(
        self,
        prepared_grid_key: str,
        policy: AdaptiveGridPolicy,
        product: AdaptiveGridProduct,
    ) -> str:
        key = self.key_for(prepared_grid_key, policy)
        entry = self.root / key
        entry.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".adaptive.", suffix=".tmp", dir=entry)
        try:
            with os.fdopen(fd, "wb") as handle:
                np.savez_compressed(
                    handle,
                    resolution_m=product.resolution_m,
                    level=product.level,
                    refinement_reason=product.refinement_reason,
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, entry / "adaptive_grid.npz")
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise
        atomic_write_json(entry / "metadata.json", {
            "schema": _SCHEMA,
            "key": key,
            "cell_count_by_level": product.cell_count_by_level,
            "total_hydraulic_cells": product.total_hydraulic_cells,
            "full_1m_equivalent_cells": product.full_1m_equivalent_cells,
            "reduction_ratio": product.reduction_ratio,
            "threshold_identity": product.threshold_identity,
            "active_levels_m": list(product.active_levels_m),
            "protection_counts": product.protection_counts,
            "hard_boundary_preserved": product.hard_boundary_preserved,
        })
        return key
