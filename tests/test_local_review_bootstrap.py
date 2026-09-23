from __future__ import annotations

from pathlib import Path

import pytest

from scripts import bootstrap_local_review


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("windows", "amd64", ("win-64", "Library/bin/micromamba.exe")),
        ("linux", "x86_64", ("linux-64", "bin/micromamba")),
        ("darwin", "arm64", ("osx-arm64", "bin/micromamba")),
    ],
)
def test_micromamba_archive_spec(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    machine: str,
    expected: tuple[str, str],
) -> None:
    monkeypatch.setattr(bootstrap_local_review.platform, "system", lambda: system)
    monkeypatch.setattr(bootstrap_local_review.platform, "machine", lambda: machine)
    assert bootstrap_local_review._micromamba_archive_spec() == expected


def test_find_manager_uses_portable_bootstrap_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap_local_review.shutil, "which", lambda _name: None)
    expected = bootstrap_local_review.EnvironmentManager(
        executable=str(Path("micromamba.exe")),
        environment={"MAMBA_ROOT_PREFIX": "test"},
    )
    monkeypatch.setattr(
        bootstrap_local_review,
        "_download_portable_micromamba",
        lambda: expected,
    )

    assert bootstrap_local_review._find_manager(None, allow_bootstrap=True) == expected


def test_find_manager_can_forbid_portable_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bootstrap_local_review.shutil, "which", lambda _name: None)

    with pytest.raises(SystemExit, match="No conda-compatible environment manager"):
        bootstrap_local_review._find_manager(None, allow_bootstrap=False)
