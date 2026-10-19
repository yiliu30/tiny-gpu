"""Device control register (DCR); mirrors ``src/dcr.sv``."""

from __future__ import annotations


class Dcr:
    """Storage for the thread count that controls how many blocks a kernel launches."""

    def __init__(self) -> None:
        """Create a device control register holding a zero thread count."""

        self.value = 0

    def evaluate(self, *, reset: bool, write_enable: int, data: int) -> int:
        """Return the next stored thread count without committing it."""

        if reset:
            return 0
        if write_enable:
            return data & 0xFF
        return self.value

    def clock(self, *, reset: bool, write_enable: int, data: int) -> None:
        """Commit the evaluated thread count at a simulated clock edge."""

        self.value = self.evaluate(reset=reset, write_enable=write_enable, data=data)

