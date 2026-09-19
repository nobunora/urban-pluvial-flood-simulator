from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from scripts import run_local_review


def test_canonical_environment_problems_reports_python_and_package_mismatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_local_review, "EXPECTED_PYTHON", (9, 9, 9))
    monkeypatch.setattr(run_local_review, "EXPECTED_PACKAGES", {"demo-package": "1.2.3"})
    monkeypatch.setattr(
        run_local_review.importlib.metadata,
        "version",
        lambda _name: "9.9.9",
    )

    problems = run_local_review._canonical_environment_problems()

    assert any("Python 9.9.9 required" in problem for problem in problems)
    assert "demo-package 1.2.3 required; found 9.9.9" in problems


def test_canonical_environment_problems_accepts_exact_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_local_review, "EXPECTED_PYTHON", sys.version_info[:3])
    monkeypatch.setattr(run_local_review, "EXPECTED_PACKAGES", {"demo-package": "1.2.3"})
    monkeypatch.setattr(
        run_local_review.importlib.metadata,
        "version",
        lambda _name: "1.2.3",
    )

    assert run_local_review._canonical_environment_problems() == []


def test_node_version_parses_node_24(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_local_review.shutil, "which", lambda name: "node" if "node" in name else None)
    monkeypatch.setattr(
        run_local_review.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="v24.15.0\n"),
    )

    assert run_local_review._node_version() == (24, 15, 0)


def test_node_version_rejects_unparseable_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_local_review.shutil, "which", lambda name: "node" if "node" in name else None)
    monkeypatch.setattr(
        run_local_review.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="unknown\n"),
    )

    with pytest.raises(SystemExit, match="Could not parse Node.js version"):
        run_local_review._node_version()


@pytest.mark.parametrize(
    ("version", "supported"),
    [
        ((22, 11, 0), False),
        ((22, 12, 0), True),
        ((24, 15, 0), True),
    ],
)
def test_node_version_support(version: tuple[int, int, int], supported: bool) -> None:
    assert run_local_review._node_version_supported(version) is supported
