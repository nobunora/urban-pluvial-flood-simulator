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

EXPECTED_PYTHON = (3, 12, 10)
EXPECTED_PACKAGES = {
    "fastapi": "0.141.1",
    "geopandas": "1.1.4",
    "hydromt": "1.4.1",
    "hydromt-sfincs": "2.0.0rc3",
    "netCDF4": "1.7.4",
    "numpy": "2.5.2",
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
            "npm was not found. Install Node.js 22, or rerun with --skip-build only if "
            "floodsim/static already contains a current frontend build."
        )
    return npm


def _node_major_version() -> int:
    node = shutil.which("node.exe") or shutil.which("node")
    if node is None:
        raise SystemExit("Node.js was not found. Install Node.js 22.")
    result = subprocess.run(
        [node, "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip().removeprefix("v")
    try:
        return int(value.split(".", 1)[0])
    except ValueError as exc:
        raise SystemExit(f"Could not parse Node.js version: {result.stdout.strip()}") from exc


def _build_frontend() -> None:
    major = _node_major_version()
    if major != 22:
        raise SystemExit(f"Node.js 22 is required for the review build; found major {major}.")
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and run the local Full 1 m user-review application."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Serve the existing floodsim/static build without running npm.",
    )
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

    if args.sfincs_bin is not None:
        sfincs_bin = args.sfincs_bin.expanduser().resolve()
        if not sfincs_bin.is_file():
            raise SystemExit(f"SFINCS executable not found: {sfincs_bin}")
        os.environ["SFINCS_BIN"] = str(sfincs_bin)

    if not args.skip_build:
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
