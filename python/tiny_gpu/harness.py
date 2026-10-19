"""Shared simulation phases used by the module-aligned model."""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Protocol, Sequence


class SimulationPhase(str, Enum):
    """Ordered phases used by one simulated clock step."""

    SERVICE_MEMORY = "service_memory"
    SETTLE = "settle"
    CAPTURE = "capture"
    EVALUATE_CLOCKED = "evaluate_clocked"
    COMMIT = "commit"


class SimulationModel(Protocol):
    """Operations a model must provide to the shared simulation harness."""

    done: bool

    def service_external_memory(self) -> None:
        """Return pending external-memory responses to the model."""

    def settle(self) -> None:
        """Let combinational values settle before the pre-edge capture."""

    def observe(self, cycle: int) -> Sequence[Any]:
        """Capture the state visible in ``cycle`` before the next rising edge."""

    def evaluate_clocked(self) -> None:
        """Evaluate clocked modules while they still see the old state."""

    def commit(self) -> None:
        """Publish all staged state changes together."""


class SimulationHarness:
    """Run one pre-edge observation and one clock edge per step."""

    def __init__(
        self,
        model: SimulationModel,
        *,
        phases: list[SimulationPhase] | None = None,
        observe: Callable[[int], Sequence[Any]] | None = None,
    ) -> None:
        """Store the model, observer, and optional phase recorder."""

        self.model = model
        self.phases = phases
        self._observe = observe or model.observe
        self.cycle = 0
        self.snapshots: list[Sequence[Any]] = []

    def _enter(self, phase: SimulationPhase) -> None:
        if self.phases is not None:
            self.phases.append(phase)

    def step(self) -> Sequence[Any]:
        """Run one complete service, settle, capture, evaluate, and commit cycle."""

        self._enter(SimulationPhase.SERVICE_MEMORY)
        self.model.service_external_memory()
        self._enter(SimulationPhase.SETTLE)
        self.model.settle()
        self._enter(SimulationPhase.CAPTURE)
        snapshot = self._observe(self.cycle)
        self.snapshots.append(snapshot)
        self._enter(SimulationPhase.EVALUATE_CLOCKED)
        self.model.evaluate_clocked()
        self._enter(SimulationPhase.COMMIT)
        self.model.commit()
        self.cycle += 1
        return snapshot

    def run_until_done(self, *, max_cycles: int = 100_000) -> list[Sequence[Any]]:
        """Run until completion, preserving the testbench trailing-cycle observation."""

        while True:
            if self.cycle >= max_cycles:
                raise RuntimeError(f"simulation exceeded {max_cycles} cycles")
            done_before_edge = bool(self.model.done)
            self.step()
            if done_before_edge:
                break
        return self.snapshots
