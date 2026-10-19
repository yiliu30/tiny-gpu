from pathlib import Path

from tiny_gpu.harness import SimulationHarness
from tiny_gpu.kernels import MATADD_INPUT, MATADD_PROGRAM
from tiny_gpu.trace import compare_traces, read_jsonl

from tests.two_core_harness import TwoCoreHarness


def test_matadd_runs_and_writes_expected_results():
    harness = TwoCoreHarness(program=MATADD_PROGRAM, data=MATADD_INPUT)
    simulation = SimulationHarness(harness)
    records = [
        record
        for snapshot in simulation.run_until_done(max_cycles=500)
        for record in snapshot
    ]

    fixture = Path(__file__).resolve().parents[2] / "test/fixtures/traces/02b6c2c/matadd/compatibility.jsonl"
    expected = read_jsonl(fixture)
    compare_traces(expected, records)

    assert harness.data_memory.memory[16:24] == [0, 2, 4, 6, 8, 10, 12, 14]
    assert simulation.cycle == 178
    assert len(records) == len(expected)

