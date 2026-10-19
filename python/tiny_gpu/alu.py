"""Arithmetic-logic unit; mirrors ``src/alu.sv``."""

from __future__ import annotations

from . import isa


class Alu:
    """The ALU's output is registered and only changes during EXECUTE."""

    def __init__(self) -> None:
        self.alu_out = 0

    def evaluate(
        self,
        *,
        reset: bool,
        enable: bool,
        core_state: int,
        arithmetic_mux: int,
        output_mux: int,
        rs: int,
        rt: int,
    ) -> int:
        if reset:
            return 0
        if not enable or core_state != isa.CORE_EXECUTE:
            return self.alu_out

        rs = isa.truncate(rs, isa.DATA_BITS)
        rt = isa.truncate(rt, isa.DATA_BITS)
        if output_mux:
            difference = (rs - rt) & 0xFF
            return ((difference > 0) << 2) | ((difference == 0) << 1) | (difference < 0)

        if arithmetic_mux == isa.ALU_ADD:
            return (rs + rt) & 0xFF
        if arithmetic_mux == isa.ALU_SUB:
            return (rs - rt) & 0xFF
        if arithmetic_mux == isa.ALU_MUL:
            return (rs * rt) & 0xFF
        if arithmetic_mux == isa.ALU_DIV:
            if rt == 0:
                raise ArithmeticError("division by zero is undefined in the RTL")
            return (rs // rt) & 0xFF
        return self.alu_out

    def clock(
        self,
        *,
        reset: bool,
        enable: bool,
        core_state: int,
        arithmetic_mux: int,
        output_mux: int,
        rs: int,
        rt: int,
    ) -> None:
        self.alu_out = self.evaluate(
            reset=reset,
            enable=enable,
            core_state=core_state,
            arithmetic_mux=arithmetic_mux,
            output_mux=output_mux,
            rs=rs,
            rt=rt,
        )

