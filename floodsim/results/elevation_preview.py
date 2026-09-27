"""Bounded process-local storage for disposable elevation preview images."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True)
class ElevationPreview:
    preview_id: UUID
    png: bytes
    metadata: dict[str, Any]


class ElevationPreviewStore:
    """Retain recent PNG previews without turning them into simulation runs."""

    def __init__(self, max_bytes: int = 64 * 1024**2) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.max_bytes = max_bytes
        self._records: OrderedDict[UUID, ElevationPreview] = OrderedDict()
        self._bytes = 0
        self._lock = Lock()

    def add(self, png: bytes, metadata: dict[str, Any]) -> ElevationPreview:
        if not png:
            raise ValueError("preview PNG must not be empty")
        preview = ElevationPreview(uuid4(), bytes(png), dict(metadata))
        with self._lock:
            self._records[preview.preview_id] = preview
            self._bytes += len(preview.png)
            while self._bytes > self.max_bytes and len(self._records) > 1:
                _, removed = self._records.popitem(last=False)
                self._bytes -= len(removed.png)
        return preview

    def get(self, preview_id: UUID) -> ElevationPreview | None:
        with self._lock:
            preview = self._records.get(preview_id)
            if preview is not None:
                self._records.move_to_end(preview_id)
            return preview
