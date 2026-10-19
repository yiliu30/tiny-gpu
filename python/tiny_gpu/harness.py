"""Shared simulation phases used by the module-aligned model."""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, Sequence


class SimulationPhase(str, Enum):
    SERVICE_MEMORY = "service_memory"
    SETTLE = "settle"
    CAPTURE = "capture"
    EVALUATE_CLOCKED = "evaluate_clocked"
    COMMIT = "commit"


class SimulationModel(Protocol):
    done: bool

    def service_external_memory(self) -> None: ...

    def settle(self) -> None: ...

    def observe(self) -> Sequence[Any]: ...

    def evaluate_clocked(self) -> None: ...

    def commit(self) -> None: ...


class SimulationHarness:
    """Run one pre-edge observation and one clock edge per step."""

    def __init__(
        self,
        model: SimulationModel,
        *,
        phases: list[SimulationPhase] | None = None,
    ) -> None:
        self.model = model
        self.phases = phases
        self.snapshots: list[Sequence[Any]] = []

    def _enter(self, phase: SimulationPhase) -> None:
        if self.phases is not None:
            self.phases.append(phase)

    def step(self) -> Sequence[Any]:
        self._enter(SimulationPhase.SERVICE_MEMORY)
        self.model.service_external_memory()
        self._enter(SimulationPhase.SETTLE)
        self.model.settle()
        self._enter(SimulationPhase.CAPTURE)
        snapshot = self.model.observe()
        self.snapshots.append(snapshot)
        self._enter(SimulationPhase.EVALUATE_CLOCKED)
        self.model.evaluate_clocked()
        self._enter(SimulationPhase.COMMIT)
        self.model.commit()
        return snapshot

    def run_until_done(self, *, max_cycles: int = 100_000) -> list[Sequence[Any]]:
        while not self.model.done:
            self.step()
            if len(self.snapshots) > max_cycles:
                raise RuntimeError(f"simulation exceeded {max_cycles} cycles")
        return self.snapshots

