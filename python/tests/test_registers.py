from tiny_gpu import isa
from tiny_gpu.registers import RegisterFile


def _clock(registers, **overrides):
    inputs = dict(
        reset=False,
        enable=True,
        block_id=0,
        core_state=isa.CORE_IDLE,
        reg_write_enable=0,
        reg_input_mux=0,
        rd_address=0,
        rs_address=0,
        rt_address=0,
        immediate=0,
        alu_out=0,
        lsu_out=0,
    )
    inputs.update(overrides)
    registers.clock(**inputs)


def test_reset_initializes_special_registers_and_clears_free_registers():
    registers = RegisterFile(threads_per_block=4, thread_id=2)
    registers.values[0] = 99
    _clock(registers, reset=True, block_id=3)
    assert registers.values[:13] == [0] * 13
    assert registers.values[13:] == [0, 4, 2]


def test_request_reads_old_registers_and_update_writes_new_value():
    registers = RegisterFile()
    registers.values[1] = 7
    registers.values[2] = 9
    _clock(registers, core_state=isa.CORE_REQUEST, rs_address=1, rt_address=2)
    assert (registers.rs, registers.rt) == (7, 9)

    _clock(
        registers,
        core_state=isa.CORE_UPDATE,
        reg_write_enable=1,
        reg_input_mux=isa.REG_ARITHMETIC,
        rd_address=3,
        alu_out=12,
    )
    assert registers.values[3] == 12


def test_read_only_registers_ignore_writes_but_block_id_tracks_dispatcher():
    registers = RegisterFile(threads_per_block=4, thread_id=3)
    _clock(
        registers,
        block_id=5,
        core_state=isa.CORE_UPDATE,
        reg_write_enable=1,
        reg_input_mux=isa.REG_CONSTANT,
        rd_address=14,
        immediate=123,
    )
    assert registers.values[13:] == [5, 4, 3]
