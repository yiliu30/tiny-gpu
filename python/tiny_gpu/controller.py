"""Shared memory controller; mirrors ``src/controller.sv``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from . import isa


@dataclass
class ControllerOutputs:
    """Consumer and external-memory ports plus controller arbitration state."""

    consumer_read_ready: list[int]
    consumer_read_data: list[int]
    consumer_write_ready: list[int]
    mem_read_valid: list[int]
    mem_read_address: list[int]
    mem_read_data: list[int]
    mem_write_valid: list[int]
    mem_write_address: list[int]
    mem_write_data: list[int]
    state: list[int]
    current_consumer: list[int]
    serving: int


class Controller:
    """Arbitrate several memory consumers onto one or more external channels."""

    def __init__(
        self,
        *,
        address_bits: int = 8,
        data_bits: int = 8,
        num_consumers: int = 4,
        num_channels: int = 1,
        write_enable: int = 1,
    ) -> None:
        """Create a controller with the requested consumer and channel counts."""

        self.address_bits = address_bits
        self.data_bits = data_bits
        self.num_consumers = num_consumers
        self.num_channels = num_channels
        self.write_enable = write_enable

        self.consumer_read_ready = [0] * num_consumers
        self.consumer_read_data = [0] * num_consumers
        self.consumer_write_ready = [0] * num_consumers
        self.mem_read_valid = [0] * num_channels
        self.mem_read_address = [0] * num_channels
        self.mem_read_data = [0] * num_channels
        self.mem_write_valid = [0] * num_channels
        self.mem_write_address = [0] * num_channels
        self.mem_write_data = [0] * num_channels
        self.state = [isa.CONTROLLER_IDLE] * num_channels
        self.current_consumer = [0] * num_channels
        self.serving = 0

    def evaluate(
        self,
        *,
        reset: bool,
        consumer_read_valid: Sequence[int],
        consumer_read_address: Sequence[int],
        consumer_write_valid: Sequence[int] = (),
        consumer_write_address: Sequence[int] = (),
        consumer_write_data: Sequence[int] = (),
        mem_read_ready: Sequence[int] = (),
        mem_read_data: Sequence[int] = (),
        mem_write_ready: Sequence[int] = (),
    ) -> ControllerOutputs:
        """Return the next arbitration state and memory-port values without committing them."""

        if reset:
            return ControllerOutputs(
                consumer_read_ready=[0] * self.num_consumers,
                consumer_read_data=[0] * self.num_consumers,
                consumer_write_ready=[0] * self.num_consumers,
                mem_read_valid=[0] * self.num_channels,
                mem_read_address=[0] * self.num_channels,
                mem_read_data=[0] * self.num_channels,
                mem_write_valid=[0] * self.num_channels,
                mem_write_address=[0] * self.num_channels,
                mem_write_data=[0] * self.num_channels,
                state=[isa.CONTROLLER_IDLE] * self.num_channels,
                current_consumer=[0] * self.num_channels,
                serving=0,
            )

        consumer_read_ready = list(self.consumer_read_ready)
        consumer_read_data = list(self.consumer_read_data)
        consumer_write_ready = list(self.consumer_write_ready)
        mem_read_valid = list(self.mem_read_valid)
        mem_read_address = list(self.mem_read_address)
        mem_read_data_out = list(self.mem_read_data)
        mem_write_valid = list(self.mem_write_valid)
        mem_write_address = list(self.mem_write_address)
        mem_write_data = list(self.mem_write_data)
        state = list(self.state)
        current_consumer = list(self.current_consumer)
        serving = self.serving

        for channel in range(self.num_channels):
            if state[channel] == isa.CONTROLLER_IDLE:
                for consumer in range(self.num_consumers):
                    served = bool(serving & (1 << consumer))
                    if _at(consumer_read_valid, consumer) and not served:
                        serving |= 1 << consumer
                        current_consumer[channel] = consumer
                        mem_read_valid[channel] = 1
                        mem_read_address[channel] = (
                            consumer_read_address[consumer] & ((1 << self.address_bits) - 1)
                        )
                        state[channel] = isa.CONTROLLER_READ_WAITING
                        break
                    if _at(consumer_write_valid, consumer) and not served:
                        serving |= 1 << consumer
                        current_consumer[channel] = consumer
                        mem_write_valid[channel] = 1
                        mem_write_address[channel] = (
                            _at(consumer_write_address, consumer)
                            & ((1 << self.address_bits) - 1)
                        )
                        mem_write_data[channel] = (
                            _at(consumer_write_data, consumer) & ((1 << self.data_bits) - 1)
                        )
                        state[channel] = isa.CONTROLLER_WRITE_WAITING
                        break
            elif state[channel] == isa.CONTROLLER_READ_WAITING:
                if _at(mem_read_ready, channel):
                    consumer = current_consumer[channel]
                    mem_read_valid[channel] = 0
                    consumer_read_ready[consumer] = 1
                    consumer_read_data[consumer] = _at(mem_read_data, channel) & (
                        (1 << self.data_bits) - 1
                    )
                    state[channel] = isa.CONTROLLER_READ_RELAYING
            elif state[channel] == isa.CONTROLLER_WRITE_WAITING:
                if _at(mem_write_ready, channel):
                    consumer = current_consumer[channel]
                    mem_write_valid[channel] = 0
                    consumer_write_ready[consumer] = 1
                    state[channel] = isa.CONTROLLER_WRITE_RELAYING
            elif state[channel] == isa.CONTROLLER_READ_RELAYING:
                consumer = current_consumer[channel]
                if not _at(consumer_read_valid, consumer):
                    serving &= ~(1 << consumer)
                    consumer_read_ready[consumer] = 0
                    state[channel] = isa.CONTROLLER_IDLE
            elif state[channel] == isa.CONTROLLER_WRITE_RELAYING:
                consumer = current_consumer[channel]
                if not _at(consumer_write_valid, consumer):
                    serving &= ~(1 << consumer)
                    consumer_write_ready[consumer] = 0
                    state[channel] = isa.CONTROLLER_IDLE

        return ControllerOutputs(
            consumer_read_ready=consumer_read_ready,
            consumer_read_data=consumer_read_data,
            consumer_write_ready=consumer_write_ready,
            mem_read_valid=mem_read_valid,
            mem_read_address=mem_read_address,
            mem_read_data=mem_read_data_out,
            mem_write_valid=mem_write_valid,
            mem_write_address=mem_write_address,
            mem_write_data=mem_write_data,
            state=state,
            current_consumer=current_consumer,
            serving=serving,
        )

    def commit(self, outputs: ControllerOutputs) -> None:
        """Publish the evaluated controller outputs at a simulated clock edge."""

        self.consumer_read_ready = outputs.consumer_read_ready
        self.consumer_read_data = outputs.consumer_read_data
        self.consumer_write_ready = outputs.consumer_write_ready
        self.mem_read_valid = outputs.mem_read_valid
        self.mem_read_address = outputs.mem_read_address
        self.mem_read_data = outputs.mem_read_data
        self.mem_write_valid = outputs.mem_write_valid
        self.mem_write_address = outputs.mem_write_address
        self.mem_write_data = outputs.mem_write_data
        self.state = outputs.state
        self.current_consumer = outputs.current_consumer
        self.serving = outputs.serving


def _at(values: Sequence[int], index: int) -> int:
    """Return an optional channel value, using zero when the index is absent."""

    return values[index] if index < len(values) else 0

