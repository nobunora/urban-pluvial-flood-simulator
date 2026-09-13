"""Build and launch the local Full 1 m review application."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import threading
import webbrowser
from pathlib import Path

import uvicorn

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = REPO_ROOT / "web"
STATIC_DIR = REPO_ROOT / "floodsim" / "static"


def _npm_executable() -> str:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise SystemExit(
            "npm was not found. Install Node.js 22, or rerun with --skip-build only if "
            "floodsim/static already contains a current frontend build."
        )
    return npm


def _build_frontend() -> None:
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
    os.chdir(REPO_ROOT)

    if args.sfincs_bin is not None:
        sfincs_bin = args.sfincs_bin.expanduser().resolve()
        if not sfincs_bin.is_file():
            raise SystemExit(f"SFINCS executable not found: {sfincs_bin}")
        os.environ["SFINCS_BIN"] = str(sfincs_bin)

    if not args.skip_build:
        _build_frontend()
    _validate_static_build()

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

    uvicorn.run(
        "floodsim.api.app:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
