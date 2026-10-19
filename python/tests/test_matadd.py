from pathlib import Path

from tiny_gpu.kernels import MATADD_INPUT, MATADD_PROGRAM
from tiny_gpu.trace import compare_traces, read_jsonl

from tests.two_core_harness import TwoCoreHarness


def test_matadd_runs_and_writes_expected_results():
    harness = TwoCoreHarness(program=MATADD_PROGRAM, data=MATADD_INPUT)
    records = []
    cycle = 0
    while not harness.done:
        harness.service_external_memory()
        harness.settle()
        records.extend(harness.observe(cycle))
        harness.evaluate_clocked()
        harness.commit()
        cycle += 1
        if cycle > 500:
            raise AssertionError("matadd did not complete")

    # cocotb resumes in the active region at the edge, so the testbench's
    # `while not dut.done` check sees the pre-NBA value and observes one final
    # trailing cycle after the dispatcher's done register updates.
    harness.service_external_memory()
    harness.settle()
    records.extend(harness.observe(cycle))
    harness.evaluate_clocked()
    harness.commit()
    cycle += 1

    fixture = Path(__file__).resolve().parents[2] / "test/fixtures/traces/02b6c2c/matadd/compatibility.jsonl"
    expected = read_jsonl(fixture)
    compare_traces(expected, records)

    assert harness.data_memory.memory[16:24] == [0, 2, 4, 6, 8, 10, 12, 14]
    assert cycle == 178
    assert len(records) == len(expected)

