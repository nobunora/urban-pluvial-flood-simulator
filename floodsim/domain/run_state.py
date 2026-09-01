"""Exact Phase 1 run lifecycle state machine."""

from enum import Enum


class RunState(str, Enum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    ACQUIRING_TERRAIN = "ACQUIRING_TERRAIN"
    ACQUIRING_VECTORS = "ACQUIRING_VECTORS"
    ACQUIRING_RAINFALL = "ACQUIRING_RAINFALL"
    PREPROCESSING_TERRAIN = "PREPROCESSING_TERRAIN"
    ALLOCATING_ROOF_RAIN = "ALLOCATING_ROOF_RAIN"
    BUILDING_GRID = "BUILDING_GRID"
    BUILDING_MODEL = "BUILDING_MODEL"
    ENSURING_ENGINE = "ENSURING_ENGINE"
    RUNNING_ENGINE = "RUNNING_ENGINE"
    READING_RESULTS = "READING_RESULTS"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"


class StateTransitionError(RuntimeError):
    """Raised when a lifecycle transition violates the contract."""


_NORMAL_SEQUENCE = (
    RunState.CREATED,
    RunState.VALIDATING,
    RunState.ACQUIRING_TERRAIN,
    RunState.ACQUIRING_VECTORS,
    RunState.ACQUIRING_RAINFALL,
    RunState.PREPROCESSING_TERRAIN,
    RunState.ALLOCATING_ROOF_RAIN,
    RunState.BUILDING_GRID,
    RunState.BUILDING_MODEL,
    RunState.ENSURING_ENGINE,
    RunState.RUNNING_ENGINE,
    RunState.READING_RESULTS,
    RunState.COMPLETE,
)
_TERMINAL_STATES = frozenset({RunState.COMPLETE, RunState.FAILED, RunState.CANCELLED})
_CANCELLABLE_STATES = frozenset(_NORMAL_SEQUENCE[:-1])


class RunStateMachine:
    """Own and validate one run's lifecycle state."""

    def __init__(self, state: RunState = RunState.CREATED) -> None:
        self.state = state

    def transition(self, target: RunState) -> RunState:
        current = self.state
        if current in _TERMINAL_STATES:
            raise StateTransitionError(f"terminal state {current.value} cannot transition")
        if current is RunState.CANCELLING and target is RunState.CANCELLED:
            self.state = target
            return self.state
        if target is RunState.FAILED and current is not RunState.CANCELLING:
            self.state = target
            return self.state
        if target is RunState.CANCELLING and current in _CANCELLABLE_STATES:
            self.state = target
            return self.state
        try:
            next_state = _NORMAL_SEQUENCE[_NORMAL_SEQUENCE.index(current) + 1]
        except (ValueError, IndexError) as error:
            raise StateTransitionError(
                f"illegal transition {current.value} -> {target.value}"
            ) from error
        if target is not next_state:
            raise StateTransitionError(f"illegal transition {current.value} -> {target.value}")
        self.state = target
        return self.state
