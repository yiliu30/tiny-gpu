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

