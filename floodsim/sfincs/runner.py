"""Pinned SFINCS engine resolution and cancellable process execution."""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path

SFINCS_VERSION = "2.4.0"
SFINCS_DISPLAY_VERSION = "2.4.0 Galibier"


class SfincsEngineUnavailable(RuntimeError):
    code = "SFINCS_ENGINE_UNAVAILABLE"
    retryable = False


class SfincsRunError(RuntimeError):
    code = "SFINCS_RUN_FAILED"
    retryable = False


class SfincsRunCancelled(RuntimeError):
    code = "SFINCS_RUN_CANCELLED"
    retryable = False


@dataclass(frozen=True)
class ResolvedEngine:
    executable: Path
    source: str
    sha256: str
    version: str = SFINCS_DISPLAY_VERSION


@dataclass(frozen=True)
class SfincsRunResult:
    return_code: int
    result_path: Path
    stdout_log: Path
    stderr_log: Path
    engine: ResolvedEngine


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _managed_engine_candidate() -> Path:
    root = user_data_path("urban-pluvial-flood-simulator", appauthor=False)
    system = platform.system().lower()
    machine = platform.machine().lower()
    name = "sfincs.exe" if system == "windows" else "sfincs"
    return Path(root) / "engines" / "sfincs" / SFINCS_VERSION / f"{system}-{machine}" / name


def resolve_sfincs_executable() -> ResolvedEngine:
    """Resolve a permitted local engine without downloading or redistributing it."""
    override = os.environ.get("SFINCS_BIN")
    if override:
        executable = Path(override).expanduser().resolve()
        if not executable.is_file():
            raise SfincsEngineUnavailable("SFINCS_BIN does not identify a readable file")
        return ResolvedEngine(executable, "SFINCS_BIN", sha256_file(executable))

    managed = _managed_engine_candidate()
    if managed.is_file():
        return ResolvedEngine(managed.resolve(), "managed-local", sha256_file(managed))

    raise SfincsEngineUnavailable(
        "SFINCS 2.4.0 Galibier is not available locally. "
        "Managed download is intentionally disabled until redistribution/bootstrap licensing is resolved."
    )


class SfincsRunner:
    """Run SFINCS with captured logs and cooperative cancellation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None

    @property
    def process_id(self) -> int | None:
        with self._lock:
            return None if self._process is None else self._process.pid

    def cancel(self) -> None:
        with self._lock:
            process = self._process
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def run(
        self,
        model_dir: str | Path,
        *,
        logs_dir: str | Path,
        engine: ResolvedEngine | None = None,
        cancel_event: threading.Event | None = None,
    ) -> SfincsRunResult:
        root = Path(model_dir)
        logs = Path(logs_dir)
        logs.mkdir(parents=True, exist_ok=True)
        stdout_path = logs / "sfincs.stdout.log"
        stderr_path = logs / "sfincs.stderr.log"
        resolved = engine or resolve_sfincs_executable()

        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(
                [str(resolved.executable)],
                cwd=root,
                stdout=stdout,
                stderr=stderr,
                shell=False,
            )
            with self._lock:
                self._process = process
            try:
                while process.poll() is None:
                    if cancel_event is not None and cancel_event.wait(0.1):
                        self.cancel()
                        raise SfincsRunCancelled("SFINCS execution was cancelled")
                    process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                # Normal polling path; continue until exit or cancellation.
                while process.poll() is None:
                    if cancel_event is not None and cancel_event.wait(0.1):
                        self.cancel()
                        raise SfincsRunCancelled("SFINCS execution was cancelled")
                    try:
                        process.wait(timeout=0.1)
                    except subprocess.TimeoutExpired:
                        continue
            finally:
                with self._lock:
                    self._process = None

        return_code = process.returncode
        if return_code is None:
            raise SfincsRunError("SFINCS process did not terminate")
        if return_code != 0:
            raise SfincsRunError(f"SFINCS exited with code {return_code}")
        result_path = root / "sfincs_map.nc"
        if not result_path.is_file() or result_path.stat().st_size == 0:
            raise SfincsRunError("SFINCS did not produce a readable sfincs_map.nc")
        return SfincsRunResult(
            return_code=return_code,
            result_path=result_path,
            stdout_log=stdout_path,
            stderr_log=stderr_path,
            engine=resolved,
        )
