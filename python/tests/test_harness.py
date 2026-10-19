from dataclasses import dataclass

from tiny_gpu.harness import SimulationHarness, SimulationPhase


@dataclass
class DummyModel:
    done: bool = False
    memory_phase: bool = False
    pending_memory_response: int | None = None
    observed_ready: bool = False
    state: str = "IDLE"
    next_state: str = "FETCH"
    cycle: int = 0

    def service_external_memory(self) -> None:
        self.memory_phase = True
        if self.pending_memory_response is not None:
            self.observed_ready = self.pending_memory_response == 1
            self.pending_memory_response = None

    def settle(self) -> None:
        assert self.memory_phase

    def observe(self, cycle: int):
        assert cycle == self.cycle
        return {"cycle": cycle, "state": self.state, "ready": self.observed_ready}

    def evaluate_clocked(self) -> None:
        self.next_state = self.state

    def commit(self) -> None:
        self.state = self.next_state
        self.cycle += 1
        self.memory_phase = False
        if self.cycle == 3:
            self.done = True


def test_harness_observes_before_edge_and_services_memory_first():
    phases = []
    model = DummyModel()
    harness = SimulationHarness(model, phases=phases)

    first = harness.step()
    assert first == {"cycle": 0, "state": "IDLE", "ready": False}
    assert model.state == "IDLE"
    assert phases[:5] == [
        SimulationPhase.SERVICE_MEMORY,
        SimulationPhase.SETTLE,
        SimulationPhase.CAPTURE,
        SimulationPhase.EVALUATE_CLOCKED,
        SimulationPhase.COMMIT,
    ]

    model.pending_memory_response = 1
    second = harness.step()
    assert second["cycle"] == 1
    assert second["ready"] is True


def test_run_until_done_includes_terminal_observed_cycle():
    model = DummyModel()
    harness = SimulationHarness(model)
    snapshots = harness.run_until_done(max_cycles=10)
    assert [snapshot["cycle"] for snapshot in snapshots] == [0, 1, 2, 3]
    assert harness.cycle == 4
    assert model.done is True


def test_custom_observer_receives_harness_cycle():
    observed_cycles = []

    def observe(cycle: int):
        observed_cycles.append(cycle)
        return (cycle,)

    harness = SimulationHarness(DummyModel(), observe=observe)
    harness.step()
    harness.step()

    assert observed_cycles == [0, 1]
    assert harness.snapshots == [(0,), (1,)]
