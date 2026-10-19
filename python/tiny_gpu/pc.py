"""Per-lane program counter and negative-zero-positive state; mirrors ``src/pc.sv``."""

from __future__ import annotations

from dataclasses import dataclass

from . import isa


@dataclass
class PcOutputs:
    """Next program counter and negative, zero, positive (NZP) condition state."""

    nzp: int
    next_pc: int


class PcUnit:
    """Per-lane program counter and condition-code register."""

    def __init__(self) -> None:
        """Create a program counter and condition register cleared to zero."""

        self.nzp = 0
        self.next_pc = 0

    def evaluate(
        self,
        *,
        reset: bool,
        enable: bool,
        core_state: int,
        decoded_nzp: int,
        decoded_immediate: int,
        nzp_write_enable: int,
        pc_mux: int,
        alu_out: int,
        current_pc: int,
    ) -> PcOutputs:
        """Return the next program counter and condition state without committing them."""

        if reset:
            return PcOutputs(nzp=0, next_pc=0)

        nzp = self.nzp
        next_pc = self.next_pc
        if not enable:
            return PcOutputs(nzp=nzp, next_pc=next_pc)

        if core_state == isa.CORE_EXECUTE:
            if pc_mux and (nzp & decoded_nzp) != 0:
                next_pc = decoded_immediate & 0xFF
            else:
                next_pc = (current_pc + 1) & 0xFF

        if core_state == isa.CORE_UPDATE and nzp_write_enable:
            nzp = alu_out & 0b111

        return PcOutputs(nzp=nzp, next_pc=next_pc)

    def clock(self, **kwargs: int | bool) -> None:
        """Commit the evaluated program counter and condition state at a clock edge."""

        outputs = self.evaluate(**kwargs)
        self.nzp = outputs.nzp
        self.next_pc = outputs.next_pc
