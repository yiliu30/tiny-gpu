from tiny_gpu import isa


def test_instruction_field_split():
    fields = isa.split_instruction(0b0011010000010001)
    assert fields.opcode == isa.OP_ADD
    assert fields.destination_register == 4
    assert fields.first_source_register == 1
    assert fields.second_source_register == 1
    assert fields.branch_condition_mask == 2
    assert fields.immediate == 0x11
    assert fields.name == "ADD"
    assert fields.full_name == "Add"


def test_reserved_opcode_name():
    assert isa.split_instruction(0b1010000000000000).name == "UNKNOWN"


def test_trace_schema_keeps_short_rtl_field_names():
    fields = isa.split_instruction(0b0011010000010001)
    serialized = fields.to_dict()
    assert serialized == {
        "opcode": isa.OP_ADD,
        "rd": 4,
        "rs": 1,
        "rt": 1,
        "nzp": 2,
        "immediate": 0x11,
    }
    assert isa.InstructionFields.from_dict(serialized) == fields


def test_branch_full_name_is_explicit():
    fields = isa.split_instruction(isa.OP_BRANCH_ON_CONDITION << 12)
    assert fields.name == "BRnzp"
    assert fields.full_name == "Branch if negative, zero, or positive"
