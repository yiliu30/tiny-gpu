"""Per-lane register file; mirrors ``src/registers.sv``."""

from __future__ import annotations

from dataclasses import dataclass

from . import isa


@dataclass
class RegisterFileOutputs:
    """Register operands and the complete register values after evaluation."""

    rs: int
    rt: int
    values: tuple[int, ...]


class RegisterFile:
    """Per-lane register file plus read-only block and thread identity values."""

    def __init__(self, *, threads_per_block: int = 4, thread_id: int = 0) -> None:
        """Create a register file for one lane and seed its read-only registers."""

        self.threads_per_block = threads_per_block
        self.thread_id = thread_id
        self.rs = 0
        self.rt = 0
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
        reg_write_enable: int,
        reg_input_mux: int,
        rd_address: int,
        rs_address: int,
        rt_address: int,
        immediate: int,
        alu_out: int,
        lsu_out: int,
    ) -> RegisterFileOutputs:
        """Return read operands and the next register image without committing it."""

        if reset:
            return RegisterFileOutputs(rs=0, rt=0, values=self._reset_values())

        rs = self.rs
        rt = self.rt
        values = list(self.values)
        if not enable:
            return RegisterFileOutputs(rs=rs, rt=rt, values=tuple(values))

        values[13] = block_id & 0xFF
        if core_state == isa.CORE_REQUEST:
            rs = self.values[rs_address]
            rt = self.values[rt_address]

        if core_state == isa.CORE_UPDATE and reg_write_enable and rd_address < 13:
            if reg_input_mux == isa.REG_ARITHMETIC:
                values[rd_address] = alu_out & 0xFF
            elif reg_input_mux == isa.REG_MEMORY:
                values[rd_address] = lsu_out & 0xFF
            elif reg_input_mux == isa.REG_CONSTANT:
                values[rd_address] = immediate & 0xFF

        return RegisterFileOutputs(rs=rs, rt=rt, values=tuple(values))

    def clock(self, **kwargs: int | bool) -> None:
        """Commit evaluated operands and register values at a simulated clock edge."""

        outputs = self.evaluate(**kwargs)
        self.rs = outputs.rs
        self.rt = outputs.rt
        self.values = list(outputs.values)
