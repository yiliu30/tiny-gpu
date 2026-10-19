import pytest

from tiny_gpu import isa
from tiny_gpu.alu import Alu


@pytest.mark.parametrize(
    ("mux", "first_operand_value", "second_operand_value", "expected"),
    [
        (isa.ALU_ADD, 2, 3, 5),
        (isa.ALU_SUB, 2, 3, 255),
        (isa.ALU_MUL, 20, 13, 4),
        (isa.ALU_DIV, 20, 3, 6),
    ],
)
def test_arithmetic_and_wrap(
    mux, first_operand_value, second_operand_value, expected
):
    alu = Alu()
    actual = alu.evaluate(
        reset=False,
        enable=True,
        core_state=isa.CORE_EXECUTE,
        arithmetic_mux=mux,
        output_mux=0,
        first_operand_value=first_operand_value,
        second_operand_value=second_operand_value,
    )
    assert actual == expected


@pytest.mark.parametrize(
    ("first_operand_value", "second_operand_value", "expected"),
    [
        (5, 3, 0b100),
        (5, 5, 0b010),
        (3, 5, 0b100),
        (0, 1, 0b100),
        (1, 2, 0b100),
        (0, 0, 0b010),
        (127, 128, 0b100),
        (128, 127, 0b100),
        (0, 255, 0b100),
        (255, 0, 0b100),
    ],
)
def test_cmp_uses_pinned_wrapping_unsigned_difference(
    first_operand_value, second_operand_value, expected
):
    alu = Alu()
    assert (
        alu.evaluate(
            reset=False,
            enable=True,
            core_state=isa.CORE_EXECUTE,
            arithmetic_mux=0,
            output_mux=1,
            first_operand_value=first_operand_value,
            second_operand_value=second_operand_value,
        )
        == expected
    )


def test_cmp_does_not_set_negative_for_wrapped_nonzero_difference():
    alu = Alu()
    result = alu.evaluate(
        reset=False,
        enable=True,
        core_state=isa.CORE_EXECUTE,
        arithmetic_mux=0,
        output_mux=1,
        first_operand_value=0,
        second_operand_value=1,
    )

    assert result == 0b100
    assert result & 0b001 == 0


def test_output_only_changes_in_execute_and_enabled_lane():
    alu = Alu()
    alu.clock(
        reset=False,
        enable=True,
        core_state=isa.CORE_EXECUTE,
        arithmetic_mux=isa.ALU_ADD,
        output_mux=0,
        first_operand_value=4,
        second_operand_value=5,
    )
    assert alu.alu_out == 9
    alu.clock(
        reset=False,
        enable=False,
        core_state=isa.CORE_EXECUTE,
        arithmetic_mux=isa.ALU_ADD,
        output_mux=0,
        first_operand_value=100,
        second_operand_value=100,
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
        first_operand_value=1,
        second_operand_value=1,
    )
    assert alu.alu_out == 0
