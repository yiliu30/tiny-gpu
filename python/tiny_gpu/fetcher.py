"""Instruction fetcher; mirrors ``src/fetcher.sv``."""

from __future__ import annotations

from dataclasses import dataclass

from . import isa


@dataclass
class FetcherOutputs:
    """Next fetcher state, program-memory request, and fetched instruction."""

    state: int
    mem_read_valid: int
    mem_read_address: int
    instruction: int


class Fetcher:
    """Request one instruction and hold it until the core enters decode."""

    def __init__(self) -> None:
        """Create a fetcher waiting for the core to enter its fetch state."""

        self.state = isa.FETCHER_IDLE
        self.mem_read_valid = 0
        self.mem_read_address = 0
        self.instruction = 0

    def evaluate(
        self,
        *,
        reset: bool,
        core_state: int,
        current_pc: int,
        mem_read_ready: int,
        mem_read_data: int,
    ) -> FetcherOutputs:
        """Return the next fetch state and program-memory request without committing it."""

        if reset:
            return FetcherOutputs(isa.FETCHER_IDLE, 0, 0, 0)

        state = self.state
        mem_read_valid = self.mem_read_valid
        mem_read_address = self.mem_read_address
        instruction = self.instruction

        if state == isa.FETCHER_IDLE:
            if core_state == isa.CORE_FETCH:
                state = isa.FETCHER_FETCHING
                mem_read_valid = 1
                mem_read_address = current_pc & 0xFF
        elif state == isa.FETCHER_FETCHING:
            if mem_read_ready:
                state = isa.FETCHER_FETCHED
                instruction = mem_read_data & 0xFFFF
                mem_read_valid = 0
        elif state == isa.FETCHER_FETCHED:
            if core_state == isa.CORE_DECODE:
                state = isa.FETCHER_IDLE

        return FetcherOutputs(
            state=state,
            mem_read_valid=mem_read_valid,
            mem_read_address=mem_read_address,
            instruction=instruction,
        )

    def clock(self, **kwargs: int | bool) -> None:
        """Commit the evaluated fetch state and program-memory request at a clock edge."""

        outputs = self.evaluate(**kwargs)
        self.state = outputs.state
        self.mem_read_valid = outputs.mem_read_valid
        self.mem_read_address = outputs.mem_read_address
        self.instruction = outputs.instruction

