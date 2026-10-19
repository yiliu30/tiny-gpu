"""Instruction decoder; mirrors ``src/decoder.sv``."""

from __future__ import annotations

from dataclasses import dataclass

from . import isa


@dataclass
class DecoderOutputs:
    rd_address: int = 0
    rs_address: int = 0
    rt_address: int = 0
    nzp: int = 0
    immediate: int = 0
    reg_write_enable: int = 0
    mem_read_enable: int = 0
    mem_write_enable: int = 0
    nzp_write_enable: int = 0
    reg_input_mux: int = 0
    alu_arithmetic_mux: int = 0
    alu_output_mux: int = 0
    pc_mux: int = 0
    ret: int = 0

    def copy(self) -> "DecoderOutputs":
        return DecoderOutputs(**vars(self))


class Decoder:
    """Registered decoder with the same inactive-state behavior as the RTL."""

    def __init__(self) -> None:
        self.outputs = DecoderOutputs()

    def evaluate(self, *, reset: bool, core_state: int, instruction: int) -> DecoderOutputs:
        if reset:
            return DecoderOutputs()

        outputs = self.outputs.copy()
        if core_state != isa.CORE_DECODE:
            return outputs

        fields = isa.split_instruction(instruction)
        outputs.rd_address = fields.rd
        outputs.rs_address = fields.rs
        outputs.rt_address = fields.rt
        outputs.immediate = fields.immediate
        outputs.nzp = fields.nzp

        outputs.reg_write_enable = 0
        outputs.mem_read_enable = 0
        outputs.mem_write_enable = 0
        outputs.nzp_write_enable = 0
        outputs.reg_input_mux = 0
        outputs.alu_arithmetic_mux = 0
        outputs.alu_output_mux = 0
        outputs.pc_mux = 0
        outputs.ret = 0

        if fields.opcode == isa.OP_BRNZP:
            outputs.pc_mux = 1
        elif fields.opcode == isa.OP_CMP:
            outputs.alu_output_mux = 1
            outputs.nzp_write_enable = 1
        elif fields.opcode == isa.OP_ADD:
            outputs.reg_write_enable = 1
            outputs.reg_input_mux = isa.REG_ARITHMETIC
            outputs.alu_arithmetic_mux = isa.ALU_ADD
        elif fields.opcode == isa.OP_SUB:
            outputs.reg_write_enable = 1
            outputs.reg_input_mux = isa.REG_ARITHMETIC
            outputs.alu_arithmetic_mux = isa.ALU_SUB
        elif fields.opcode == isa.OP_MUL:
            outputs.reg_write_enable = 1
            outputs.reg_input_mux = isa.REG_ARITHMETIC
            outputs.alu_arithmetic_mux = isa.ALU_MUL
        elif fields.opcode == isa.OP_DIV:
            outputs.reg_write_enable = 1
            outputs.reg_input_mux = isa.REG_ARITHMETIC
            outputs.alu_arithmetic_mux = isa.ALU_DIV
        elif fields.opcode == isa.OP_LDR:
            outputs.reg_write_enable = 1
            outputs.reg_input_mux = isa.REG_MEMORY
            outputs.mem_read_enable = 1
        elif fields.opcode == isa.OP_STR:
            outputs.mem_write_enable = 1
        elif fields.opcode == isa.OP_CONST:
            outputs.reg_write_enable = 1
            outputs.reg_input_mux = isa.REG_CONSTANT
        elif fields.opcode == isa.OP_RET:
            outputs.ret = 1

        return outputs

    def clock(self, *, reset: bool, core_state: int, instruction: int) -> None:
        self.outputs = self.evaluate(
            reset=reset,
            core_state=core_state,
            instruction=instruction,
        )

