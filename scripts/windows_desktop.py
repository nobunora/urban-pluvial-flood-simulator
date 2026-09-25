"""Windows portable application entry point for the PyInstaller distribution."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser
from pathlib import Path


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Urban Pluvial Flood Simulator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--sfincs-bin", type=Path)
    parser.add_argument("--verify-model-import", action="store_true")
    return parser.parse_args()


def _distribution_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def _configure_native_data() -> None:
    root = _distribution_root()
    for environment_name, directory_name in (("PROJ_DATA", "proj_data"), ("GDAL_DATA", "gdal_data")):
        data_directory = root / directory_name
        if data_directory.is_dir():
            os.environ.setdefault(environment_name, str(data_directory))
    if root.is_dir():
        os.environ["PATH"] = f"{root}{os.pathsep}{os.environ.get('PATH', '')}"
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(root))


def main() -> None:
    args = _arguments()
    # HydroMT-SFINCS rc3 interprets DEBUG as an integer setting.
    if os.environ.get("DEBUG", "").strip().casefold() == "release":
        os.environ.pop("DEBUG", None)
    _configure_native_data()
    if args.sfincs_bin is not None:
        executable = args.sfincs_bin.expanduser().resolve()
        if not executable.is_file():
            raise SystemExit(f"SFINCS executable not found: {executable}")
        os.environ["SFINCS_BIN"] = str(executable)

    if args.verify_model_import:
        from floodsim.sfincs.model_builder import _load_sfincs_model

        _load_sfincs_model()
        print("HydroMT-SFINCS model import: OK")
        return

    from uvicorn import run as uvicorn_run

    from floodsim.api.app import app

    url = f"http://{args.host}:{args.port}/"
    print(f"Urban Pluvial Flood Simulator: {url}")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn_run(app, host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
