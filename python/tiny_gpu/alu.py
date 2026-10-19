"""Arithmetic-logic unit (ALU) model; mirrors ``src/alu.sv``."""

from __future__ import annotations

from . import isa


class Alu:
    """Arithmetic-logic unit whose output register changes only in EXECUTE."""

    def __init__(self) -> None:
        """Create an arithmetic-logic unit with a zeroed output register."""

        self.alu_out = 0

    def evaluate(
        self,
        *,
        reset: bool,
        enable: bool,
        core_state: int,
        arithmetic_mux: int,
        output_mux: int,
        first_operand_value: int,
        second_operand_value: int,
    ) -> int:
        """Return the output implied by the inputs without changing stored state.

        The comparison output reproduces the pinned RTL behavior: the first
        operand minus the second operand is wrapped to eight bits and compared
        as an unsigned value. A nonzero wrapped difference sets the positive
        bit, including when the mathematical difference is negative. The
        negative bit is therefore never set by this implementation.
        """

        if reset:
            return 0
        if not enable or core_state != isa.CORE_EXECUTE:
            return self.alu_out

        first_operand_value = isa.truncate(first_operand_value, isa.DATA_BITS)
        second_operand_value = isa.truncate(second_operand_value, isa.DATA_BITS)
        if output_mux:
            difference = (first_operand_value - second_operand_value) & 0xFF
            return ((difference > 0) << 2) | ((difference == 0) << 1) | (difference < 0)

        if arithmetic_mux == isa.ALU_ADD:
            return (first_operand_value + second_operand_value) & 0xFF
        if arithmetic_mux == isa.ALU_SUB:
            return (first_operand_value - second_operand_value) & 0xFF
        if arithmetic_mux == isa.ALU_MUL:
            return (first_operand_value * second_operand_value) & 0xFF
        if arithmetic_mux == isa.ALU_DIV:
            if second_operand_value == 0:
                raise ArithmeticError("division by zero is undefined in the Verilog design")
            return (first_operand_value // second_operand_value) & 0xFF
        return self.alu_out

    def clock(
        self,
        *,
        reset: bool,
        enable: bool,
        core_state: int,
        arithmetic_mux: int,
        output_mux: int,
        first_operand_value: int,
        second_operand_value: int,
    ) -> None:
        """Commit the evaluated output at a simulated rising clock edge."""

        self.alu_out = self.evaluate(
            reset=reset,
            enable=enable,
            core_state=core_state,
            arithmetic_mux=arithmetic_mux,
            output_mux=output_mux,
            first_operand_value=first_operand_value,
            second_operand_value=second_operand_value,
        )
