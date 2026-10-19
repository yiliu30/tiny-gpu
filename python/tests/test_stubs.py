import pytest

from tiny_gpu import isa
from tiny_gpu.stubs import IdleLsu


@pytest.mark.parametrize(
    ("read_enable", "write_enable", "name"),
    [(1, 0, "LDR"), (0, 1, "STR")],
)
def test_idle_lsu_rejects_memory_operations(read_enable, write_enable, name):
    lsu = IdleLsu()

    with pytest.raises(NotImplementedError, match=name):
        lsu.evaluate(
            reset=False,
            enable=True,
            core_state=isa.CORE_REQUEST,
            decoded_mem_read_enable=read_enable,
            decoded_mem_write_enable=write_enable,
        )


def test_idle_lsu_ignores_memory_controls_for_disabled_lane():
    lsu = IdleLsu()

    outputs = lsu.evaluate(
        reset=False,
        enable=False,
        core_state=isa.CORE_REQUEST,
        decoded_mem_read_enable=1,
        decoded_mem_write_enable=1,
    )

    assert outputs.state == isa.LSU_IDLE
    assert outputs.mem_read_valid == 0
    assert outputs.mem_write_valid == 0
