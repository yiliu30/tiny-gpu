"""Temporary module stubs used by the staged vertical slices."""

from __future__ import annotations

from dataclasses import dataclass

from . import isa


@dataclass
class LsuOutputs:
    """State and memory-port values produced by a load-store unit."""

    state: int
    lsu_out: int
    mem_read_valid: int
    mem_read_address: int
    mem_write_valid: int
    mem_write_address: int
    mem_write_data: int


class IdleLsu:
    """Stage-B placeholder that rejects memory instructions until Stage C."""

    def __init__(self) -> None:
        """Create an idle load-store unit with cleared memory requests."""

        self.state = isa.LSU_IDLE
        self.lsu_out = 0
        self.mem_read_valid = 0
        self.mem_read_address = 0
        self.mem_write_valid = 0
        self.mem_write_address = 0
        self.mem_write_data = 0

    def evaluate(
        self,
        *,
        reset: bool,
        enable: bool = False,
        decoded_mem_read_enable: int = 0,
        decoded_mem_write_enable: int = 0,
        **_: int | bool,
    ) -> LsuOutputs:
        """Return idle values, or reject an enabled memory instruction."""

        if reset:
            return LsuOutputs(isa.LSU_IDLE, 0, 0, 0, 0, 0, 0)
        if enable and decoded_mem_read_enable:
            raise NotImplementedError("LDR requires the Stage C load-store unit")
        if enable and decoded_mem_write_enable:
            raise NotImplementedError("STR requires the Stage C load-store unit")
        return LsuOutputs(
            state=self.state,
            lsu_out=self.lsu_out,
            mem_read_valid=self.mem_read_valid,
            mem_read_address=self.mem_read_address,
            mem_write_valid=self.mem_write_valid,
            mem_write_address=self.mem_write_address,
            mem_write_data=self.mem_write_data,
        )

    def clock(self, **kwargs: int | bool) -> None:
        """Commit the idle load-store values at a simulated clock edge."""

        outputs = self.evaluate(**kwargs)
        self.state = outputs.state
        self.lsu_out = outputs.lsu_out
        self.mem_read_valid = outputs.mem_read_valid
        self.mem_read_address = outputs.mem_read_address
        self.mem_write_valid = outputs.mem_write_valid
        self.mem_write_address = outputs.mem_write_address
        self.mem_write_data = outputs.mem_write_data
