"""Block dispatcher; mirrors ``src/dispatch.sv``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass
class DispatchOutputs:
    """Next block assignments, completion state, and per-core launch controls."""

    done: int
    core_start: list[int]
    core_reset: list[int]
    core_block_id: list[int]
    core_thread_count: list[int]
    blocks_dispatched: int
    blocks_done: int
    start_execution: int


class Dispatch:
    """Divide a kernel's threads into blocks and assign blocks to available cores."""

    def __init__(self, *, num_cores: int = 2, threads_per_block: int = 4) -> None:
        """Create dispatcher state for a fixed core count and block size."""

        self.num_cores = num_cores
        self.threads_per_block = threads_per_block
        self.done = 0
        self.blocks_dispatched = 0
        self.blocks_done = 0
        self.start_execution = 0
        self.core_start = [0] * num_cores
        self.core_reset = [1] * num_cores
        self.core_block_id = [0] * num_cores
        self.core_thread_count = [threads_per_block] * num_cores

    def evaluate(
        self,
        *,
        reset: bool,
        start: int,
        thread_count: int,
        core_done: Sequence[int],
    ) -> DispatchOutputs:
        """Return the next block assignment and completion state without committing it."""

        if reset:
            return DispatchOutputs(
                done=0,
                core_start=[0] * self.num_cores,
                core_reset=[1] * self.num_cores,
                core_block_id=[0] * self.num_cores,
                core_thread_count=[self.threads_per_block] * self.num_cores,
                blocks_dispatched=0,
                blocks_done=0,
                start_execution=0,
            )

        done = self.done
        blocks_dispatched = self.blocks_dispatched
        blocks_done = self.blocks_done
        start_execution = self.start_execution
        core_start = list(self.core_start)
        core_reset = list(self.core_reset)
        core_block_id = list(self.core_block_id)
        core_thread_count = list(self.core_thread_count)

        total_blocks = (thread_count + self.threads_per_block - 1) // self.threads_per_block
        if start:
            if not start_execution:
                start_execution = 1
                core_reset = [1] * self.num_cores

            if blocks_done == total_blocks:
                done = 1

            for index in range(self.num_cores):
                if core_reset[index]:
                    core_reset[index] = 0
                    if blocks_dispatched < total_blocks:
                        core_start[index] = 1
                        core_block_id[index] = blocks_dispatched
                        core_thread_count[index] = (
                            thread_count - blocks_dispatched * self.threads_per_block
                            if blocks_dispatched == total_blocks - 1
                            else self.threads_per_block
                        )
                        blocks_dispatched += 1

            for index in range(self.num_cores):
                if core_start[index] and _at(core_done, index):
                    core_reset[index] = 1
                    core_start[index] = 0
                    blocks_done += 1

        return DispatchOutputs(
            done=done,
            core_start=core_start,
            core_reset=core_reset,
            core_block_id=core_block_id,
            core_thread_count=core_thread_count,
            blocks_dispatched=blocks_dispatched,
            blocks_done=blocks_done,
            start_execution=start_execution,
        )

    def commit(self, outputs: DispatchOutputs) -> None:
        """Publish the evaluated dispatcher state at a simulated clock edge."""

        self.done = outputs.done
        self.blocks_dispatched = outputs.blocks_dispatched
        self.blocks_done = outputs.blocks_done
        self.start_execution = outputs.start_execution
        self.core_start = outputs.core_start
        self.core_reset = outputs.core_reset
        self.core_block_id = outputs.core_block_id
        self.core_thread_count = outputs.core_thread_count


def _at(values: Sequence[int], index: int) -> int:
    """Return an optional per-core value, using zero when the index is absent."""

    return values[index] if index < len(values) else 0

