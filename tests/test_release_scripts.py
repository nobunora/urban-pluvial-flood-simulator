from __future__ import annotations

import sys
from pathlib import Path

from scripts import generate_demo_results, windows_desktop


def test_demo_events_use_the_published_mixed_extents() -> None:
    half_sizes = {
        event.event_id: event.half_size_m for event in generate_demo_results.EVENTS
    }

    assert half_sizes == {
        "2025-yokkaichi": 2000,
        "2026-chiba": 1000,
        "2019-saga": 500,
        "2026-nagoya": 500,
        "2000-nagoya": 500,
    }


def test_frozen_application_root_is_executable_parent(monkeypatch) -> None:
    executable = Path("C:/portable/UrbanPluvialFloodSimulator.exe")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert windows_desktop._application_root() == executable.parent


def test_bundled_sfincs_is_discovered_without_system_install(tmp_path, monkeypatch) -> None:
    application_root = tmp_path / "portable"
    engine_dir = application_root / "sfincs"
    engine_dir.mkdir(parents=True)
    executable = engine_dir / "sfincs.exe"
    executable.write_bytes(b"self-built engine")
    monkeypatch.setattr(windows_desktop, "_application_root", lambda: application_root)
    monkeypatch.setenv("PATH", "C:\\Windows")

    assert windows_desktop._bundled_sfincs_executable() == executable
    assert windows_desktop.os.environ["PATH"] == "C:\\Windows"
