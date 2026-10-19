from pathlib import Path

from tiny_gpu.gpu import Gpu
from tiny_gpu.kernels import MATADD_INPUT, MATADD_PROGRAM
from tiny_gpu.trace import compare_traces, read_jsonl


def test_matadd_runs_and_writes_expected_results():
    gpu = Gpu()
    gpu.load_program(MATADD_PROGRAM)
    gpu.load_data(MATADD_INPUT)
    gpu.boot(thread_count=8)
    records, cycle = gpu.run_until_testbench_done()

    fixture = Path(__file__).resolve().parents[2] / "test/fixtures/traces/02b6c2c/matadd/compatibility.jsonl"
    expected = read_jsonl(fixture)
    compare_traces(expected, records)

    assert gpu.data_memory.memory[16:24] == [0, 2, 4, 6, 8, 10, 12, 14]
    assert cycle == 178
    assert len(records) == len(expected)
