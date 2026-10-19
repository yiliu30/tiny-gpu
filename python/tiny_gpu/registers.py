"""Per-lane register file; mirrors ``src/registers.sv``."""

from __future__ import annotations

from dataclasses import dataclass

from . import isa


@dataclass
class RegisterFileOutputs:
    """Register operands and the complete register values after evaluation."""

    first_source_value: int
    second_source_value: int
    values: tuple[int, ...]


class RegisterFile:
    """Per-lane register file plus read-only block and thread identity values."""

    def __init__(self, *, threads_per_block: int = 4, thread_id: int = 0) -> None:
        """Create a register file for one lane and seed its read-only registers."""

        self.threads_per_block = threads_per_block
        self.thread_id = thread_id
        self.first_source_value = 0
        self.second_source_value = 0
        self.values = list(self._reset_values())

    def _reset_values(self) -> tuple[int, ...]:
        """Return the register image produced by reset."""

        values = [0] * 16
        values[14] = self.threads_per_block & 0xFF
        values[15] = self.thread_id & 0xFF
        return tuple(values)

    def evaluate(
        self,
        *,
        reset: bool,
        enable: bool,
        block_id: int,
        core_state: int,
        register_write_enable: int,
        register_input_mux: int,
        destination_register_address: int,
        first_source_register_address: int,
        second_source_register_address: int,
        immediate: int,
        alu_out: int,
        lsu_out: int,
    ) -> RegisterFileOutputs:
        """Return read operands and the next register image without committing it."""

        if reset:
            return RegisterFileOutputs(
                first_source_value=0,
                second_source_value=0,
                values=self._reset_values(),
            )

        first_source_value = self.first_source_value
        second_source_value = self.second_source_value
        values = list(self.values)
        if not enable:
            return RegisterFileOutputs(
                first_source_value=first_source_value,
                second_source_value=second_source_value,
                values=tuple(values),
            )

        values[13] = block_id & 0xFF
        if core_state == isa.CORE_REQUEST:
            first_source_value = self.values[first_source_register_address]
            second_source_value = self.values[second_source_register_address]

        if (
            core_state == isa.CORE_UPDATE
            and register_write_enable
            and destination_register_address < 13
        ):
            if register_input_mux == isa.REG_ARITHMETIC:
                values[destination_register_address] = alu_out & 0xFF
            elif register_input_mux == isa.REG_MEMORY:
                values[destination_register_address] = lsu_out & 0xFF
            elif register_input_mux == isa.REG_CONSTANT:
                values[destination_register_address] = immediate & 0xFF

        return RegisterFileOutputs(
            first_source_value=first_source_value,
            second_source_value=second_source_value,
            values=tuple(values),
        )

    def clock(self, **kwargs: int | bool) -> None:
        """Commit evaluated operands and register values at a simulated clock edge."""

        outputs = self.evaluate(**kwargs)
        self.first_source_value = outputs.first_source_value
        self.second_source_value = outputs.second_source_value
        self.values = list(outputs.values)
