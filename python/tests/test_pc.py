from tiny_gpu import isa
from tiny_gpu.pc import PcUnit


def _evaluate(pc, **overrides):
    inputs = dict(
        reset=False,
        enable=True,
        core_state=isa.CORE_EXECUTE,
        branch_condition_mask=0,
        decoded_immediate=0,
        condition_flags_write_enable=0,
        pc_mux=0,
        alu_out=0,
        current_pc=10,
    )
    inputs.update(overrides)
    return pc.evaluate(**inputs)


def test_sequential_pc_updates_during_execute():
    pc = PcUnit()
    next_state = _evaluate(pc, core_state=isa.CORE_EXECUTE)
    assert next_state.next_pc == 11


def test_branch_uses_condition_mask_and_immediate():
    pc = PcUnit()
    pc.condition_flags = 0b100
    assert _evaluate(pc, pc_mux=1, branch_condition_mask=0b100, decoded_immediate=12).next_pc == 12
    assert _evaluate(pc, pc_mux=1, branch_condition_mask=0b001, decoded_immediate=12).next_pc == 11


def test_condition_flags_update_during_update_when_enabled():
    pc = PcUnit()
    outputs = _evaluate(
        pc,
        core_state=isa.CORE_UPDATE,
        condition_flags_write_enable=1,
        alu_out=0b101,
    )
    assert outputs.condition_flags == 0b101


def test_reset_clears_condition_flags_and_next_pc():
    pc = PcUnit()
    pc.condition_flags = 7
    pc.next_pc = 33
    reset_state = _evaluate(pc, reset=True)
    assert (reset_state.condition_flags, reset_state.next_pc) == (0, 0)
