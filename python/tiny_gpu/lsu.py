"""Load-store unit (LSU); mirrors ``src/lsu.sv``."""

from __future__ import annotations

from dataclasses import dataclass

from . import isa


@dataclass
class LsuOutputs:
    """State and memory-port values produced by one load-store unit."""

    state: int
    lsu_out: int
    mem_read_valid: int
    mem_read_address: int
    mem_write_valid: int
    mem_write_address: int
    mem_write_data: int


class Lsu:
    """Per-lane unit that handles one data-memory load or store at a time."""

    def __init__(self) -> None:
        """Create an idle load-store unit with no active memory request."""

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
        enable: bool,
        core_state: int,
        decoded_mem_read_enable: int,
        decoded_mem_write_enable: int,
        rs: int,
        rt: int,
        mem_read_ready: int,
        mem_read_data: int,
        mem_write_ready: int,
    ) -> LsuOutputs:
        """Return the next load-store state and memory request without committing it."""

        if reset:
            return LsuOutputs(isa.LSU_IDLE, 0, 0, 0, 0, 0, 0)
        if not enable:
            return LsuOutputs(
                self.state,
                self.lsu_out,
                self.mem_read_valid,
                self.mem_read_address,
                self.mem_write_valid,
                self.mem_write_address,
                self.mem_write_data,
            )

        state = self.state
        lsu_out = self.lsu_out
        mem_read_valid = self.mem_read_valid
        mem_read_address = self.mem_read_address
        mem_write_valid = self.mem_write_valid
        mem_write_address = self.mem_write_address
        mem_write_data = self.mem_write_data

        if decoded_mem_read_enable:
            if state == isa.LSU_IDLE:
                if core_state == isa.CORE_REQUEST:
                    state = isa.LSU_REQUESTING
            elif state == isa.LSU_REQUESTING:
                mem_read_valid = 1
                mem_read_address = rs & 0xFF
                state = isa.LSU_WAITING
            elif state == isa.LSU_WAITING:
                if mem_read_ready:
                    mem_read_valid = 0
                    lsu_out = mem_read_data & 0xFF
                    state = isa.LSU_DONE
            elif state == isa.LSU_DONE:
                if core_state == isa.CORE_UPDATE:
                    state = isa.LSU_IDLE

        if decoded_mem_write_enable:
            if state == isa.LSU_IDLE:
                if core_state == isa.CORE_REQUEST:
                    state = isa.LSU_REQUESTING
            elif state == isa.LSU_REQUESTING:
                mem_write_valid = 1
                mem_write_address = rs & 0xFF
                mem_write_data = rt & 0xFF
                state = isa.LSU_WAITING
            elif state == isa.LSU_WAITING:
                if mem_write_ready:
                    mem_write_valid = 0
                    state = isa.LSU_DONE
            elif state == isa.LSU_DONE:
                if core_state == isa.CORE_UPDATE:
                    state = isa.LSU_IDLE

        return LsuOutputs(
            state=state,
            lsu_out=lsu_out,
            mem_read_valid=mem_read_valid,
            mem_read_address=mem_read_address,
            mem_write_valid=mem_write_valid,
            mem_write_address=mem_write_address,
            mem_write_data=mem_write_data,
        )

    def clock(self, **kwargs: int | bool) -> None:
        """Commit the evaluated load-store state and memory request at a clock edge."""

        outputs = self.evaluate(**kwargs)
        self.state = outputs.state
        self.lsu_out = outputs.lsu_out
        self.mem_read_valid = outputs.mem_read_valid
        self.mem_read_address = outputs.mem_read_address
        self.mem_write_valid = outputs.mem_write_valid
        self.mem_write_address = outputs.mem_write_address
        self.mem_write_data = outputs.mem_write_data

