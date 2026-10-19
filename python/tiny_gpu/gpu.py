"""Top-level GPU wiring; mirrors ``src/gpu.sv``."""

from __future__ import annotations

from typing import Sequence

from .controller import Controller
from .core import Core
from .dcr import Dcr
from .dispatch import Dispatch
from .harness import SimulationHarness
from .memory import ExternalMemory, MemoryResponse
from .trace import TraceRecord


PINNED_CONFIGURATION = {
    "data_mem_addr_bits": 8,
    "data_mem_data_bits": 8,
    "data_mem_num_channels": 4,
    "program_mem_addr_bits": 8,
    "program_mem_data_bits": 16,
    "program_mem_num_channels": 1,
    "num_cores": 2,
    "threads_per_block": 4,
}


class Gpu:
    """Top-level processor wiring for the pinned two-core compatibility profile."""

    def __init__(
        self,
        *,
        data_mem_addr_bits: int = 8,
        data_mem_data_bits: int = 8,
        data_mem_num_channels: int = 4,
        program_mem_addr_bits: int = 8,
        program_mem_data_bits: int = 16,
        program_mem_num_channels: int = 1,
        num_cores: int = 2,
        threads_per_block: int = 4,
    ) -> None:
        """Create the device control register, dispatcher, controllers, memories, and cores."""

        _validate_pinned_configuration(
            {
                "data_mem_addr_bits": data_mem_addr_bits,
                "data_mem_data_bits": data_mem_data_bits,
                "data_mem_num_channels": data_mem_num_channels,
                "program_mem_addr_bits": program_mem_addr_bits,
                "program_mem_data_bits": program_mem_data_bits,
                "program_mem_num_channels": program_mem_num_channels,
                "num_cores": num_cores,
                "threads_per_block": threads_per_block,
            }
        )

        self.data_mem_addr_bits = data_mem_addr_bits
        self.data_mem_data_bits = data_mem_data_bits
        self.data_mem_num_channels = data_mem_num_channels
        self.program_mem_addr_bits = program_mem_addr_bits
        self.program_mem_data_bits = program_mem_data_bits
        self.program_mem_num_channels = program_mem_num_channels
        self.num_cores = num_cores
        self.threads_per_block = threads_per_block

        self.reset = 0
        self.start = 0
        self.device_control_write_enable = 0
        self.device_control_data = 0

        self.program_memory = ExternalMemory(
            address_bits=program_mem_addr_bits,
            data_bits=program_mem_data_bits,
            channels=program_mem_num_channels,
            read_only=True,
        )
        self.data_memory = ExternalMemory(
            address_bits=data_mem_addr_bits,
            data_bits=data_mem_data_bits,
            channels=data_mem_num_channels,
        )

        self.dcr = Dcr()
        self.dispatch = Dispatch(
            num_cores=num_cores,
            threads_per_block=threads_per_block,
        )
        self.program_controller = Controller(
            address_bits=program_mem_addr_bits,
            data_bits=program_mem_data_bits,
            num_consumers=num_cores,
            num_channels=program_mem_num_channels,
            write_enable=0,
        )
        num_lsus = num_cores * threads_per_block
        self.data_controller = Controller(
            address_bits=data_mem_addr_bits,
            data_bits=data_mem_data_bits,
            num_consumers=num_lsus,
            num_channels=data_mem_num_channels,
        )
        self.cores = [
            Core(
                threads_per_block=threads_per_block,
                core_index=index,
            )
            for index in range(num_cores)
        ]

        self.lsu_read_valid = [0] * num_lsus
        self.lsu_read_address = [0] * num_lsus
        self.lsu_write_valid = [0] * num_lsus
        self.lsu_write_address = [0] * num_lsus
        self.lsu_write_data = [0] * num_lsus

        self._program_response = _zero_response(program_mem_num_channels)
        self._data_response = _zero_response(data_mem_num_channels)
        self._pending_program_request: dict | None = None
        self._pending_data_request: dict | None = None
        self._next_pending_program_request: dict | None = None
        self._next_pending_data_request: dict | None = None
        self._staged_dcr = None
        self._staged_dispatch = None
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
        self._relay_initialized = False
        self._sync_dispatch_outputs()

    @property
    def done(self) -> int:
        """Return whether the dispatcher has marked every block complete."""

        return self.dispatch.done

    def load_program(self, program: Sequence[int]) -> None:
        """Load a machine-code instruction image into external program memory."""

        self.program_memory.load(program)

    def load_data(self, data: Sequence[int]) -> None:
        """Load input values into external data memory."""

        self.data_memory.load(data)

    def boot(self, *, thread_count: int) -> None:
        """Reset the processor, write the device control register, then assert start."""

        self.reset = 1
        self.device_control_write_enable = 0
        self.start = 0
        self.evaluate_clocked()
        self.commit()

        self.reset = 0
        self.device_control_write_enable = 1
        self.device_control_data = thread_count
        self.evaluate_clocked()
        self.commit()

        self.device_control_write_enable = 0
        self.start = 1
        # The RTL relay arrays are still X on the first captured cycle because
        # their first post-reset sample happens on the launch edge.
        self._relay_initialized = False

    def service_external_memory(self) -> None:
        """Return responses for program and data requests captured at the prior edge."""

        self._program_response = (
            _zero_response(self.program_mem_num_channels)
            if self._pending_program_request is None
            else self.program_memory.service(**self._pending_program_request)
        )
        self._data_response = (
            _zero_response(self.data_mem_num_channels)
            if self._pending_data_request is None
            else self.data_memory.service(**self._pending_data_request)
        )

    def settle(self) -> None:
        """Provide the combinational settle point; current module outputs are already explicit."""

        return None

    def observe(
        self,
        cycle: int,
        *,
        compatibility: bool = True,
        full: bool = False,
    ) -> list[TraceRecord]:
        """Capture lane records for started cores before the next clock edge."""

        records = []
        for index, core in enumerate(self.cores):
            if self.dcr.value <= index * self.threads_per_block:
                continue
            records.extend(
                core.observe(
                    cycle,
                    compatibility=compatibility,
                    full=full,
                )
            )
        if full and records:
            records[0].extra["arch_state"] = self.full_trace_state()
        return records

    def full_trace_state(self) -> dict[str, object]:
        """Return the full architectural state captured by the RTL log."""

        relay_values = (
            [
                None if not self._relay_initialized else value
                for value in self.lsu_read_valid
            ],
            [
                None if not self._relay_initialized else value
                for value in self.lsu_read_address
            ],
            [
                None if not self._relay_initialized else value
                for value in self.lsu_write_valid
            ],
            [
                None if not self._relay_initialized else value
                for value in self.lsu_write_address
            ],
            [
                None if not self._relay_initialized else value
                for value in self.lsu_write_data
            ],
        )
        (
            relay_read_valid,
            relay_read_address,
            relay_write_valid,
            relay_write_address,
            relay_write_data,
        ) = relay_values

        return {
            "data_controller": {
                "current_consumer": list(self.data_controller.current_consumer),
                "serving": self.data_controller.serving,
                "state": list(self.data_controller.state),
            },
            "data_memory": {
                "read_address": list(self.data_controller.mem_read_address),
                "read_data": list(self._data_response.read_data),
                "read_ready": list(self._data_response.read_ready),
                "read_valid": list(self.data_controller.mem_read_valid),
                "write_address": list(self.data_controller.mem_write_address),
                "write_data": list(self.data_controller.mem_write_data),
                "write_ready": list(self._data_response.write_ready),
                "write_valid": list(self.data_controller.mem_write_valid),
            },
            "dcr": {"thread_count": self.dcr.value},
            "dispatch": {
                "blocks_dispatched": self.dispatch.blocks_dispatched,
                "blocks_done": self.dispatch.blocks_done,
                "core_block_id": list(self.dispatch.core_block_id),
                "core_reset": list(self.dispatch.core_reset),
                "core_start": list(self.dispatch.core_start),
                "core_thread_count": list(self.dispatch.core_thread_count),
                "done": self.dispatch.done,
                "start_execution": self.dispatch.start_execution,
            },
            "done": self.done,
            "fetchers": {
                "read_address": [core.program_mem_read_address for core in self.cores],
                "read_data": list(self.program_controller.consumer_read_data),
                "read_ready": list(self.program_controller.consumer_read_ready),
                "read_valid": [core.program_mem_read_valid for core in self.cores],
            },
            "lsu_relay": {
                "read_address": relay_read_address,
                "read_data": list(self.data_controller.consumer_read_data),
                "read_ready": list(self.data_controller.consumer_read_ready),
                "read_valid": relay_read_valid,
                "write_address": relay_write_address,
                "write_data": relay_write_data,
                "write_ready": list(self.data_controller.consumer_write_ready),
                "write_valid": relay_write_valid,
            },
            "program_controller": {
                "current_consumer": list(self.program_controller.current_consumer),
                "serving": self.program_controller.serving,
                "state": list(self.program_controller.state),
            },
            "program_memory": {
                "read_address": list(self.program_controller.mem_read_address),
                "read_data": list(self._program_response.read_data),
                "read_ready": list(self._program_response.read_ready),
                "read_valid": list(self.program_controller.mem_read_valid),
            },
        }

    def evaluate_clocked(self) -> None:
        """Evaluate every clocked module while all modules still see old state."""

        for core in self.cores:
            core.evaluate_clocked()

        self._staged_dcr = self.dcr.evaluate(
            reset=bool(self.reset),
            write_enable=self.device_control_write_enable,
            data=self.device_control_data,
        )
        self._staged_dispatch = self.dispatch.evaluate(
            reset=bool(self.reset),
            start=self.start,
            thread_count=self.dcr.value,
            core_done=[core.done for core in self.cores],
        )
        self._staged_program_controller = self.program_controller.evaluate(
            reset=bool(self.reset),
            consumer_read_valid=[core.program_mem_read_valid for core in self.cores],
            consumer_read_address=[core.program_mem_read_address for core in self.cores],
            consumer_write_valid=[0] * self.num_cores,
            consumer_write_address=[0] * self.num_cores,
            consumer_write_data=[0] * self.num_cores,
            mem_read_ready=self._program_response.read_ready,
            mem_read_data=self._program_response.read_data,
        )
        self._staged_data_controller = self.data_controller.evaluate(
            reset=bool(self.reset),
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

        self._staged_core_read_ready = []
        self._staged_core_read_data = []
        self._staged_core_write_ready = []
        for core_index in range(self.num_cores):
            start = core_index * self.threads_per_block
            stop = start + self.threads_per_block
            self._staged_core_read_ready.append(
                list(self.data_controller.consumer_read_ready[start:stop])
            )
            self._staged_core_read_data.append(
                list(self.data_controller.consumer_read_data[start:stop])
            )
            self._staged_core_write_ready.append(
                list(self.data_controller.consumer_write_ready[start:stop])
            )

    def commit(self) -> None:
        """Publish all staged processor updates together at the simulated clock edge."""

        for core in self.cores:
            core.commit()
        self.dcr.value = self._staged_dcr
        self.dispatch.commit(self._staged_dispatch)
        self.program_controller.commit(self._staged_program_controller)
        self.data_controller.commit(self._staged_data_controller)
        self._relay_initialized = True
        self._pending_program_request = self._next_pending_program_request
        self._pending_data_request = self._next_pending_data_request

        self.lsu_read_valid = self._staged_lsu_read_valid
        self.lsu_read_address = self._staged_lsu_read_address
        self.lsu_write_valid = self._staged_lsu_write_valid
        self.lsu_write_address = self._staged_lsu_write_address
        self.lsu_write_data = self._staged_lsu_write_data

        self._sync_dispatch_outputs()
        for index, core in enumerate(self.cores):
            core.program_mem_read_ready = self.program_controller.consumer_read_ready[index]
            core.program_mem_read_data = self.program_controller.consumer_read_data[index]
            core.data_mem_read_ready = list(self._staged_core_read_ready[index])
            core.data_mem_read_data = list(self._staged_core_read_data[index])
            core.data_mem_write_ready = list(self._staged_core_write_ready[index])

    def run_until_testbench_done(
        self,
        *,
        max_cycles: int = 100_000,
        compatibility: bool = True,
        full: bool = False,
    ) -> tuple[list[TraceRecord], int]:
        """Run through the shared harness and return flattened records plus cycle count."""

        simulation = SimulationHarness(
            self,
            observe=lambda cycle: self.observe(
                cycle,
                compatibility=compatibility,
                full=full,
            ),
        )
        snapshots = simulation.run_until_done(max_cycles=max_cycles)
        records = [record for snapshot in snapshots for record in snapshot]
        return records, simulation.cycle

    def _sync_dispatch_outputs(self) -> None:
        """Copy dispatcher launch controls onto the compute cores."""

        for index, core in enumerate(self.cores):
            core.start = self.dispatch.core_start[index]
            core.reset = self.dispatch.core_reset[index]
            core.block_id = self.dispatch.core_block_id[index]
            core.thread_count = self.dispatch.core_thread_count[index]


def _zero_response(channels: int) -> MemoryResponse:
    """Return an all-inactive response for every external-memory channel."""

    return MemoryResponse((0,) * channels, (0,) * channels, (0,) * channels)


def _validate_pinned_configuration(configuration: dict[str, int]) -> None:
    """Reject configuration values that the pinned datapath does not model."""

    mismatches = [
        f"{name}={value} (pinned value is {PINNED_CONFIGURATION[name]})"
        for name, value in configuration.items()
        if value != PINNED_CONFIGURATION[name]
    ]
    if mismatches:
        raise ValueError("unsupported Gpu configuration: " + "; ".join(mismatches))
