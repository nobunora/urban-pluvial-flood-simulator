"""Run orchestration and one-active-run process policy."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from floodsim.domain.geometry import AnalysisArea
from floodsim.domain.manifest import Limitations, RunManifest
from floodsim.domain.rainfall import ConstantRainfall
from floodsim.domain.run_config import AccuracyMode, RunConfig
from floodsim.domain.run_state import RunState, RunStateMachine
from floodsim.orchestration.rainfall_resolution import resolve_rainfall
from floodsim.preprocessing.full_grid import FullGridProduct, build_full_1m_grid
from floodsim.providers.gsi_elevation import GsiElevationProvider
from floodsim.providers.vector_acquisition import acquire_vectors
from floodsim.results.normalize import NormalizedResult, normalize_regular_result
from floodsim.sfincs.engine import resolve_engine
from floodsim.sfincs.model_builder import ModelBuildResult, SfincsModelBuilder
from floodsim.sfincs.output_reader import RegularSfincsResult, read_regular_result
from floodsim.sfincs.runner import SfincsRunCancelled, SfincsRunner
from floodsim.storage.run_store import RunStore

STAGE_LABELS: dict[RunState, str] = {
    RunState.CREATED: "計算を準備しています。",
    RunState.VALIDATING: "入力条件を確認しています。",
    RunState.ACQUIRING_TERRAIN: "標高データを取得しています。",
    RunState.ACQUIRING_VECTORS: "建物・道路データを取得しています。",
    RunState.ACQUIRING_RAINFALL: "降雨条件を準備しています。",
    RunState.PREPROCESSING_TERRAIN: "1 m標高格子を準備しています。",
    RunState.ALLOCATING_ROOF_RAIN: "屋根降雨を地表へ再配分しています。",
    RunState.BUILDING_GRID: "Full 1 m格子を構築しています。",
    RunState.BUILDING_MODEL: "SFINCSモデルを構築しています。",
    RunState.ENSURING_ENGINE: "SFINCS実行環境を確認しています。",
    RunState.RUNNING_ENGINE: "SFINCSを実行しています。",
    RunState.READING_RESULTS: "SFINCS NetCDF結果を正規化しています。",
    RunState.COMPLETE: "Full 1 m計算が完了しました。",
    RunState.FAILED: "計算に失敗しました。",
    RunState.CANCELLING: "キャンセル要求を処理しています。",
    RunState.CANCELLED: "計算をキャンセルしました。",
}


class RunAlreadyActive(RuntimeError):
    code = "RUN_ALREADY_ACTIVE"


class RunNotFound(RuntimeError):
    code = "RUN_NOT_FOUND"


class ResultNotReady(RuntimeError):
    code = "RESULT_NOT_READY"


class AdaptiveNotAvailable(RuntimeError):
    code = "ADAPTIVE_NOT_AVAILABLE"


@dataclass(frozen=True)
class RunEvent:
    sequence: int
    state: RunState
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"sequence": self.sequence, "state": self.state.value, "message": self.message}


@dataclass
class RunRecord:
    run_id: UUID
    config: RunConfig
    machine: RunStateMachine
    manifest: RunManifest
    events: list[RunEvent] = field(default_factory=list)
    failure_code: str | None = None
    failure_message: str | None = None
    result_metadata: dict[str, Any] | None = None
    future: Future[None] | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    runner: SfincsRunner | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)


class RunCoordinator:
    def __init__(
        self,
        *,
        runs_root: str | Path | None = None,
        elevation_provider: Any | None = None,
        vector_acquirer: Callable[..., Any] | None = None,
        model_builder: Any | None = None,
        engine_resolver: Callable[[], Any] | None = None,
        runner_factory: Callable[[], Any] | None = None,
        result_reader: Callable[[str | Path], RegularSfincsResult] | None = None,
        result_normalizer: Callable[..., NormalizedResult] | None = None,
    ):
        self.store = RunStore(runs_root)
        self.elevation_provider = elevation_provider or GsiElevationProvider()
        self.vector_acquirer = vector_acquirer or acquire_vectors
        self.model_builder = model_builder or SfincsModelBuilder()
        self.engine_resolver = engine_resolver or resolve_engine
        self.runner_factory = runner_factory or SfincsRunner
        self.result_reader = result_reader or read_regular_result
        self.result_normalizer = result_normalizer or normalize_regular_result
        self._records: dict[UUID, RunRecord] = {}
        self._active_run_id: UUID | None = None
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="floodsim-full1m")

    @property
    def active_run_id(self) -> UUID | None:
        with self._lock:
            return self._active_run_id

    def _append_event(self, record: RunRecord, state: RunState, message: str | None = None) -> None:
        record.events.append(
            RunEvent(
                sequence=len(record.events) + 1,
                state=state,
                message=message or STAGE_LABELS[state],
            )
        )

    def _persist_manifest(self, record: RunRecord) -> None:
        self.store.write_manifest(record.run_id, record.manifest.model_dump(mode="json"))

    def _set_state(self, record: RunRecord, state: RunState, message: str | None = None) -> None:
        with record.lock:
            record.machine.transition(state)
            record.manifest = record.manifest.model_copy(update={"run_status": state})
            self._append_event(record, state, message)
            self._persist_manifest(record)

    def _check_cancel(self, record: RunRecord) -> None:
        if record.cancel_event.is_set():
            raise SfincsRunCancelled("run cancelled")

    def _rainfall_summary(self, config: RunConfig) -> dict[str, Any]:
        rainfall = config.rainfall
        if isinstance(rainfall, ConstantRainfall):
            return {
                "kind": rainfall.kind,
                "intensity_mm_per_h": rainfall.intensity_mm_per_h,
                "duration_minutes": rainfall.duration_minutes,
            }
        return rainfall.model_dump(mode="json")

    def create_run(self, config: RunConfig) -> RunRecord:
        if config.requested_accuracy_mode is AccuracyMode.ADAPTIVE:
            raise AdaptiveNotAvailable("Adaptive mode is reserved for Phase 4")
        with self._lock:
            if self._active_run_id is not None:
                active = self._records.get(self._active_run_id)
                if active is not None and not active.machine.is_terminal:
                    raise RunAlreadyActive("only one hydraulic run may execute at a time")
                self._active_run_id = None

            run_id = uuid4()
            machine = RunStateMachine()
            manifest = RunManifest(
                run_id=run_id,
                analysis_area=config.analysis_area,
                requested_accuracy_mode=config.requested_accuracy_mode,
                final_grid_mode=AccuracyMode.FULL_1M,
                rainfall=self._rainfall_summary(config),
                limitations=Limitations(),
            )
            record = RunRecord(run_id=run_id, config=config, machine=machine, manifest=manifest)
            self._append_event(record, RunState.CREATED)
            self._records[run_id] = record
            self._active_run_id = run_id
            self.store.write_run_config(run_id, config.model_dump(mode="json"))
            self._persist_manifest(record)
            record.future = self._executor.submit(self._execute, record)
            return record

    def get(self, run_id: UUID) -> RunRecord:
        with self._lock:
            record = self._records.get(run_id)
        if record is None:
            raise RunNotFound(str(run_id))
        return record

    def events_after(self, run_id: UUID, sequence: int = 0) -> list[RunEvent]:
        record = self.get(run_id)
        with record.lock:
            return [event for event in record.events if event.sequence > sequence]

    def cancel(self, run_id: UUID) -> RunRecord:
        record = self.get(run_id)
        with record.lock:
            if record.machine.is_terminal:
                return record
            record.cancel_event.set()
            if record.machine.state is not RunState.CANCELLING:
                record.machine.transition(RunState.CANCELLING)
                record.manifest = record.manifest.model_copy(update={"run_status": RunState.CANCELLING})
                self._append_event(record, RunState.CANCELLING)
                self._persist_manifest(record)
            if record.runner is not None:
                record.runner.cancel()
        return record

    def result_metadata(self, run_id: UUID) -> dict[str, Any]:
        record = self.get(run_id)
        with record.lock:
            if record.machine.state is not RunState.COMPLETE or record.result_metadata is None:
                raise ResultNotReady(str(run_id))
            return dict(record.result_metadata)

    def _execute(self, record: RunRecord) -> None:
        try:
            self._set_state(record, RunState.VALIDATING)
            self._check_cancel(record)

            self._set_state(record, RunState.ACQUIRING_TERRAIN)
            elevation = self.elevation_provider.acquire(record.config.analysis_area)
            self._check_cancel(record)

            self._set_state(record, RunState.ACQUIRING_VECTORS)
            vectors = self.vector_acquirer(record.config.analysis_area)
            self._check_cancel(record)

            self._set_state(record, RunState.ACQUIRING_RAINFALL)
            rainfall = resolve_rainfall(record.config.rainfall)
            self._check_cancel(record)

            self._set_state(record, RunState.PREPROCESSING_TERRAIN)
            self._set_state(record, RunState.ALLOCATING_ROOF_RAIN)
            self._set_state(record, RunState.BUILDING_GRID)
            full_grid: FullGridProduct = build_full_1m_grid(
                record.config.analysis_area,
                elevation,
                vectors,
            )
            record.manifest = record.manifest.model_copy(
                update={
                    "terrain_source": elevation.provenance.provider_id,
                    "building_source": vectors.provenance.provider_id,
                    "road_source": vectors.provenance.provider_id,
                    "rain_source": rainfall.source_kind,
                    "rainfall": rainfall.metadata,
                    "roof_rain_redistribution_enabled": True,
                    "roof_rain_mass_diagnostic": {
                        "meteorological_area_m2": full_grid.roof_allocation.meteorological_area_m2,
                        "hydraulic_weighted_area_m2": full_grid.roof_allocation.hydraulic_weighted_area_m2,
                        "relative_error": full_grid.roof_allocation.relative_mass_error,
                    },
                    "cell_counts_by_level": {"1m": full_grid.cell_count},
                    "total_hydraulic_cells": full_grid.cell_count,
                    "final_grid_mode": AccuracyMode.FULL_1M,
                    "preliminary_adaptive_cells": None,
                    "final_adaptive_cells": None,
                }
            )
            self._persist_manifest(record)
            self._check_cancel(record)

            self._set_state(record, RunState.BUILDING_MODEL)
            run_root = self.store.run_dir(record.run_id)
            build: ModelBuildResult = self.model_builder.build(
                run_root / "model",
                full_grid,
                rainfall,
            )
            self._check_cancel(record)

            self._set_state(record, RunState.ENSURING_ENGINE)
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
        # This is the top-level worker boundary: unexpected operational errors must
        # become a persisted FAILED run instead of escaping the executor silently.
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
