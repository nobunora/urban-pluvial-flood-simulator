"""Build and launch the local Full 1 m review application."""

from __future__ import annotations

import argparse
import importlib.metadata
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = REPO_ROOT / "web"
STATIC_DIR = REPO_ROOT / "floodsim" / "static"
LOCAL_SFINCS_RELATIVE_PATH = (
    Path("SFINCS_2026_01_release")
    / "SFINCS_v2.4.0_Galibier_release_exe"
    / "sfincs.exe"
)
EXPECTED_SFINCS_SHA256 = "4EF0D62212FE3B23B0DD6BBBB06A0CE01961B38C7B1089CE6EA040145EE1E673"

EXPECTED_PYTHON = (3, 12, 10)
EXPECTED_PACKAGES = {
    "fastapi": "0.141.1",
    "geopandas": "1.1.4",
    "hydromt": "1.4.1",
    "hydromt-sfincs": "2.0.0rc3",
    "netCDF4": "1.7.4",
    "numpy": "2.5.2",
    "Pillow": "11.3.0",
    "platformdirs": "4.4.0",
    "pyproj": "3.7.2",
    "rasterio": "1.5.1",
    "scipy": "1.18.0",
    "shapely": "2.1.2",
    "uvicorn": "0.52.4",
    "xarray": "2026.7.0",
    "xugrid": "0.15.3",
}


def _canonical_environment_problems() -> list[str]:
    problems: list[str] = []
    actual_python = sys.version_info[:3]
    if actual_python != EXPECTED_PYTHON:
        problems.append(
            "Python "
            + ".".join(map(str, EXPECTED_PYTHON))
            + " required; found "
            + ".".join(map(str, actual_python))
        )

    for distribution, expected in EXPECTED_PACKAGES.items():
        try:
            actual = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            problems.append(f"{distribution} {expected} required; package is not installed")
            continue
        if actual != expected:
            problems.append(f"{distribution} {expected} required; found {actual}")
    return problems


def _require_canonical_environment() -> None:
    problems = _canonical_environment_problems()
    if not problems:
        return
    details = "\n".join(f"  - {problem}" for problem in problems)
    raise SystemExit(
        "Canonical local-review environment is not active:\n"
        f"{details}\n\n"
        "Create or restore it with:\n"
        "  python -m scripts.bootstrap_local_review\n"
        "Then activate 'urban-pluvial-flood-phase0' and rerun this command."
    )


def _npm_executable() -> str:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise SystemExit(
            "npm was not found. Install Node.js >=22.12 to build the current frontend."
        )
    return npm


def _node_version() -> tuple[int, int, int]:
    node = shutil.which("node.exe") or shutil.which("node")
    if node is None:
        raise SystemExit("Node.js was not found. Install Node.js >=22.12.")
    result = subprocess.run(
        [node, "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip().removeprefix("v")
    try:
        parts = value.split(".")
        if len(parts) < 3:
            raise ValueError(value)
        return tuple(int(part) for part in parts[:3])
    except ValueError as exc:
        raise SystemExit(f"Could not parse Node.js version: {result.stdout.strip()}") from exc


def _node_version_supported(version: tuple[int, int, int]) -> bool:
    return version >= (22, 12, 0)


def _build_frontend() -> None:
    version = _node_version()
    if not _node_version_supported(version):
        found = ".".join(map(str, version))
        raise SystemExit(
            f"Node.js >=22.12 is required for the review build; found {found}."
        )
    npm = _npm_executable()
    if not (WEB_DIR / "node_modules").exists():
        print("[review] Installing pinned frontend dependencies with npm ci...")
        subprocess.run([npm, "ci"], cwd=WEB_DIR, check=True)
    print("[review] Building the local review frontend...")
    subprocess.run([npm, "run", "build"], cwd=WEB_DIR, check=True)


def _validate_static_build() -> None:
    required = [STATIC_DIR / "index.html", STATIC_DIR / "smoke.html"]
    missing = [path.relative_to(REPO_ROOT) for path in required if not path.is_file()]
    if missing:
        formatted = ", ".join(str(path) for path in missing)
        raise SystemExit(f"Frontend build is incomplete; missing: {formatted}")


def _git_worktree_roots() -> list[Path]:
    """Return local worktrees without assuming an absolute checkout path."""
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return [REPO_ROOT]
    roots = [
        Path(line.removeprefix("worktree "))
        for line in result.stdout.splitlines()
        if line.startswith("worktree ")
    ]
    return roots or [REPO_ROOT]


def _configure_sfincs(sfincs_bin: Path | None) -> None:
    """Select an existing permitted Galibier binary; never download one."""
    if sfincs_bin is not None:
        executable = sfincs_bin.expanduser().resolve()
        if not executable.is_file():
            raise SystemExit(f"SFINCS executable not found: {executable}")
        os.environ["SFINCS_BIN"] = str(executable)
        return
    if os.environ.get("SFINCS_BIN"):
        return

    from floodsim.sfincs.runner import (
        SfincsEngineUnavailable,
        resolve_sfincs_executable,
        sha256_file,
    )

    try:
        resolved = resolve_sfincs_executable()
    except SfincsEngineUnavailable:
        resolved = None
    if resolved is not None:
        os.environ["SFINCS_BIN"] = str(resolved.executable)
        print(f"[review] SFINCS: {resolved.source} / {resolved.executable}")
        return

    for root in _git_worktree_roots():
        candidate = root / LOCAL_SFINCS_RELATIVE_PATH
        if candidate.is_file() and sha256_file(candidate) == EXPECTED_SFINCS_SHA256:
            os.environ["SFINCS_BIN"] = str(candidate.resolve())
            print(f"[review] SFINCS: permitted local worktree binary / {candidate}")
            return


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and run the local Full 1 m user-review application."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--check-env",
        action="store_true",
        help="Validate the exact canonical Python environment and exit.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the review URL automatically.",
    )
    parser.add_argument(
        "--sfincs-bin",
        type=Path,
        help="Optional path to an existing permitted SFINCS executable.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    _require_canonical_environment()
    if args.check_env:
        print("[review] Canonical Python environment: OK")
        return

    os.chdir(REPO_ROOT)

    _configure_sfincs(args.sfincs_bin)

    _build_frontend()
    _validate_static_build()

    from uvicorn import run as uvicorn_run

    url = f"http://{args.host}:{args.port}/"
    print("[review] Local user-review build")
    print(f"[review] URL: {url}")
    print("[review] Scope: Full 1 m input, estimate, run, progress, cancellation")
    print("[review] Deferred: Adaptive, result map, packaging")
    if "SFINCS_BIN" not in os.environ:
        print(
            "[review] SFINCS_BIN is not set. The UI and preprocessing path can still be "
            "reviewed, but a run may stop when the engine is required."
        )

    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    uvicorn_run(
        "floodsim.api.app:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
