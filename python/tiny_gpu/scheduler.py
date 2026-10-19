"""Core control-flow scheduler; mirrors ``src/scheduler.sv``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from . import isa


@dataclass
class SchedulerOutputs:
    """Next program counter, core state, and completion flag."""

    current_pc: int
    core_state: int
    done: int


class Scheduler:
    """Advance the shared core through fetch, decode, memory wait, and update."""

    def __init__(self, *, threads_per_block: int = 4) -> None:
        """Create a scheduler for a fixed number of lanes per block."""

        self.threads_per_block = threads_per_block
        self.current_pc = 0
        self.core_state = isa.CORE_IDLE
        self.done = 0

    def evaluate(
        self,
        *,
        reset: bool,
        start: int,
        decoded_mem_read_enable: int,
        decoded_mem_write_enable: int,
        decoded_ret: int,
        fetcher_state: int,
        lsu_state: Sequence[int],
        next_pc: Sequence[int],
    ) -> SchedulerOutputs:
        """Return the next core control state without publishing it."""

        del decoded_mem_read_enable, decoded_mem_write_enable
        if reset:
            return SchedulerOutputs(current_pc=0, core_state=isa.CORE_IDLE, done=0)

        current_pc = self.current_pc
        core_state = self.core_state
        done = self.done

        if core_state == isa.CORE_IDLE:
            if start:
                core_state = isa.CORE_FETCH
        elif core_state == isa.CORE_FETCH:
            if fetcher_state == isa.FETCHER_FETCHED:
                core_state = isa.CORE_DECODE
        elif core_state == isa.CORE_DECODE:
            core_state = isa.CORE_REQUEST
        elif core_state == isa.CORE_REQUEST:
            core_state = isa.CORE_WAIT
        elif core_state == isa.CORE_WAIT:
            any_lsu_waiting = any(
                state in (isa.LSU_REQUESTING, isa.LSU_WAITING)
                for state in lsu_state[: self.threads_per_block]
            )
            if not any_lsu_waiting:
                core_state = isa.CORE_EXECUTE
        elif core_state == isa.CORE_EXECUTE:
            core_state = isa.CORE_UPDATE
        elif core_state == isa.CORE_UPDATE:
            if decoded_ret:
                done = 1
                core_state = isa.CORE_DONE
            else:
                current_pc = next_pc[self.threads_per_block - 1] & 0xFF
                core_state = isa.CORE_FETCH

        return SchedulerOutputs(current_pc=current_pc, core_state=core_state, done=done)

    def clock(self, **kwargs: int | bool | Sequence[int]) -> None:
        """Commit the evaluated core control state at a simulated clock edge."""

        outputs = self.evaluate(**kwargs)
        self.current_pc = outputs.current_pc
        self.core_state = outputs.core_state
        self.done = outputs.done
