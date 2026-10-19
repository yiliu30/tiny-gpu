"""Device control register; mirrors ``src/dcr.sv``."""

from __future__ import annotations


class Dcr:
    def __init__(self) -> None:
        self.value = 0

    def evaluate(self, *, reset: bool, write_enable: int, data: int) -> int:
        if reset:
            return 0
        if write_enable:
            return data & 0xFF
        return self.value

    def clock(self, *, reset: bool, write_enable: int, data: int) -> None:
        self.value = self.evaluate(reset=reset, write_enable=write_enable, data=data)

