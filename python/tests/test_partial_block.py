from pathlib import Path

from tiny_gpu.gpu import Gpu
from tiny_gpu.trace import compare_traces, read_jsonl


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "test/fixtures/traces/02b6c2c/partial/compatibility.jsonl"
)
PARTIAL_PROGRAM = [
    0b1001000100000111,  # CONST R1, #7
    0b1111000000000000,  # RET
]


def test_partial_final_block_matches_rtl_and_preserves_stale_next_pc_quirk():
    gpu = Gpu()
    gpu.load_program(PARTIAL_PROGRAM)
    gpu.boot(thread_count=5)

    records = []
    for cycle in range(60):
        gpu.service_external_memory()
        gpu.settle()
        records.extend(gpu.observe(cycle))
        gpu.evaluate_clocked()
        gpu.commit()

    expected = read_jsonl(FIXTURE)
    compare_traces(expected, records)

    core_one_lane_zero = [
        record for record in records if record.core == 1 and record.lane == 0
    ]
    assert core_one_lane_zero
    assert all(record.pc == 0 for record in core_one_lane_zero if record.instruction_bits)
    assert all(not record.done for record in core_one_lane_zero)
    assert core_one_lane_zero[-1].registers["R1"] == 7

