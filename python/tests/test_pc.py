from tiny_gpu import isa
from tiny_gpu.pc import PcUnit


def _evaluate(pc, **overrides):
    inputs = dict(
        reset=False,
        enable=True,
        core_state=isa.CORE_EXECUTE,
        decoded_nzp=0,
        decoded_immediate=0,
        nzp_write_enable=0,
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


def test_branch_uses_nzp_mask_and_immediate():
    pc = PcUnit()
    pc.nzp = 0b100
    assert _evaluate(pc, pc_mux=1, decoded_nzp=0b100, decoded_immediate=12).next_pc == 12
    assert _evaluate(pc, pc_mux=1, decoded_nzp=0b001, decoded_immediate=12).next_pc == 11


def test_nzp_updates_during_update_when_enabled():
    pc = PcUnit()
    outputs = _evaluate(pc, core_state=isa.CORE_UPDATE, nzp_write_enable=1, alu_out=0b101)
    assert outputs.nzp == 0b101


def test_reset_clears_nzp_and_next_pc():
    pc = PcUnit()
    pc.nzp = 7
    pc.next_pc = 33
    reset_state = _evaluate(pc, reset=True)
    assert (reset_state.nzp, reset_state.next_pc) == (0, 0)
