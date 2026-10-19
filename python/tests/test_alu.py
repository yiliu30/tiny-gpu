import pytest

from tiny_gpu import isa
from tiny_gpu.alu import Alu


@pytest.mark.parametrize(
    ("mux", "rs", "rt", "expected"),
    [
        (isa.ALU_ADD, 2, 3, 5),
        (isa.ALU_SUB, 2, 3, 255),
        (isa.ALU_MUL, 20, 13, 4),
        (isa.ALU_DIV, 20, 3, 6),
    ],
)
def test_arithmetic_and_wrap(mux, rs, rt, expected):
    alu = Alu()
    actual = alu.evaluate(
        reset=False,
        enable=True,
        core_state=isa.CORE_EXECUTE,
        arithmetic_mux=mux,
        output_mux=0,
        rs=rs,
        rt=rt,
    )
    assert actual == expected


@pytest.mark.parametrize(("rs", "rt", "expected"), [(5, 3, 0b100), (5, 5, 0b010), (3, 5, 0b100)])
def test_cmp_uses_wrapping_unsigned_difference(rs, rt, expected):
    alu = Alu()
    assert (
        alu.evaluate(
            reset=False,
            enable=True,
            core_state=isa.CORE_EXECUTE,
            arithmetic_mux=0,
            output_mux=1,
            rs=rs,
            rt=rt,
        )
        == expected
    )


def test_output_only_changes_in_execute_and_enabled_lane():
    alu = Alu()
    alu.clock(
        reset=False,
        enable=True,
        core_state=isa.CORE_EXECUTE,
        arithmetic_mux=isa.ALU_ADD,
        output_mux=0,
        rs=4,
        rt=5,
    )
    assert alu.alu_out == 9
    alu.clock(
        reset=False,
        enable=False,
        core_state=isa.CORE_EXECUTE,
        arithmetic_mux=isa.ALU_ADD,
        output_mux=0,
        rs=100,
        rt=100,
    )
    assert alu.alu_out == 9


def test_reset_clears_output():
    alu = Alu()
    alu.alu_out = 42
    alu.clock(
        reset=True,
        enable=True,
        core_state=isa.CORE_EXECUTE,
        arithmetic_mux=isa.ALU_ADD,
        output_mux=0,
        rs=1,
        rt=1,
    )
    assert alu.alu_out == 0

