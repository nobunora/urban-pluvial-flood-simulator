"""Filesystem + JSON storage for one-run local execution."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID


def atomic_write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


class RunStore:
    """Own the deterministic directory layout for local simulation runs."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def run_dir(self, run_id: UUID | str) -> Path:
        return self.root / str(run_id)

    def ensure_run(self, run_id: UUID | str) -> Path:
        root = self.run_dir(run_id)
        for name in ("logs", "source_refs", "prepared", "model", "results"):
            (root / name).mkdir(parents=True, exist_ok=True)
        return root

    def write_run_config(self, run_id: UUID | str, payload: dict[str, Any]) -> Path:
        path = self.ensure_run(run_id) / "run_config.json"
        atomic_write_json(path, payload)
        return path

    def write_manifest(self, run_id: UUID | str, payload: dict[str, Any]) -> Path:
        path = self.ensure_run(run_id) / "manifest.json"
        atomic_write_json(path, payload)
        return path

    def read_manifest(self, run_id: UUID | str) -> dict[str, Any] | None:
        path = self.run_dir(run_id) / "manifest.json"
        if not path.is_file():
            return None
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise TypeError("manifest root must be an object")
        return value
