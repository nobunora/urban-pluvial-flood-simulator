"""Single-active-run coordinator for the Phase 3 Full 1 m workflow."""

from __future__ import annotations

import threading
import time
import traceback
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import numpy as np
from platformdirs import user_data_path

from floodsim import __version__
from floodsim.domain.manifest import RunManifest
from floodsim.domain.run_config import AccuracyMode, RunConfig
from floodsim.domain.run_state import RunState, RunStateMachine
from floodsim.orchestration.rainfall_resolution import resolve_rainfall
from floodsim.preprocessing.full_grid import build_full_1m_grid
from floodsim.providers.gsi_elevation import GsiElevationProvider
from floodsim.providers.jma import JmaCatalogProvider
from floodsim.providers.vectors import acquire_vectors
from floodsim.results.normalize import normalize_regular_result
from floodsim.sfincs.model_builder import SfincsModelBuilder
from floodsim.sfincs.output_reader import read_regular_result
from floodsim.sfincs.runner import (
    ResolvedEngine,
    SfincsProgress,
    SfincsRunCancelled,
    SfincsRunner,
    resolve_sfincs_executable,
)
from floodsim.storage.prepared_grid_cache import PreparedGridCache
from floodsim.storage.run_store import RunStore


class RunCoordinatorError(RuntimeError):
    code = "INTERNAL_RUN_COORDINATOR_ERROR"
    retryable = False


class RunAlreadyActive(RunCoordinatorError):
    code = "RUN_ALREADY_ACTIVE"


class RunNotFound(RunCoordinatorError):
    code = "RUN_NOT_FOUND"


class AdaptiveNotAvailable(RunCoordinatorError):
    code = "GRID_ADAPTIVE_NOT_AVAILABLE"


class ResultNotReady(RunCoordinatorError):
    code = "RESULT_NOT_READY"


DEFAULT_PLATEAU_REVIEW_BUDGET_S = 20.0
DEFAULT_OSM_REVIEW_BUDGET_S = 30.0


STAGE_LABELS = {
    RunState.CREATED: "実行待機",
    RunState.VALIDATING: "入力を確認中",
    RunState.ACQUIRING_TERRAIN: "標高データを取得中",
    RunState.ACQUIRING_VECTORS: "建物・道路データを取得中",
    RunState.ACQUIRING_RAINFALL: "降雨条件を準備中",
    RunState.PREPROCESSING_TERRAIN: "地形を前処理中",
    RunState.ALLOCATING_ROOF_RAIN: "屋根降雨を再配分中",
    RunState.BUILDING_GRID: "1 m計算格子を構築中",
    RunState.BUILDING_MODEL: "SFINCSモデルを構築中",
    RunState.ENSURING_ENGINE: "SFINCSエンジンを確認中",
    RunState.RUNNING_ENGINE: "SFINCSを実行中",
    RunState.READING_RESULTS: "計算結果を読み込み中",
    RunState.COMPLETE: "完了",
    RunState.FAILED: "失敗",
    RunState.CANCELLING: "キャンセル中",
    RunState.CANCELLED: "キャンセル済み",
}


@dataclass(frozen=True)
class RunEvent:
    sequence: int
    state: RunState
    stage_code: str
    stage_label_ja: str
    message: str
    timestamp_utc: str
    progress: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "state": self.state.value,
            "stage_code": self.stage_code,
            "stage_label": self.stage_label_ja,
            "progress": self.progress,
            "message": self.message,
            "timestamp": self.timestamp_utc,
        }


@dataclass
class RunRecord:
    run_id: UUID
    config: RunConfig
    manifest: RunManifest
    machine: RunStateMachine = field(default_factory=RunStateMachine)
    events: list[RunEvent] = field(default_factory=list)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    failure_code: str | None = None
    failure_message: str | None = None
    result_metadata: dict[str, Any] | None = None
    future: Future[None] | None = None
    runner: SfincsRunner | None = None
    progress_fraction: float | None = None
    estimated_remaining_seconds: float | None = None
    activity_lines: list[str] = field(default_factory=list)
    lock: threading.RLock = field(default_factory=threading.RLock)


class RunCoordinator:
    """Own lifecycle mutation and one background worker for Full 1 m runs."""

    def __init__(
        self,
        *,
        runs_root: str | Path | None = None,
        elevation_provider: Any | None = None,
        vector_acquirer: Callable[..., Any] = acquire_vectors,
        plateau_vector_budget_s: float = DEFAULT_PLATEAU_REVIEW_BUDGET_S,
        osm_vector_budget_s: float = DEFAULT_OSM_REVIEW_BUDGET_S,
        rainfall_resolver: Callable[..., Any] = resolve_rainfall,
        catalog_provider: JmaCatalogProvider | None = None,
        grid_builder: Callable[..., Any] = build_full_1m_grid,
        model_builder: Any | None = None,
        engine_resolver: Callable[[], ResolvedEngine] = resolve_sfincs_executable,
        runner_factory: Callable[[], SfincsRunner] = SfincsRunner,
        result_reader: Callable[..., Any] = read_regular_result,
        result_normalizer: Callable[..., Any] = normalize_regular_result,
    ) -> None:
        default_root = user_data_path("urban-pluvial-flood-simulator", appauthor=False) / "runs"
        self.store = RunStore(runs_root or default_root)
        self.elevation_provider = elevation_provider or GsiElevationProvider()
        if plateau_vector_budget_s <= 0 or osm_vector_budget_s <= 0:
            raise ValueError("vector acquisition budgets must be positive")
        self.vector_acquirer = vector_acquirer
        self.plateau_vector_budget_s = plateau_vector_budget_s
        self.osm_vector_budget_s = osm_vector_budget_s
        self.rainfall_resolver = rainfall_resolver
        self.catalog_provider = catalog_provider or JmaCatalogProvider()
        self.grid_builder = grid_builder
        self.model_builder = model_builder or SfincsModelBuilder()
        self.engine_resolver = engine_resolver
        self.runner_factory = runner_factory
        self.result_reader = result_reader
        self.result_normalizer = result_normalizer
        self.prepared_cache = PreparedGridCache(self.store.root.parent / "cache")
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="floodsim-run")
        self._records: dict[UUID, RunRecord] = {}
        self._active_run_id: UUID | None = None
        self._lock = threading.RLock()

    def _manifest_payload(self, record: RunRecord) -> dict[str, Any]:
        return record.manifest.model_dump(mode="json")

    def _persist_manifest(self, record: RunRecord) -> None:
        self.store.write_manifest(record.run_id, self._manifest_payload(record))

    def _append_event(
        self,
        record: RunRecord,
        state: RunState,
        message: str,
        *,
        progress: float | None = None,
    ) -> None:
        event = RunEvent(
            sequence=len(record.events) + 1,
            state=state,
            stage_code=state.value,
            stage_label_ja=STAGE_LABELS[state],
            message=message,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            progress=progress,
        )
        record.events.append(event)

    def _append_activity(self, record: RunRecord, message: str, *, raw: bool = False) -> None:
        line = message.strip()
        if not line:
            return
        if not raw:
            line = f"[APP] {line}"
        with record.lock:
            record.activity_lines.append(line)
            if len(record.activity_lines) > 80:
                del record.activity_lines[:-80]

    def _set_state(self, record: RunRecord, state: RunState, message: str) -> None:
        with record.lock:
            record.machine.transition(state)
            record.manifest = record.manifest.model_copy(update={"run_status": state})
            self._append_event(record, state, message)
            self._append_activity(record, message)
            self._persist_manifest(record)

    def _mark_cancelled(self, record: RunRecord, message: str) -> None:
        with record.lock:
            if record.machine.state is RunState.CANCELLED:
                return
            if record.machine.state is not RunState.CANCELLING:
                record.machine.transition(RunState.CANCELLING)
                record.manifest = record.manifest.model_copy(update={"run_status": RunState.CANCELLING})
                self._append_event(record, RunState.CANCELLING, message)
            record.machine.transition(RunState.CANCELLED)
            record.manifest = record.manifest.model_copy(update={"run_status": RunState.CANCELLED})
            self._append_event(record, RunState.CANCELLED, "計算をキャンセルしました。")
            self._persist_manifest(record)

    def _check_cancel(self, record: RunRecord) -> None:
        if not record.cancel_event.is_set():
            return
        self._mark_cancelled(record, "キャンセル要求を処理しています。")
        raise SfincsRunCancelled("run cancelled")

    def create_run(self, config: RunConfig) -> RunRecord:
        if config.requested_accuracy_mode is not AccuracyMode.FULL_1M:
            raise AdaptiveNotAvailable("Adaptive mode belongs to Phase 4 and is not available yet")
        with self._lock:
            if self._active_run_id is not None:
                active = self._records.get(self._active_run_id)
                if active is not None and active.machine.state not in {
                    RunState.COMPLETE,
                    RunState.FAILED,
                    RunState.CANCELLED,
                }:
                    raise RunAlreadyActive("one simulation is already active")
            run_id = uuid4()
            manifest = RunManifest(
                application_version=__version__,
                run_id=run_id,
                created_at_utc=datetime.now(timezone.utc),
                analysis_area=config.analysis_area,
                requested_accuracy_mode=config.requested_accuracy_mode,
                run_status=RunState.CREATED,
            )
            record = RunRecord(run_id=run_id, config=config, manifest=manifest)
            self._records[run_id] = record
            self._active_run_id = run_id
            self.store.write_run_config(run_id, config.model_dump(mode="json"))
            self._append_event(record, RunState.CREATED, "計算を受け付けました。")
            self._append_activity(record, "計算を受け付けました。")
            self._persist_manifest(record)
            record.future = self._executor.submit(self._execute, record)
            return record

    def get(self, run_id: UUID) -> RunRecord:
        with self._lock:
            record = self._records.get(run_id)
        if record is None:
            raise RunNotFound(str(run_id))
        return record

    def cancel(self, run_id: UUID) -> RunRecord:
        record = self.get(run_id)
        with record.lock:
            if record.machine.state in {RunState.COMPLETE, RunState.FAILED, RunState.CANCELLED}:
                return record
            record.cancel_event.set()
            runner = record.runner
        self._mark_cancelled(record, "キャンセルを要求しました。")
        if runner is not None:
            runner.cancel()
        return record

    def result_metadata(self, run_id: UUID) -> dict[str, Any]:
        record = self.get(run_id)
        with record.lock:
            if record.machine.state is not RunState.COMPLETE or record.result_metadata is None:
                raise ResultNotReady(str(run_id))
            return dict(record.result_metadata)

    def result_arrays_path(self, run_id: UUID) -> Path:
        record = self.get(run_id)
        with record.lock:
            if record.machine.state is not RunState.COMPLETE or record.result_metadata is None:
                raise ResultNotReady(str(run_id))
            filename = record.manifest.output_files.get("normalized_arrays")
        if not filename:
            raise ResultNotReady(str(run_id))
        path = self.store.run_dir(run_id) / "results" / filename
        if not path.is_file():
            raise ResultNotReady(str(run_id))
        return path

    def events_after(self, run_id: UUID, sequence: int = 0) -> list[RunEvent]:
        record = self.get(run_id)
        with record.lock:
            return [event for event in record.events if event.sequence > sequence]

    @staticmethod
    def _array_summary(values: Any) -> dict[str, Any]:
        array = np.asarray(values)
        summary: dict[str, Any] = {
            "shape": list(array.shape),
            "dtype": str(array.dtype),
            "size": int(array.size),
        }
        if array.size and np.issubdtype(array.dtype, np.number):
            finite = np.isfinite(array)
            summary["finite_values"] = int(np.count_nonzero(finite))
            summary["nonfinite_values"] = int(array.size - np.count_nonzero(finite))
            if np.any(finite):
                summary["finite_min"] = float(np.min(array[finite]))
                summary["finite_max"] = float(np.max(array[finite]))
        return summary

    @classmethod
    def _grid_input_diagnostic(
        cls,
        record: RunRecord,
        elevation: Any,
        vectors: Any,
    ) -> dict[str, Any]:
        provenance = getattr(vectors, "provenance", None)
        return {
            "analysis_area": {
                "width_m": record.config.analysis_area.width_m,
                "height_m": record.config.analysis_area.height_m,
                "area_m2": record.config.analysis_area.area_m2,
            },
            "elevation": cls._array_summary(elevation.z),
            "vectors": {
                "provider_id": getattr(provenance, "provider_id", None),
                "buildings": len(getattr(vectors, "buildings", [])),
                "road_lines": len(getattr(vectors, "road_lines", [])),
                "road_polygons": len(getattr(vectors, "road_polygons", [])),
            },
        }

    def _persist_failure_diagnostic(
        self,
        record: RunRecord,
        *,
        failing_state: RunState,
        exc: Exception,
        runtime_diagnostic: dict[str, Any],
    ) -> str | None:
        payload = {
            "run_id": str(record.run_id),
            "stage": failing_state.value,
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
            "runtime": runtime_diagnostic,
        }
        try:
            path = self.store.write_diagnostic(
                record.run_id,
                "failure_diagnostic.json",
                payload,
            )
        except Exception:  # noqa: BLE001
            return None
        return path.relative_to(self.store.run_dir(record.run_id)).as_posix()

    def _execute(self, record: RunRecord) -> None:
        run_root = self.store.ensure_run(record.run_id)
        runtime_diagnostic: dict[str, Any] = {}
        try:
            self._set_state(record, RunState.VALIDATING, "Full 1 m入力条件を検証しています。")
            self._check_cancel(record)

            cache_entry = self.prepared_cache.load(record.config.analysis_area)
            cache_hit = cache_entry is not None

            self._set_state(
                record,
                RunState.ACQUIRING_TERRAIN,
                "準備済み地図データを再利用しています。" if cache_hit else "地理院標高タイルを取得しています。",
            )
            if cache_entry is not None:
                grid = cache_entry.grid
                cache_metadata = cache_entry.metadata
                runtime_diagnostic["prepared_grid_cache"] = {
                    "hit": True,
                    "key": cache_entry.key,
                }
                self._append_activity(record, f"prepared grid cache hit: {cache_entry.key}")
            else:
                elevation = self.elevation_provider.acquire(
                    record.config.analysis_area,
                    grid_m=1.0,
                    cache_dir=run_root.parent.parent / "cache",
                )
                runtime_diagnostic["elevation"] = self._array_summary(elevation.z)
                self._append_activity(
                    record,
                    f"標高取得完了: {elevation.z.shape[1]} × {elevation.z.shape[0]} samples",
                )
            self._check_cancel(record)

            self._set_state(
                record,
                RunState.ACQUIRING_VECTORS,
                "準備済み建物・道路データを再利用しています。" if cache_hit else "PLATEAU優先で建物・道路を取得しています。",
            )
            if not cache_hit:
                vectors = self.vector_acquirer(
                    record.config.analysis_area,
                    mode="auto",
                    cache_dir=str(run_root.parent.parent / "cache"),
                    out_dir=str(run_root / "source_refs"),
                    plateau_budget_s=self.plateau_vector_budget_s,
                    osm_budget_s=self.osm_vector_budget_s,
                    cancel_event=record.cancel_event,
                )
                runtime_diagnostic["grid_input"] = self._grid_input_diagnostic(
                    record,
                    elevation,
                    vectors,
                )
                vector_provenance = vectors.provenance
                self._append_activity(
                    record,
                    "建物・道路取得完了: "
                    f"provider={vector_provenance.provider_id}, "
                    f"buildings={len(vectors.buildings)}, "
                    f"roads={len(vectors.road_lines) + len(vectors.road_polygons)}",
                )
            self._check_cancel(record)

            self._set_state(record, RunState.ACQUIRING_RAINFALL, "降雨シナリオを時間系列へ変換しています。")
            rainfall = self.rainfall_resolver(record.config, self.catalog_provider)
            self._check_cancel(record)

            self._set_state(
                record,
                RunState.PREPROCESSING_TERRAIN,
                "準備済み1 m地形を再利用しています。" if cache_hit else "1 m地形配列を検証しています。",
            )
            self._check_cancel(record)
            self._set_state(
                record,
                RunState.ALLOCATING_ROOF_RAIN,
                "準備済み屋根雨水重みを再利用しています。" if cache_hit else "建物屋根の降雨量を周辺地表へ保存的に配分します。",
            )
            self._check_cancel(record)
            self._set_state(
                record,
                RunState.BUILDING_GRID,
                "準備済みFull 1 m格子を再利用しています。" if cache_hit else "Full 1 m格子・建物マスク・粗度を構築しています。",
            )

            if cache_hit:
                assert cache_entry is not None
                cache_metadata = cache_entry.metadata
            else:
                grid = self.grid_builder(record.config.analysis_area, elevation, vectors)
                elevation_details = elevation.provenance.source_details
                vector_provenance = vectors.provenance
                cache_metadata = {
                    "elevation_provider_counts": dict(elevation_details.get("provider_counts", {})),
                    "elevation_source_summary": {
                        "grid_m": 1.0,
                        "source_names": list(elevation.source_names),
                        "nearest_filled_cells": elevation.nearest_filled,
                    },
                    "building_provider": vector_provenance.provider_id,
                    "road_provider": vector_provenance.provider_id,
                    "provider_warnings": list(vector_provenance.warnings),
                }
                saved_entry = self.prepared_cache.save(
                    record.config.analysis_area,
                    grid,
                    metadata=cache_metadata,
                )
                runtime_diagnostic["prepared_grid_cache"] = {
                    "hit": False,
                    "key": saved_entry.key,
                }
                self._append_activity(
                    record,
                    f"Full 1 m格子構築完了: {grid.width_cells} × {grid.height_cells} cells / "
                    f"buildings={int(np.count_nonzero(grid.building_mask))} cells",
                )
                self._append_activity(record, f"prepared grid cache saved: {saved_entry.key}")

            elevation_summary = dict(cache_metadata.get("elevation_source_summary", {}))
            elevation_summary.update(
                {
                    "prepared_cache_hit": cache_hit,
                    "prepared_cache_key": self.prepared_cache.key_for(record.config.analysis_area),
                }
            )
            record.manifest = record.manifest.model_copy(
                update={
                    "projected_crs": grid.crs_wkt,
                    "final_grid_level_counts": {"1m": grid.cell_count},
                    "elevation_provider_counts": dict(cache_metadata.get("elevation_provider_counts", {})),
                    "elevation_source_summary": elevation_summary,
                    "building_provider": cache_metadata.get("building_provider"),
                    "road_provider": cache_metadata.get("road_provider"),
                    "provider_warnings": list(cache_metadata.get("provider_warnings", [])),
                    "rainfall_source": dict(rainfall.source_metadata),
                    "roof_rain_mass_diagnostic": {
                        "relative_error": grid.roof_allocation.relative_mass_error,
                        "meteorological_area_m2": grid.roof_allocation.meteorological_area_m2,
                        "hydraulic_weighted_area_m2": grid.roof_allocation.hydraulic_weighted_area_m2,
                        "building_components": grid.roof_allocation.building_components,
                    },
                }
            )
            self._persist_manifest(record)
            self._check_cancel(record)

            self._set_state(record, RunState.BUILDING_MODEL, "HydroMT-SFINCSでregular 1 mモデルを構築しています。")
            build = self.model_builder.build(run_root / "model", grid, rainfall)
            self._append_activity(record, "SFINCSモデル構築完了。")
            self._check_cancel(record)

            self._set_state(record, RunState.ENSURING_ENGINE, "SFINCS 2.4.0 Galibierを確認しています。")
            engine = self.engine_resolver()
            record.manifest = record.manifest.model_copy(
                update={
                    "sfincs_version": engine.version,
                    "sfincs_build_sha256": engine.sha256,
                    "sfincs_engine_source": engine.source,
                    "hydromt_sfincs_version": "2.0.0rc3",
                }
            )
            self._persist_manifest(record)
            self._check_cancel(record)

            self._set_state(record, RunState.RUNNING_ENGINE, "SFINCSを実行しています。")
            runner = self.runner_factory()
            record.runner = runner
            engine_started = time.monotonic()

            def append_engine_line(line: str) -> None:
                self._append_activity(record, line, raw=True)

            def update_engine_progress(progress: SfincsProgress) -> None:
                elapsed = max(0.0, time.monotonic() - engine_started)
                remaining = None
                if progress.fraction > 0.0:
                    estimated_total = elapsed / progress.fraction
                    remaining = max(0.0, estimated_total - elapsed)
                with record.lock:
                    record.progress_fraction = progress.fraction
                    record.estimated_remaining_seconds = remaining

            execution = runner.run(
                build.model_dir,
                logs_dir=run_root / "logs",
                engine=engine,
                cancel_event=record.cancel_event,
                progress_callback=update_engine_progress,
                line_callback=append_engine_line,
            )
            with record.lock:
                record.progress_fraction = 1.0
                record.estimated_remaining_seconds = 0.0
            runtime_diagnostic["sfincs_elapsed_seconds"] = execution.elapsed_seconds
            self._append_activity(record, f"SFINCS完了: {execution.elapsed_seconds:.2f} s")
            record.runner = None
            self._check_cancel(record)

            self._set_state(record, RunState.READING_RESULTS, "SFINCS NetCDF結果を正規化しています。")
            raw_result = self.result_reader(execution.result_path)
            normalized = self.result_normalizer(
                raw_result,
                area=record.config.analysis_area,
                results_dir=run_root / "results",
                limitations=record.manifest.limitations,
                provider_summary={
                    "building_provider": record.manifest.building_provider,
                    "road_provider": record.manifest.road_provider,
                    "warnings": list(record.manifest.provider_warnings),
                },
                engine_summary={
                    "sfincs_version": record.manifest.sfincs_version,
                    "sfincs_build_sha256": record.manifest.sfincs_build_sha256,
                    "sfincs_engine_source": record.manifest.sfincs_engine_source,
                    "hydromt_sfincs_version": record.manifest.hydromt_sfincs_version,
                },
                run_summary={
                    "application_version": record.manifest.application_version,
                    "requested_accuracy_mode": record.manifest.requested_accuracy_mode.value,
                    "rainfall_source": dict(record.manifest.rainfall_source),
                    "elevation_provider_counts": dict(record.manifest.elevation_provider_counts),
                    "elevation_source_summary": dict(record.manifest.elevation_source_summary),
                    "manning_defaults": dict(record.manifest.manning_defaults),
                    "boundary_policy": record.manifest.boundary_policy,
                    "roof_rain_mass_diagnostic": dict(record.manifest.roof_rain_mass_diagnostic),
                },
            )
            record.result_metadata = normalized.metadata
            self._append_activity(record, "結果読込・正規化完了。")
            record.manifest = record.manifest.model_copy(
                update={
                    "output_files": {
                        "sfincs_map_nc": execution.result_path.name,
                        "model_build_report": build.report_path.name,
                        "normalized_arrays": normalized.arrays_path.name,
                        "result_metadata": normalized.metadata_path.name,
                    }
                }
            )
            self._persist_manifest(record)
            self._set_state(record, RunState.COMPLETE, "Full 1 m計算が完了しました。")
        except SfincsRunCancelled:
            self._mark_cancelled(record, "キャンセル要求を処理しています。")
        # Top-level worker boundary: persist unexpected operational failures as FAILED.
        except Exception as exc:  # noqa: BLE001
            with record.lock:
                if record.cancel_event.is_set():
                    self._mark_cancelled(record, "キャンセル要求を処理しています。")
                else:
                    failing_state = record.machine.state
                    record.machine.transition(RunState.FAILED)
                    code = str(getattr(exc, "code", "INTERNAL_RUN_FAILED"))
                    message = str(exc) or type(exc).__name__
                    diagnostic_file = self._persist_failure_diagnostic(
                        record,
                        failing_state=failing_state,
                        exc=exc,
                        runtime_diagnostic=runtime_diagnostic,
                    )
                    record.failure_code = code
                    record.failure_message = message
                    record.manifest = record.manifest.model_copy(
                        update={
                            "run_status": RunState.FAILED,
                            "failing_stage": failing_state.value,
                            "failure_code": code,
                            "failure_exception_type": type(exc).__name__,
                            "failure_message": message,
                            "failure_diagnostic_file": diagnostic_file,
                        }
                    )
                    self._append_event(record, RunState.FAILED, "計算に失敗しました。")
                self._persist_manifest(record)
        finally:
            record.runner = None
            with self._lock:
                if self._active_run_id == record.run_id:
                    self._active_run_id = None
