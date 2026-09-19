"""Create/update the canonical local-review environment.

When no conda-compatible manager is installed, this helper downloads the
official micromamba portable archive into the user's local application-data
area. It does not require administrator rights or modify shell startup files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / "environment.yml"
ENV_NAME = "urban-pluvial-flood-phase0"
MANAGERS = ("micromamba", "mamba", "conda")
MICROMAMBA_BASE_URL = "https://micro.mamba.pm/api/micromamba"


@dataclass(frozen=True)
class EnvironmentManager:
    executable: str
    environment: dict[str, str]


def _local_tool_root() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "urban-pluvial-flood-simulator"


def _portable_micromamba_path() -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return _local_tool_root() / "tools" / f"micromamba{suffix}"


def _portable_micromamba_root() -> Path:
    return _local_tool_root() / "micromamba"


def _micromamba_archive_spec() -> tuple[str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows" and machine in {"amd64", "x86_64"}:
        return "win-64", "Library/bin/micromamba.exe"
    if system == "linux" and machine in {"amd64", "x86_64"}:
        return "linux-64", "bin/micromamba"
    if system == "linux" and machine in {"aarch64", "arm64"}:
        return "linux-aarch64", "bin/micromamba"
    if system == "darwin" and machine in {"arm64", "aarch64"}:
        return "osx-arm64", "bin/micromamba"
    if system == "darwin" and machine in {"x86_64", "amd64"}:
        return "osx-64", "bin/micromamba"
    raise SystemExit(
        f"Automatic portable micromamba bootstrap is unsupported on {system}/{machine}. "
        "Install conda, mamba, or micromamba manually and rerun."
    )


def _download_portable_micromamba() -> EnvironmentManager:
    target = _portable_micromamba_path()
    root_prefix = _portable_micromamba_root()
    if target.is_file():
        env = os.environ.copy()
        env["MAMBA_ROOT_PREFIX"] = str(root_prefix)
        return EnvironmentManager(str(target), env)

    platform_name, archive_member = _micromamba_archive_spec()
    url = f"{MICROMAMBA_BASE_URL}/{platform_name}/latest"
    target.parent.mkdir(parents=True, exist_ok=True)
    root_prefix.mkdir(parents=True, exist_ok=True)

    print("[review] No conda-compatible manager found.")
    print(f"[review] Downloading official portable micromamba from {url}")

    archive_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".tar.bz2", delete=False) as temporary:
            archive_path = Path(temporary.name)
            digest = hashlib.sha256()
            with urllib.request.urlopen(url, timeout=120) as response:
                while chunk := response.read(1024 * 1024):
                    temporary.write(chunk)
                    digest.update(chunk)

        print(f"[review] micromamba archive SHA-256: {digest.hexdigest().upper()}")
        with tarfile.open(archive_path, mode="r:bz2") as archive:
            try:
                member = archive.getmember(archive_member)
            except KeyError as exc:
                raise SystemExit(
                    f"Official micromamba archive did not contain {archive_member}"
                ) from exc
            source = archive.extractfile(member)
            if source is None:
                raise SystemExit(f"Could not read {archive_member} from micromamba archive")
            with source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
        if os.name != "nt":
            target.chmod(target.stat().st_mode | stat.S_IXUSR)
    finally:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)

    env = os.environ.copy()
    env["MAMBA_ROOT_PREFIX"] = str(root_prefix)
    print(f"[review] Portable micromamba ready: {target}")
    return EnvironmentManager(str(target), env)


def _find_manager(explicit: str | None, *, allow_bootstrap: bool) -> EnvironmentManager:
    if explicit is not None:
        executable = shutil.which(explicit)
        if executable is None:
            candidate = Path(explicit).expanduser()
            if candidate.is_file():
                executable = str(candidate.resolve())
        if executable is None:
            raise SystemExit(f"Environment manager not found: {explicit}")
        return EnvironmentManager(executable, os.environ.copy())

    for candidate in MANAGERS:
        executable = shutil.which(candidate)
        if executable is not None:
            return EnvironmentManager(executable, os.environ.copy())

    if allow_bootstrap:
        return _download_portable_micromamba()

    raise SystemExit(
        "No conda-compatible environment manager was found. "
        "Rerun without --no-bootstrap-manager to download portable micromamba, "
        "or install conda/mamba/micromamba manually."
    )


def _run(
    manager: EnvironmentManager,
    arguments: list[str],
    *,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [manager.executable, *arguments],
        cwd=REPO_ROOT,
        env=manager.environment,
        check=True,
        capture_output=capture_output,
        text=True,
    )


def _environment_exists(manager: EnvironmentManager) -> bool:
    result = _run(manager, ["env", "list", "--json"], capture_output=True)
    payload = json.loads(result.stdout)
    return any(Path(prefix).name == ENV_NAME for prefix in payload.get("envs", []))


def _create_or_update_environment(manager: EnvironmentManager) -> None:
    if _environment_exists(manager):
        command = [
            "env",
            "update",
            "--name",
            ENV_NAME,
            "--file",
            str(ENV_FILE),
            "--prune",
            "--yes",
        ]
        action = "Updating"
    else:
        command = [
            "env",
            "create",
            "--name",
            ENV_NAME,
            "--file",
            str(ENV_FILE),
            "--yes",
        ]
        action = "Creating"

    print(f"[review] {action} canonical environment '{ENV_NAME}'...")
    _run(manager, command)


def _run_in_environment(manager: EnvironmentManager, arguments: list[str]) -> None:
    _run(manager, ["run", "--name", ENV_NAME, *arguments])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create/update the exact Python environment used by local review and CI."
    )
    parser.add_argument(
        "--manager",
        help="Explicit conda-compatible manager name or executable path.",
    )
    parser.add_argument(
        "--no-bootstrap-manager",
        action="store_true",
        help="Do not download portable micromamba when no manager is installed.",
    )
    parser.add_argument(
        "--run-review",
        action="store_true",
        help="After environment setup/preflight, run scripts.run_local_review in it.",
    )
    parser.add_argument(
        "review_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to scripts.run_local_review after '--'.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if not ENV_FILE.is_file():
        raise SystemExit(f"Missing canonical environment file: {ENV_FILE}")

    manager = _find_manager(
        args.manager,
        allow_bootstrap=not args.no_bootstrap_manager,
    )
    print(f"[review] Environment manager: {manager.executable}")

    _create_or_update_environment(manager)

    print("[review] Verifying canonical environment...")
    _run_in_environment(
        manager,
        ["python", "-m", "scripts.run_local_review", "--check-env"],
    )
    print("[review] Canonical environment ready.")

    manager_name = Path(manager.executable).name
    print(
        "[review] No shell activation is required. Run commands through the manager, e.g.:"
    )
    print(
        f'[review] "{manager.executable}" run -n {ENV_NAME} '
        "python -m scripts.run_local_review"
    )

    if args.run_review:
        review_args = list(args.review_args)
        if review_args and review_args[0] == "--":
            review_args = review_args[1:]
        print("[review] Launching local review inside canonical environment...")
        _run_in_environment(
            manager,
            ["python", "-m", "scripts.run_local_review", *review_args],
        )


if __name__ == "__main__":
    main()
