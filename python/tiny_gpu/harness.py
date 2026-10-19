"""Shared simulation phases used by the module-aligned model."""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, Sequence


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

    def observe(self) -> Sequence[Any]:
        """Capture the state visible before the next rising clock edge."""

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
    ) -> None:
        """Store the model and an optional phase recorder for tests."""

        self.model = model
        self.phases = phases
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
        snapshot = self.model.observe()
        self.snapshots.append(snapshot)
        self._enter(SimulationPhase.EVALUATE_CLOCKED)
        self.model.evaluate_clocked()
        self._enter(SimulationPhase.COMMIT)
        self.model.commit()
        return snapshot

    def run_until_done(self, *, max_cycles: int = 100_000) -> list[Sequence[Any]]:
        """Step until the model reports completion, with a cycle limit."""

        while not self.model.done:
            self.step()
            if len(self.snapshots) > max_cycles:
                raise RuntimeError(f"simulation exceeded {max_cycles} cycles")
        return self.snapshots

