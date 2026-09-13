"""Single-active-run coordinator for the Phase 3 Full 1 m workflow."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

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
    SfincsRunCancelled,
    SfincsRunner,
    resolve_sfincs_executable,
)
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
    lock: threading.RLock = field(default_factory=threading.RLock)


class RunCoordinator:
    """Own lifecycle mutation and one background worker for Full 1 m runs."""

    def __init__(
        self,
        *,
        runs_root: str | Path | None = None,
        elevation_provider: Any | None = None,
        vector_acquirer: Callable[..., Any] = acquire_vectors,
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
        self.vector_acquirer = vector_acquirer
        self.rainfall_resolver = rainfall_resolver
        self.catalog_provider = catalog_provider or JmaCatalogProvider()
        self.grid_builder = grid_builder
        self.model_builder = model_builder or SfincsModelBuilder()
        self.engine_resolver = engine_resolver
        self.runner_factory = runner_factory
        self.result_reader = result_reader
        self.result_normalizer = result_normalizer
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

    def _set_state(self, record: RunRecord, state: RunState, message: str) -> None:
        with record.lock:
            record.machine.transition(state)
            record.manifest = record.manifest.model_copy(update={"run_status": state})
            self._append_event(record, state, message)
            self._persist_manifest(record)

    def _check_cancel(self, record: RunRecord) -> None:
        if not record.cancel_event.is_set():
            return
        with record.lock:
            if record.machine.state is not RunState.CANCELLING:
                record.machine.transition(RunState.CANCELLING)
                record.manifest = record.manifest.model_copy(update={"run_status": RunState.CANCELLING})
                self._append_event(record, RunState.CANCELLING, "キャンセル要求を処理しています。")
            record.machine.transition(RunState.CANCELLED)
            record.manifest = record.manifest.model_copy(update={"run_status": RunState.CANCELLED})
            self._append_event(record, RunState.CANCELLED, "計算をキャンセルしました。")
            self._persist_manifest(record)
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
            if record.machine.state is not RunState.CANCELLING:
                record.machine.transition(RunState.CANCELLING)
                record.manifest = record.manifest.model_copy(update={"run_status": RunState.CANCELLING})
                self._append_event(record, RunState.CANCELLING, "キャンセルを要求しました。")
                self._persist_manifest(record)
            runner = record.runner
        if runner is not None:
            runner.cancel()
        return record

    def result_metadata(self, run_id: UUID) -> dict[str, Any]:
        record = self.get(run_id)
        with record.lock:
            if record.machine.state is not RunState.COMPLETE or record.result_metadata is None:
                raise ResultNotReady(str(run_id))
            return dict(record.result_metadata)

    def events_after(self, run_id: UUID, sequence: int = 0) -> list[RunEvent]:
        record = self.get(run_id)
        with record.lock:
            return [event for event in record.events if event.sequence > sequence]

    def _execute(self, record: RunRecord) -> None:
        run_root = self.store.ensure_run(record.run_id)
        try:
            self._set_state(record, RunState.VALIDATING, "Full 1 m入力条件を検証しています。")
            self._check_cancel(record)

            self._set_state(record, RunState.ACQUIRING_TERRAIN, "地理院標高タイルを取得しています。")
            elevation = self.elevation_provider.acquire(
                record.config.analysis_area,
                grid_m=1.0,
                cache_dir=run_root.parent.parent / "cache",
            )
            self._check_cancel(record)

            self._set_state(record, RunState.ACQUIRING_VECTORS, "PLATEAU優先で建物・道路を取得しています。")
            vectors = self.vector_acquirer(
                record.config.analysis_area,
                mode="auto",
                cache_dir=str(run_root.parent.parent / "cache"),
                out_dir=str(run_root / "source_refs"),
            )
            self._check_cancel(record)

            self._set_state(record, RunState.ACQUIRING_RAINFALL, "降雨シナリオを時間系列へ変換しています。")
            rainfall = self.rainfall_resolver(record.config, self.catalog_provider)
            self._check_cancel(record)

            self._set_state(record, RunState.PREPROCESSING_TERRAIN, "1 m地形配列を検証しています。")
            self._check_cancel(record)
            self._set_state(record, RunState.ALLOCATING_ROOF_RAIN, "建物屋根の降雨量を周辺地表へ保存的に配分します。")
            self._check_cancel(record)
            self._set_state(record, RunState.BUILDING_GRID, "Full 1 m格子・建物マスク・粗度を構築しています。")
            grid = self.grid_builder(record.config.analysis_area, elevation, vectors)

            elevation_details = elevation.provenance.source_details
            vector_provenance = vectors.provenance
            record.manifest = record.manifest.model_copy(
                update={
                    "projected_crs": grid.crs_wkt,
                    "final_grid_level_counts": {"1m": grid.cell_count},
                    "elevation_provider_counts": dict(elevation_details.get("provider_counts", {})),
                    "elevation_source_summary": {
                        "grid_m": 1.0,
                        "source_names": list(elevation.source_names),
                        "nearest_filled_cells": elevation.nearest_filled,
                    },
                    "building_provider": vector_provenance.provider_id,
                    "road_provider": vector_provenance.provider_id,
                    "provider_warnings": list(vector_provenance.warnings),
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
            execution = runner.run(
                build.model_dir,
                logs_dir=run_root / "logs",
                engine=engine,
                cancel_event=record.cancel_event,
            )
            record.runner = None
            self._check_cancel(record)

            self._set_state(record, RunState.READING_RESULTS, "SFINCS NetCDF結果を正規化しています。")
            raw_result = self.result_reader(execution.result_path)
            normalized = self.result_normalizer(
                raw_result,
                area=record.config.analysis_area,
                results_dir=run_root / "results",
                limitations=record.manifest.limitations,
            )
            record.result_metadata = normalized.metadata
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
            with record.lock:
                if record.machine.state is RunState.CANCELLING:
                    record.machine.transition(RunState.CANCELLED)
                    record.manifest = record.manifest.model_copy(update={"run_status": RunState.CANCELLED})
                    self._append_event(record, RunState.CANCELLED, "計算をキャンセルしました。")
                    self._persist_manifest(record)
        # Top-level worker boundary: persist unexpected operational failures as FAILED.
        except Exception as exc:  # noqa: BLE001
            with record.lock:
                if record.cancel_event.is_set():
                    if record.machine.state is not RunState.CANCELLING:
                        record.machine.transition(RunState.CANCELLING)
                        self._append_event(record, RunState.CANCELLING, "キャンセル要求を処理しています。")
                    record.machine.transition(RunState.CANCELLED)
                    record.manifest = record.manifest.model_copy(update={"run_status": RunState.CANCELLED})
                    self._append_event(record, RunState.CANCELLED, "計算をキャンセルしました。")
                else:
                    failing_state = record.machine.state
                    record.machine.transition(RunState.FAILED)
                    code = str(getattr(exc, "code", "INTERNAL_RUN_FAILED"))
                    record.failure_code = code
                    record.failure_message = str(exc)
                    record.manifest = record.manifest.model_copy(
                        update={
                            "run_status": RunState.FAILED,
                            "failing_stage": failing_state.value,
                            "failure_code": code,
                        }
                    )
                    self._append_event(record, RunState.FAILED, "計算に失敗しました。")
                self._persist_manifest(record)
        finally:
            record.runner = None
            with self._lock:
                if self._active_run_id == record.run_id:
                    self._active_run_id = None
