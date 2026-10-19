"""Instruction decoder; mirrors ``src/decoder.sv``."""

from __future__ import annotations

from dataclasses import dataclass

from . import isa


@dataclass
class DecoderOutputs:
    """Control signals and instruction fields produced by the decoder."""

    destination_register_address: int = 0
    first_source_register_address: int = 0
    second_source_register_address: int = 0
    branch_condition_mask: int = 0
    immediate: int = 0
    register_write_enable: int = 0
    mem_read_enable: int = 0
    mem_write_enable: int = 0
    condition_flags_write_enable: int = 0
    register_input_mux: int = 0
    alu_arithmetic_mux: int = 0
    alu_output_mux: int = 0
    pc_mux: int = 0
    ret: int = 0

    def copy(self) -> "DecoderOutputs":
        """Return an independent copy so evaluate can stage changes safely."""

        return DecoderOutputs(**vars(self))


class Decoder:
    """Instruction decoder with the same inactive-state behavior as the Verilog."""

    def __init__(self) -> None:
        """Create a decoder with all control signals cleared."""

        self.outputs = DecoderOutputs()

    def evaluate(self, *, reset: bool, core_state: int, instruction: int) -> DecoderOutputs:
        """Return decoded controls for the current instruction without committing them."""

        if reset:
            return DecoderOutputs()

        outputs = self.outputs.copy()
        if core_state != isa.CORE_DECODE:
            return outputs

        fields = isa.split_instruction(instruction)
        outputs.destination_register_address = fields.destination_register
        outputs.first_source_register_address = fields.first_source_register
        outputs.second_source_register_address = fields.second_source_register
        outputs.immediate = fields.immediate
        outputs.branch_condition_mask = fields.branch_condition_mask

        outputs.register_write_enable = 0
        outputs.mem_read_enable = 0
        outputs.mem_write_enable = 0
        outputs.condition_flags_write_enable = 0
        outputs.register_input_mux = 0
        outputs.alu_arithmetic_mux = 0
        outputs.alu_output_mux = 0
        outputs.pc_mux = 0
        outputs.ret = 0

        if fields.opcode == isa.OP_BRANCH_ON_CONDITION:
            outputs.pc_mux = 1
        elif fields.opcode == isa.OP_CMP:
            outputs.alu_output_mux = 1
            outputs.condition_flags_write_enable = 1
        elif fields.opcode == isa.OP_ADD:
            outputs.register_write_enable = 1
            outputs.register_input_mux = isa.REG_ARITHMETIC
            outputs.alu_arithmetic_mux = isa.ALU_ADD
        elif fields.opcode == isa.OP_SUB:
            outputs.register_write_enable = 1
            outputs.register_input_mux = isa.REG_ARITHMETIC
            outputs.alu_arithmetic_mux = isa.ALU_SUB
        elif fields.opcode == isa.OP_MUL:
            outputs.register_write_enable = 1
            outputs.register_input_mux = isa.REG_ARITHMETIC
            outputs.alu_arithmetic_mux = isa.ALU_MUL
        elif fields.opcode == isa.OP_DIV:
            outputs.register_write_enable = 1
            outputs.register_input_mux = isa.REG_ARITHMETIC
            outputs.alu_arithmetic_mux = isa.ALU_DIV
        elif fields.opcode == isa.OP_LDR:
            outputs.register_write_enable = 1
            outputs.register_input_mux = isa.REG_MEMORY
            outputs.mem_read_enable = 1
        elif fields.opcode == isa.OP_STR:
            outputs.mem_write_enable = 1
        elif fields.opcode == isa.OP_CONST:
            outputs.register_write_enable = 1
            outputs.register_input_mux = isa.REG_CONSTANT
        elif fields.opcode == isa.OP_RET:
            outputs.ret = 1

        return outputs

    def clock(self, *, reset: bool, core_state: int, instruction: int) -> None:
        """Commit newly decoded controls at a simulated rising clock edge."""

        self.outputs = self.evaluate(
            reset=reset,
            core_state=core_state,
            instruction=instruction,
        )
