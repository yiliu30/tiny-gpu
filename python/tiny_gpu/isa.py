"""Shared tiny-gpu instruction-set architecture constants and field helpers."""

from __future__ import annotations

from dataclasses import dataclass


INSTRUCTION_BITS = 16
DATA_BITS = 8
ADDRESS_BITS = 8
THREADS_PER_BLOCK = 4
NUM_CORES = 2

OP_NOP = 0b0000
OP_BRANCH_ON_CONDITION = 0b0001
OP_CMP = 0b0010
OP_ADD = 0b0011
OP_SUB = 0b0100
OP_MUL = 0b0101
OP_DIV = 0b0110
OP_LDR = 0b0111
OP_STR = 0b1000
OP_CONST = 0b1001
OP_RET = 0b1111

OPCODE_NAMES = {
    OP_NOP: "NOP",
    OP_BRANCH_ON_CONDITION: "BRnzp",
    OP_CMP: "CMP",
    OP_ADD: "ADD",
    OP_SUB: "SUB",
    OP_MUL: "MUL",
    OP_DIV: "DIV",
    OP_LDR: "LDR",
    OP_STR: "STR",
    OP_CONST: "CONST",
    OP_RET: "RET",
}

OPCODE_FULL_NAMES = {
    OP_NOP: "No operation",
    OP_BRANCH_ON_CONDITION: "Branch if negative, zero, or positive",
    OP_CMP: "Compare",
    OP_ADD: "Add",
    OP_SUB: "Subtract",
    OP_MUL: "Multiply",
    OP_DIV: "Divide",
    OP_LDR: "Load register",
    OP_STR: "Store register",
    OP_CONST: "Load constant",
    OP_RET: "Return",
}

ALU_ADD = 0b00
ALU_SUB = 0b01
ALU_MUL = 0b10
ALU_DIV = 0b11

REG_ARITHMETIC = 0b00
REG_MEMORY = 0b01
REG_CONSTANT = 0b10

CORE_IDLE = 0b000
CORE_FETCH = 0b001
CORE_DECODE = 0b010
CORE_REQUEST = 0b011
CORE_WAIT = 0b100
CORE_EXECUTE = 0b101
CORE_UPDATE = 0b110
CORE_DONE = 0b111

CORE_STATE_NAMES = (
    "IDLE",
    "FETCH",
    "DECODE",
    "REQUEST",
    "WAIT",
    "EXECUTE",
    "UPDATE",
    "DONE",
)

FETCHER_IDLE = 0b000
FETCHER_FETCHING = 0b001
FETCHER_FETCHED = 0b010

FETCHER_STATE_NAMES = ("IDLE", "FETCHING", "FETCHED")

LSU_IDLE = 0b00
LSU_REQUESTING = 0b01
LSU_WAITING = 0b10
LSU_DONE = 0b11

LSU_STATE_NAMES = ("IDLE", "REQUESTING", "WAITING", "DONE")

CONTROLLER_IDLE = 0b000
CONTROLLER_READ_WAITING = 0b010
CONTROLLER_WRITE_WAITING = 0b011
CONTROLLER_READ_RELAYING = 0b100
CONTROLLER_WRITE_RELAYING = 0b101

REGISTER_NAMES = tuple(f"R{i}" for i in range(13)) + (
    "%blockIdx",
    "%blockDim",
    "%threadIdx",
)

REGISTER_NUMBERS = {name: index for index, name in enumerate(REGISTER_NAMES)}


def truncate(value: int, width: int) -> int:
    """Return the low ``width`` bits of an integer."""

    return value & ((1 << width) - 1)


def format_bits(value: int, width: int) -> str:
    """Format a value as a fixed-width binary string."""

    return f"{truncate(value, width):0{width}b}"


@dataclass(frozen=True)
class InstructionFields:
    """Raw fields shared by multiple instruction formats.

    Python names are descriptive. The serialized trace keeps the short Verilog
    field names ``rd``, ``rs``, ``rt``, and ``nzp`` for fixture compatibility.
    """

    opcode: int
    destination_register: int
    first_source_register: int
    second_source_register: int
    branch_condition_mask: int
    immediate: int

    @property
    def name(self) -> str:
        """Return the assembly name for this opcode, or ``UNKNOWN``."""

        return OPCODE_NAMES.get(self.opcode, "UNKNOWN")

    @property
    def full_name(self) -> str:
        """Return a human-readable description of this instruction."""

        return OPCODE_FULL_NAMES.get(self.opcode, "Unknown instruction")

    def to_dict(self) -> dict[str, int]:
        """Return the shared instruction fields as JSON-compatible values."""

        return {
            "opcode": self.opcode,
            "rd": self.destination_register,
            "rs": self.first_source_register,
            "rt": self.second_source_register,
            "nzp": self.branch_condition_mask,
            "immediate": self.immediate,
        }

    @classmethod
    def from_dict(cls, value: dict[str, int]) -> "InstructionFields":
        """Build fields from short RTL keys or descriptive Python keys."""

        return cls(
            opcode=int(value["opcode"]),
            destination_register=int(value.get("rd", value.get("destination_register", 0))),
            first_source_register=int(
                value.get("rs", value.get("first_source_register", 0))
            ),
            second_source_register=int(
                value.get("rt", value.get("second_source_register", 0))
            ),
            branch_condition_mask=int(
                value.get("nzp", value.get("branch_condition_mask", 0))
            ),
            immediate=int(value["immediate"]),
        )


def split_instruction(instruction: int) -> InstructionFields:
    """Split raw 16-bit instruction bits into the decoder's shared fields."""

    raw = truncate(instruction, INSTRUCTION_BITS)
    return InstructionFields(
        opcode=(raw >> 12) & 0xF,
        destination_register=(raw >> 8) & 0xF,
        first_source_register=(raw >> 4) & 0xF,
        second_source_register=raw & 0xF,
        branch_condition_mask=(raw >> 9) & 0x7,
        immediate=raw & 0xFF,
    )
