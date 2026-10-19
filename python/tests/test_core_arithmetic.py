import pytest

from tiny_gpu import isa
from tiny_gpu.core import Core


def test_arithmetic_program_runs_to_ret_without_memory():
    program = [
        0b1001000100000011,  # CONST R1, #3
        0b1001001000000100,  # CONST R2, #4
        0b0011001100010010,  # ADD R3, R1, R2
        0b1111000000000000,  # RET
    ]
    core = Core(threads_per_block=4)
    core.block_id = 0
    core.thread_count = 4
    core.start = 1
    for _ in range(100):
        core.program_mem_read_ready = 1
        core.program_mem_read_data = program[core.program_mem_read_address]
        core.evaluate_clocked()
        core.commit()
        if core.done:
            break
    else:
        raise AssertionError("core did not complete")

    assert core.core_state == isa.CORE_DONE
    assert core.registers[0].values[3] == 7
    assert core.registers[3].values[3] == 7


def test_inactive_lanes_do_not_execute_shared_control():
    program = [
        0b1001000100000011,  # CONST R1, #3
        0b1111000000000000,  # RET
    ]
    core = Core(threads_per_block=4)
    core.thread_count = 2
    core.start = 1
    for _ in range(12):
        core.program_mem_read_ready = 1
        core.program_mem_read_data = program[core.program_mem_read_address]
        core.evaluate_clocked()
        core.commit()

    assert [core.registers[lane].values[1] for lane in range(4)] == [3, 3, 0, 0]
    assert [record.lane for record in core.observe(0)] == [0, 1]


def _run_core_program(core, program, *, max_cycles=100):
    snapshots = []
    core.start = 1
    for _ in range(max_cycles):
        core.program_mem_read_ready = 1
        core.program_mem_read_data = program[core.program_mem_read_address]
        before = (core.current_pc, core.core_state, core.pcs[0].nzp)
        core.evaluate_clocked()
        core.commit()
        after = (core.current_pc, core.core_state, core.pcs[0].nzp)
        snapshots.append((before, after))
        if core.done:
            return snapshots
    raise AssertionError("core did not complete")


@pytest.mark.parametrize(
    ("branch_mask", "expected_after_branch_pc", "expected_pc_path", "expected_r3"),
    [
        (0b100, 6, [0, 1, 2, 3, 6, 7], 7),
        (0b001, 4, [0, 1, 2, 3, 4, 5, 7], 9),
    ],
)
def test_core_cmp_branch_updates_nzp_before_selecting_pc(
    branch_mask,
    expected_after_branch_pc,
    expected_pc_path,
    expected_r3,
):
    program = [
        0b1001000100000011,  # CONST R1, #3
        0b1001001000000100,  # CONST R2, #4
        0b0010000000010010,  # CMP R1, R2
        0b0001000000000000 | (branch_mask << 9) | 6,  # BRnzp mask, 6
        0b1001001100001001,  # CONST R3, #9 (fall through)
        0b0001111000000111,  # BRnzp 111, 7 (skip the other path)
        0b1001001100000111,  # CONST R3, #7 (branch target)
        0b1111000000000000,  # RET
    ]
    core = Core(threads_per_block=4)
    core.thread_count = 4

    snapshots = _run_core_program(core, program)

    cmp_before, cmp_after = next(
        (before, after)
        for before, after in snapshots
        if before[0] == 2 and before[1] == isa.CORE_UPDATE
    )
    assert cmp_before[2] == 0
    assert cmp_after[0] == 3
    assert cmp_after[2] == 0b100

    branch_before, branch_after = next(
        (before, after)
        for before, after in snapshots
        if before[0] == 3 and before[1] == isa.CORE_UPDATE
    )
    assert branch_before[2] == 0b100
    assert branch_after[0] == expected_after_branch_pc
    assert branch_after[1] == isa.CORE_FETCH

    pc_path = []
    for _, after in snapshots:
        if not pc_path or after[0] != pc_path[-1]:
            pc_path.append(after[0])
    assert pc_path == expected_pc_path
    assert core.registers[3].values[3] == expected_r3
