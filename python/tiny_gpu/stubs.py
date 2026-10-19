"""Temporary module stubs used by the staged vertical slices."""

from __future__ import annotations

from dataclasses import dataclass

from . import isa


@dataclass
class LsuOutputs:
    state: int
    lsu_out: int
    mem_read_valid: int
    mem_read_address: int
    mem_write_valid: int
    mem_write_address: int
    mem_write_data: int


class IdleLsu:
    """Hold all LSU outputs idle until the Stage C memory path lands."""

    def __init__(self) -> None:
        self.state = isa.LSU_IDLE
        self.lsu_out = 0
        self.mem_read_valid = 0
        self.mem_read_address = 0
        self.mem_write_valid = 0
        self.mem_write_address = 0
        self.mem_write_data = 0

    def evaluate(self, *, reset: bool, **_: int | bool) -> LsuOutputs:
        if reset:
            return LsuOutputs(isa.LSU_IDLE, 0, 0, 0, 0, 0, 0)
        return LsuOutputs(
            state=self.state,
            lsu_out=self.lsu_out,
            mem_read_valid=self.mem_read_valid,
            mem_read_address=self.mem_read_address,
            mem_write_valid=self.mem_write_valid,
            mem_write_address=self.mem_write_address,
            mem_write_data=self.mem_write_data,
        )

    def clock(self, **kwargs: int | bool) -> None:
        outputs = self.evaluate(**kwargs)
        self.state = outputs.state
        self.lsu_out = outputs.lsu_out
        self.mem_read_valid = outputs.mem_read_valid
        self.mem_read_address = outputs.mem_read_address
        self.mem_write_valid = outputs.mem_write_valid
        self.mem_write_address = outputs.mem_write_address
        self.mem_write_data = outputs.mem_write_data

