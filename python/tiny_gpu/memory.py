"""Testbench-equivalent external memory for the Python model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from . import isa


@dataclass(frozen=True)
class MemoryResponse:
    """Readiness and data returned by each external-memory channel."""

    read_ready: tuple[int, ...]
    read_data: tuple[int, ...]
    write_ready: tuple[int, ...]


class ExternalMemory:
    """Stand-in for the hardware testbench's external program and data memory."""

    def __init__(
        self,
        *,
        address_bits: int = 8,
        data_bits: int = 8,
        channels: int = 1,
        read_only: bool = False,
    ) -> None:
        """Create zeroed external memory with configurable address and data widths."""

        self.address_bits = address_bits
        self.data_bits = data_bits
        self.channels = channels
        self.read_only = read_only
        self.memory = [0] * (1 << address_bits)

    def load(self, values: Sequence[int]) -> None:
        """Replace the start of memory with an image, truncating values to data width."""

        if len(values) > len(self.memory):
            raise ValueError("program or data image exceeds memory size")
        self.memory[: len(values)] = [isa.truncate(value, self.data_bits) for value in values]

    def write(self, address: int, value: int) -> None:
        """Write one value directly, applying address wrapping and data truncation."""

        self.memory[address & ((1 << self.address_bits) - 1)] = isa.truncate(
            value,
            self.data_bits,
        )

    def service(
        self,
        *,
        read_valid: Sequence[int],
        read_address: Sequence[int],
        write_valid: Sequence[int] = (),
        write_address: Sequence[int] = (),
        write_data: Sequence[int] = (),
    ) -> MemoryResponse:
        """Serve reads before writes and return each channel's response."""

        read_ready = [0] * self.channels
        read_data = [0] * self.channels
        write_ready = [0] * self.channels

        for channel in range(self.channels):
            if read_valid[channel]:
                address = read_address[channel] & ((1 << self.address_bits) - 1)
                read_ready[channel] = 1
                read_data[channel] = self.memory[address]

        if not self.read_only:
            for channel in range(self.channels):
                if _optional(write_valid, channel) and _optional(write_address, channel) is not None:
                    address = write_address[channel] & ((1 << self.address_bits) - 1)
                    data = _optional(write_data, channel) or 0
                    self.memory[address] = isa.truncate(data, self.data_bits)
                    write_ready[channel] = 1

        return MemoryResponse(
            read_ready=tuple(read_ready),
            read_data=tuple(read_data),
            write_ready=tuple(write_ready),
        )


def _optional(values: Sequence[int], index: int) -> int | None:
    """Return an optional per-channel value, or ``None`` when it is absent."""

    return values[index] if index < len(values) else None
