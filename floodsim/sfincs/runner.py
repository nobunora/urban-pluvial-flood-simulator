"""Pinned SFINCS engine resolution and cancellable process execution."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path

SFINCS_VERSION = "2.4.0"
SFINCS_DISPLAY_VERSION = "2.4.0 Galibier"
_PROGRESS_RE = re.compile(
    r"(?P<percent>\d+(?:\.\d+)?)%\s+complete,\s+"
    r"(?P<remaining>[-+]?\d+(?:\.\d+)?|Inf|inf|-)\s+s\s+remaining"
)


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
class SfincsProgress:
    fraction: float
    engine_reported_remaining_seconds: float | None


@dataclass(frozen=True)
class SfincsRunResult:
    return_code: int
    result_path: Path
    stdout_log: Path
    stderr_log: Path
    engine: ResolvedEngine
    elapsed_seconds: float = 0.0


def parse_sfincs_progress_line(line: str) -> SfincsProgress | None:
    """Parse one official SFINCS stdout progress line."""
    match = _PROGRESS_RE.search(line)
    if match is None:
        return None
    fraction = min(1.0, max(0.0, float(match.group("percent")) / 100.0))
    raw_remaining = match.group("remaining")
    try:
        remaining = float(raw_remaining)
    except ValueError:
        remaining = None
    if remaining is not None and (remaining < 0 or remaining == float("inf")):
        remaining = None
    return SfincsProgress(fraction, remaining)


def sfincs_process_environment(base: dict[str, str] | None = None) -> dict[str, str]:
    """Return the SFINCS child environment with all logical CPUs requested."""
    env = dict(os.environ if base is None else base)
    env["OMP_NUM_THREADS"] = str(max(1, os.cpu_count() or 1))
    env["OMP_DYNAMIC"] = "FALSE"
    return env


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
    """Run SFINCS with captured logs, progress parsing, and cancellation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._cancel_process: subprocess.Popen[str] | None = None

    @property
    def process_id(self) -> int | None:
        with self._lock:
            return None if self._process is None else self._process.pid

    def cancel(self) -> None:
        """Request process termination without blocking the API caller."""
        with self._lock:
            process = self._process
            if (
                process is None
                or process.poll() is not None
                or self._cancel_process is process
            ):
                return
            self._cancel_process = process

        process.terminate()

        def escalate() -> None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if process.poll() is None:
                    process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    return
            finally:
                with self._lock:
                    if self._cancel_process is process:
                        self._cancel_process = None

        threading.Thread(
            target=escalate,
            name=f"sfincs-cancel-{process.pid}",
            daemon=True,
        ).start()

    def run(
        self,
        model_dir: str | Path,
        *,
        logs_dir: str | Path,
        engine: ResolvedEngine | None = None,
        cancel_event: threading.Event | None = None,
        progress_callback: Callable[[SfincsProgress], None] | None = None,
        line_callback: Callable[[str], None] | None = None,
    ) -> SfincsRunResult:
        root = Path(model_dir)
        logs = Path(logs_dir)
        logs.mkdir(parents=True, exist_ok=True)
        stdout_path = logs / "sfincs.stdout.log"
        stderr_path = logs / "sfincs.stderr.log"
        resolved = engine or resolve_sfincs_executable()
        started = time.monotonic()

        process_env = sfincs_process_environment()

        process = subprocess.Popen(
            [str(resolved.executable)],
            cwd=root,
            env=process_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        with self._lock:
            self._process = process

        def pump_stdout() -> None:
            assert process.stdout is not None
            with stdout_path.open("w", encoding="utf-8", newline="") as handle:
                for line in process.stdout:
                    handle.write(line)
                    handle.flush()
                    if line_callback is not None:
                        line_callback(line.rstrip("\r\n"))
                    parsed = parse_sfincs_progress_line(line)
                    if parsed is not None and progress_callback is not None:
                        progress_callback(parsed)

        def pump_stderr() -> None:
            assert process.stderr is not None
            with stderr_path.open("w", encoding="utf-8", newline="") as handle:
                for line in process.stderr:
                    handle.write(line)
                    handle.flush()
                    if line_callback is not None:
                        line_callback(f"[stderr] {line.rstrip(chr(13) + chr(10))}")

        stdout_thread = threading.Thread(target=pump_stdout, name="sfincs-stdout", daemon=True)
        stderr_thread = threading.Thread(target=pump_stderr, name="sfincs-stderr", daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        try:
            while process.poll() is None:
                if cancel_event is not None and cancel_event.wait(0.1):
                    self.cancel()
                    raise SfincsRunCancelled("SFINCS execution was cancelled")
                try:
                    process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    continue
        finally:
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
            with self._lock:
                self._process = None

        elapsed = max(0.0, time.monotonic() - started)
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
            elapsed_seconds=elapsed,
        )
