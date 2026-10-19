from pathlib import Path

import pytest

from tiny_gpu.gpu import Gpu
from tiny_gpu.kernels import (
    MATADD_INPUT,
    MATADD_PROGRAM,
    MATMUL_INPUT,
    MATMUL_PROGRAM,
)
from tiny_gpu.trace import compare_traces, read_jsonl


FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "test/fixtures/traces/02b6c2c"


@pytest.mark.parametrize(
    ("kernel", "program", "data", "threads", "cycles", "result_slice", "result"),
    (
        (
            "matadd",
            MATADD_PROGRAM,
            MATADD_INPUT,
            8,
            178,
            slice(16, 24),
            [0, 2, 4, 6, 8, 10, 12, 14],
        ),
        (
            "matmul",
            MATMUL_PROGRAM,
            MATMUL_INPUT,
            4,
            491,
            slice(8, 12),
            [7, 10, 15, 22],
        ),
    ),
)
def test_gpu_matches_full_lane_and_architecture_trace(
    kernel,
    program,
    data,
    threads,
    cycles,
    result_slice,
    result,
):
    gpu = Gpu()
    gpu.load_program(program)
    gpu.load_data(data)
    gpu.boot(thread_count=threads)
    records, observed_cycles = gpu.run_until_testbench_done(full=True)

    expected = read_jsonl(FIXTURE_ROOT / kernel / "full.jsonl")
    compare_traces(expected, records, strict_fields=True)
    assert observed_cycles == cycles
    assert len(records) == len(expected)
    assert gpu.data_memory.memory[result_slice] == result
    assert sum("arch_state" in record.extra for record in records) == cycles
