from tiny_gpu import isa


def test_instruction_field_split():
    fields = isa.split_instruction(0b0011010000010001)
    assert fields.opcode == isa.OP_ADD
    assert fields.rd == 4
    assert fields.rs == 1
    assert fields.rt == 1
    assert fields.nzp == 2
    assert fields.immediate == 0x11
    assert fields.name == "ADD"


def test_reserved_opcode_name():
    assert isa.split_instruction(0b1010000000000000).name == "UNKNOWN"
