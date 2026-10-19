from pathlib import Path

from tiny_gpu.gpu import Gpu
from tiny_gpu.kernels import MATMUL_INPUT, MATMUL_PROGRAM
from tiny_gpu.trace import compare_traces, read_jsonl


FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "test/fixtures/traces/02b6c2c"


def test_gpu_matches_matmul_compatibility_trace():
    gpu = Gpu()
    gpu.load_program(MATMUL_PROGRAM)
    gpu.load_data(MATMUL_INPUT)
    gpu.boot(thread_count=4)
    records, cycles = gpu.run_until_testbench_done(thread_id=1)
    expected = read_jsonl(FIXTURE_ROOT / "matmul" / "compatibility.jsonl")
    compare_traces(expected, records)

    assert cycles == 491
    assert len(records) == 491
    assert {record.thread_id for record in records} == {1}
    assert gpu.data_memory.memory[8:12] == [7, 10, 15, 22]
