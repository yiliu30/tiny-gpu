from pathlib import Path

import pytest

from tiny_gpu.gpu import Gpu
from tiny_gpu.harness import SimulationHarness
from tiny_gpu.kernels import MATADD_INPUT, MATADD_PROGRAM
from tiny_gpu.trace import compare_traces, read_jsonl


FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "test/fixtures/traces/02b6c2c"


def test_gpu_matches_full_matadd_compatibility_trace():
    gpu = Gpu()
    gpu.load_program(MATADD_PROGRAM)
    gpu.load_data(MATADD_INPUT)
    gpu.boot(thread_count=8)
    records, cycles = gpu.run_until_testbench_done()
    expected = read_jsonl(FIXTURE_ROOT / "matadd" / "compatibility.jsonl")
    compare_traces(expected, records)
    assert cycles == 178
    assert gpu.data_memory.memory[16:24] == [0, 2, 4, 6, 8, 10, 12, 14]


def test_gpu_runs_through_the_shared_simulation_harness():
    gpu = Gpu()
    gpu.load_program(MATADD_PROGRAM)
    gpu.load_data(MATADD_INPUT)
    gpu.boot(thread_count=8)

    simulation = SimulationHarness(gpu)
    records = [
        record
        for snapshot in simulation.run_until_done(max_cycles=200)
        for record in snapshot
    ]

    expected = read_jsonl(FIXTURE_ROOT / "matadd" / "compatibility.jsonl")
    compare_traces(expected, records)
    assert simulation.cycle == 178
    assert gpu.data_memory.memory[16:24] == [0, 2, 4, 6, 8, 10, 12, 14]


def test_gpu_dcr_controls_block_count():
    gpu = Gpu()
    gpu.load_program(MATADD_PROGRAM)
    gpu.load_data(MATADD_INPUT)
    gpu.boot(thread_count=8)
    assert gpu.dcr.value == 8
    assert gpu.dispatch.blocks_dispatched == 0
    gpu.service_external_memory()
    gpu.settle()
    gpu.observe(0)
    gpu.evaluate_clocked()
    gpu.commit()
    assert gpu.dispatch.blocks_dispatched == 2


def test_gpu_omits_unstarted_core_from_compatibility_trace():
    gpu = Gpu()
    gpu.load_program(MATADD_PROGRAM)
    gpu.load_data(MATADD_INPUT)
    gpu.boot(thread_count=4)
    assert {record.core for record in gpu.observe(0)} == {0}


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("data_mem_addr_bits", 7),
        ("data_mem_data_bits", 16),
        ("data_mem_num_channels", 2),
        ("program_mem_addr_bits", 7),
        ("program_mem_data_bits", 8),
        ("program_mem_num_channels", 2),
        ("num_cores", 1),
        ("threads_per_block", 2),
    ],
)
def test_gpu_rejects_unsupported_configuration(name, value):
    with pytest.raises(ValueError, match=name):
        Gpu(**{name: value})

