"""Create or update the canonical local-review conda environment."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / "environment.yml"
ENV_NAME = "urban-pluvial-flood-phase0"
MANAGERS = ("micromamba", "mamba", "conda")


def _find_manager(explicit: str | None) -> str:
    if explicit is not None:
        executable = shutil.which(explicit)
        if executable is None:
            raise SystemExit(f"Environment manager not found: {explicit}")
        return executable
    for candidate in MANAGERS:
        executable = shutil.which(candidate)
        if executable is not None:
            return executable
    raise SystemExit(
        "No conda-compatible environment manager was found. "
        "Install Miniforge/conda, mamba, or micromamba, then rerun this command."
    )


def _environment_exists(manager: str) -> bool:
    result = subprocess.run(
        [manager, "env", "list", "--json"],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    for prefix in payload.get("envs", []):
        if Path(prefix).name == ENV_NAME:
            return True
    return False


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create/update the exact Python environment used by local review and CI."
    )
    parser.add_argument(
        "--manager",
        choices=MANAGERS,
        help="Explicit conda-compatible manager. Auto-detected when omitted.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    manager = _find_manager(args.manager)
    if not ENV_FILE.is_file():
        raise SystemExit(f"Missing canonical environment file: {ENV_FILE}")

    if _environment_exists(manager):
        command = [
            manager,
            "env",
            "update",
            "--name",
            ENV_NAME,
            "--file",
            str(ENV_FILE),
            "--prune",
        ]
        action = "Updating"
    else:
        command = [
            manager,
            "env",
            "create",
            "--name",
            ENV_NAME,
            "--file",
            str(ENV_FILE),
        ]
        action = "Creating"

    print(f"[review] {action} canonical environment '{ENV_NAME}'...")
    subprocess.run(command, cwd=REPO_ROOT, check=True)
    manager_name = Path(manager).stem
    print("[review] Environment ready.")
    print(f"[review] Activate it with: {manager_name} activate {ENV_NAME}")
    print("[review] Then validate it with: python -m scripts.run_local_review --check-env")


if __name__ == "__main__":
    main()
