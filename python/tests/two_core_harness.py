"""Stage-C-only two-core test scaffold; not a production model interface.

Stage D replaces this wiring with ``tiny_gpu.gpu.Gpu`` and the real dispatcher.
"""

from __future__ import annotations

from tiny_gpu.controller import Controller
from tiny_gpu.core import Core
from tiny_gpu.memory import ExternalMemory, MemoryResponse


class _TwoBlockDispatcher:
    """Stage-C-only block dispatcher used until the real dispatcher exists."""

    def __init__(self, *, thread_count=8, threads_per_block=4):
        """Create dispatcher state for a fixed number of threads and lanes."""

        self.thread_count = thread_count
        self.threads_per_block = threads_per_block
        self.total_blocks = (thread_count + threads_per_block - 1) // threads_per_block
        self.blocks_dispatched = 0
        self.blocks_done = 0
        self.start_execution = 0
        self.done = 0
        self.core_start = [0, 0]
        self.core_reset = [1, 1]
        self.core_block_id = [0, 0]
        self.core_thread_count = [threads_per_block, threads_per_block]

    def evaluate(self, *, core_done):
        """Return the next block assignment and completion state without committing it."""

        start_execution = self.start_execution
        core_start = list(self.core_start)
        core_reset = list(self.core_reset)
        core_block_id = list(self.core_block_id)
        core_thread_count = list(self.core_thread_count)
        done = self.done
        blocks_dispatched = self.blocks_dispatched
        blocks_done = self.blocks_done

        if not start_execution:
            start_execution = 1
            core_reset = [1, 1]

        if blocks_done == self.total_blocks:
            done = 1

        for index in range(2):
            if core_reset[index]:
                core_reset[index] = 0
                if blocks_dispatched < self.total_blocks:
                    core_start[index] = 1
                    core_block_id[index] = blocks_dispatched
                    core_thread_count[index] = (
                        self.thread_count - blocks_dispatched * self.threads_per_block
                        if blocks_dispatched == self.total_blocks - 1
                        else self.threads_per_block
                    )
                    blocks_dispatched += 1

        for index in range(2):
            if core_start[index] and core_done[index]:
                core_reset[index] = 1
                core_start[index] = 0
                blocks_done += 1

        return {
            "start_execution": start_execution,
            "done": done,
            "core_start": core_start,
            "core_reset": core_reset,
            "core_block_id": core_block_id,
            "core_thread_count": core_thread_count,
            "blocks_dispatched": blocks_dispatched,
            "blocks_done": blocks_done,
        }

    def commit(self, outputs) -> None:
        """Publish one evaluated dispatcher state."""

        self.start_execution = outputs["start_execution"]
        self.done = outputs["done"]
        self.core_start = outputs["core_start"]
        self.core_reset = outputs["core_reset"]
        self.core_block_id = outputs["core_block_id"]
        self.core_thread_count = outputs["core_thread_count"]
        self.blocks_dispatched = outputs["blocks_dispatched"]
        self.blocks_done = outputs["blocks_done"]


class TwoCoreHarness:
    """Stage-C-only processor wiring for the matrix-addition compatibility test."""

    def __init__(self, *, program, data, thread_count=8):
        """Build two cores, two controllers, external memories, and a temporary dispatcher."""

        self.cores = [Core(threads_per_block=4, core_index=index) for index in range(2)]
        self.dispatcher = _TwoBlockDispatcher(thread_count=thread_count)
        self._sync_dispatch_outputs()

        self.program_memory = ExternalMemory(
            address_bits=8,
            data_bits=16,
            channels=1,
            read_only=True,
        )
        self.data_memory = ExternalMemory(address_bits=8, data_bits=8, channels=4)
        self.program_memory.load(program)
        self.data_memory.load(data)

        self.program_controller = Controller(
            address_bits=8,
            data_bits=16,
            num_consumers=2,
            num_channels=1,
            write_enable=0,
        )
        self.data_controller = Controller(
            address_bits=8,
            data_bits=8,
            num_consumers=8,
            num_channels=4,
        )

        self.lsu_read_valid = [0] * 8
        self.lsu_read_address = [0] * 8
        self.lsu_write_valid = [0] * 8
        self.lsu_write_address = [0] * 8
        self.lsu_write_data = [0] * 8
        self._program_response = None
        self._data_response = None
        self._pending_program_request = None
        self._pending_data_request = None
        self._next_pending_program_request = None
        self._next_pending_data_request = None
        self._staged_program_controller = None
        self._staged_data_controller = None
        self._staged_lsu_read_valid = None
        self._staged_lsu_read_address = None
        self._staged_lsu_write_valid = None
        self._staged_lsu_write_address = None
        self._staged_lsu_write_data = None
        self._staged_core_read_ready = None
        self._staged_core_read_data = None
        self._staged_core_write_ready = None
        self._staged_dispatcher = None

    @property
    def done(self) -> bool:
        """Return whether the temporary dispatcher has completed every block."""

        return bool(self.dispatcher.done)

    def service_external_memory(self) -> None:
        """Return responses for requests captured at the preceding clock edge."""

        if self._pending_program_request is None:
            self._program_response = MemoryResponse((0,), (0,), (0,))
        else:
            self._program_response = self.program_memory.service(**self._pending_program_request)
        if self._pending_data_request is None:
            self._data_response = MemoryResponse((0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0))
        else:
            self._data_response = self.data_memory.service(**self._pending_data_request)

    def settle(self) -> None:
        """Provide the harness settle point; all modeled values are already explicit."""

        return None

    def observe(self, cycle: int):
        """Capture every core's lane records for one cycle."""

        records = []
        for core in self.cores:
            records.extend(core.observe(cycle))
        return records

    def evaluate_clocked(self) -> None:
        """Evaluate every clocked component while all components still see old state."""

        assert self._program_response is not None
        assert self._data_response is not None
        for core in self.cores:
            core.evaluate_clocked()
        self._staged_dispatcher = self.dispatcher.evaluate(
            core_done=[core.done for core in self.cores]
        )

        self._staged_program_controller = self.program_controller.evaluate(
            reset=False,
            consumer_read_valid=[core.program_mem_read_valid for core in self.cores],
            consumer_read_address=[core.program_mem_read_address for core in self.cores],
            consumer_write_valid=[0, 0],
            consumer_write_address=[0, 0],
            consumer_write_data=[0, 0],
            mem_read_ready=self._program_response.read_ready,
            mem_read_data=self._program_response.read_data,
        )
        self._staged_data_controller = self.data_controller.evaluate(
            reset=False,
            consumer_read_valid=self.lsu_read_valid,
            consumer_read_address=self.lsu_read_address,
            consumer_write_valid=self.lsu_write_valid,
            consumer_write_address=self.lsu_write_address,
            consumer_write_data=self.lsu_write_data,
            mem_read_ready=self._data_response.read_ready,
            mem_read_data=self._data_response.read_data,
            mem_write_ready=self._data_response.write_ready,
        )

        self._next_pending_program_request = {
            "read_valid": list(self.program_controller.mem_read_valid),
            "read_address": list(self.program_controller.mem_read_address),
        }
        self._next_pending_data_request = {
            "read_valid": list(self.data_controller.mem_read_valid),
            "read_address": list(self.data_controller.mem_read_address),
            "write_valid": list(self.data_controller.mem_write_valid),
            "write_address": list(self.data_controller.mem_write_address),
            "write_data": list(self.data_controller.mem_write_data),
        }

        self._staged_lsu_read_valid = []
        self._staged_lsu_read_address = []
        self._staged_lsu_write_valid = []
        self._staged_lsu_write_address = []
        self._staged_lsu_write_data = []
        for core in self.cores:
            self._staged_lsu_read_valid.extend(core.data_mem_read_valid)
            self._staged_lsu_read_address.extend(core.data_mem_read_address)
            self._staged_lsu_write_valid.extend(core.data_mem_write_valid)
            self._staged_lsu_write_address.extend(core.data_mem_write_address)
            self._staged_lsu_write_data.extend(core.data_mem_write_data)

        current_data = self.data_controller
        self._staged_core_read_ready = [
            current_data.consumer_read_ready[0:4],
            current_data.consumer_read_ready[4:8],
        ]
        self._staged_core_read_data = [
            current_data.consumer_read_data[0:4],
            current_data.consumer_read_data[4:8],
        ]
        self._staged_core_write_ready = [
            current_data.consumer_write_ready[0:4],
            current_data.consumer_write_ready[4:8],
        ]

    def commit(self) -> None:
        """Publish all staged core, controller, and dispatcher updates together."""

        for core in self.cores:
            core.commit()
        self.dispatcher.commit(self._staged_dispatcher)
        self._sync_dispatch_outputs()
        self.program_controller.commit(self._staged_program_controller)
        self.data_controller.commit(self._staged_data_controller)
        self._pending_program_request = self._next_pending_program_request
        self._pending_data_request = self._next_pending_data_request

        self.lsu_read_valid = self._staged_lsu_read_valid
        self.lsu_read_address = self._staged_lsu_read_address
        self.lsu_write_valid = self._staged_lsu_write_valid
        self.lsu_write_address = self._staged_lsu_write_address
        self.lsu_write_data = self._staged_lsu_write_data

        for index, core in enumerate(self.cores):
            core.program_mem_read_ready = self.program_controller.consumer_read_ready[index]
            core.program_mem_read_data = self.program_controller.consumer_read_data[index]
            core.data_mem_read_ready = list(self._staged_core_read_ready[index])
            core.data_mem_read_data = list(self._staged_core_read_data[index])
            core.data_mem_write_ready = list(self._staged_core_write_ready[index])

    def _sync_dispatch_outputs(self) -> None:
        """Copy dispatcher launch controls onto the two cores."""

        for index, core in enumerate(self.cores):
            core.start = self.dispatcher.core_start[index]
            core.reset = self.dispatcher.core_reset[index]
            core.block_id = self.dispatcher.core_block_id[index]
            core.thread_count = self.dispatcher.core_thread_count[index]
