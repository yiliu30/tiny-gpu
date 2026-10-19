import pytest

from tiny_gpu import isa
from tiny_gpu.decoder import Decoder, DecoderOutputs


@pytest.mark.parametrize(
    ("opcode", "expected"),
    [
        (
            isa.OP_NOP,
            DecoderOutputs(
                destination_register_address=5,
                first_source_register_address=2,
                second_source_register_address=1,
                branch_condition_mask=2,
                immediate=0x21,
            ),
        ),
        (
            isa.OP_BRANCH_ON_CONDITION,
            DecoderOutputs(
                destination_register_address=5,
                first_source_register_address=2,
                second_source_register_address=1,
                branch_condition_mask=2,
                immediate=0x21,
                pc_mux=1,
            ),
        ),
        (
            isa.OP_CMP,
            DecoderOutputs(
                destination_register_address=5,
                first_source_register_address=2,
                second_source_register_address=1,
                branch_condition_mask=2,
                immediate=0x21,
                alu_output_mux=1,
                condition_flags_write_enable=1,
            ),
        ),
        (
            isa.OP_ADD,
            DecoderOutputs(
                destination_register_address=5,
                first_source_register_address=2,
                second_source_register_address=1,
                branch_condition_mask=2,
                immediate=0x21,
                register_write_enable=1,
                alu_arithmetic_mux=isa.ALU_ADD,
            ),
        ),
        (
            isa.OP_SUB,
            DecoderOutputs(
                destination_register_address=5,
                first_source_register_address=2,
                second_source_register_address=1,
                branch_condition_mask=2,
                immediate=0x21,
                register_write_enable=1,
                alu_arithmetic_mux=isa.ALU_SUB,
            ),
        ),
        (
            isa.OP_MUL,
            DecoderOutputs(
                destination_register_address=5,
                first_source_register_address=2,
                second_source_register_address=1,
                branch_condition_mask=2,
                immediate=0x21,
                register_write_enable=1,
                alu_arithmetic_mux=isa.ALU_MUL,
            ),
        ),
        (
            isa.OP_DIV,
            DecoderOutputs(
                destination_register_address=5,
                first_source_register_address=2,
                second_source_register_address=1,
                branch_condition_mask=2,
                immediate=0x21,
                register_write_enable=1,
                alu_arithmetic_mux=isa.ALU_DIV,
            ),
        ),
        (
            isa.OP_LDR,
            DecoderOutputs(
                destination_register_address=5,
                first_source_register_address=2,
                second_source_register_address=1,
                branch_condition_mask=2,
                immediate=0x21,
                register_write_enable=1,
                register_input_mux=isa.REG_MEMORY,
                mem_read_enable=1,
            ),
        ),
        (
            isa.OP_STR,
            DecoderOutputs(
                destination_register_address=5,
                first_source_register_address=2,
                second_source_register_address=1,
                branch_condition_mask=2,
                immediate=0x21,
                mem_write_enable=1,
            ),
        ),
        (
            isa.OP_CONST,
            DecoderOutputs(
                destination_register_address=5,
                first_source_register_address=2,
                second_source_register_address=1,
                branch_condition_mask=2,
                immediate=0x21,
                register_write_enable=1,
                register_input_mux=isa.REG_CONSTANT,
            ),
        ),
        (
            isa.OP_RET,
            DecoderOutputs(
                destination_register_address=5,
                first_source_register_address=2,
                second_source_register_address=1,
                branch_condition_mask=2,
                immediate=0x21,
                ret=1,
            ),
        ),
    ],
)
def test_decode_all_instructions(opcode, expected):
    instruction = (opcode << 12) | (5 << 8) | (2 << 4) | 1
    decoder = Decoder()
    assert (
        decoder.evaluate(
            reset=False,
            core_state=isa.CORE_DECODE,
            instruction=instruction,
        )
        == expected
    )


def test_reserved_encoding_keeps_fields_and_clears_controls():
    decoder = Decoder()
    outputs = decoder.evaluate(
        reset=False,
        core_state=isa.CORE_DECODE,
        instruction=0b1110000000000000,
    )
    assert outputs.destination_register_address == 0
    assert outputs.register_write_enable == 0
    assert outputs.mem_read_enable == 0
    assert outputs.mem_write_enable == 0
    assert outputs.ret == 0


def test_decoder_only_updates_in_decode_and_holds_otherwise():
    decoder = Decoder()
    decoder.clock(reset=True, core_state=isa.CORE_DECODE, instruction=0)
    add = 0b0011000000001111
    decoder.clock(reset=False, core_state=isa.CORE_DECODE, instruction=add)
    decoded = decoder.outputs.copy()
    decoder.clock(reset=False, core_state=isa.CORE_REQUEST, instruction=isa.OP_RET << 12)
    assert decoder.outputs == decoded
