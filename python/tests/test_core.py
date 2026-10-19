from pathlib import Path

from tiny_gpu import isa
from tiny_gpu.core import Core
from tiny_gpu.kernels import MATADD_PROGRAM
from tiny_gpu.trace import compare_traces, read_jsonl


class CapturingCore(Core):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.records = []

    def observe(self, cycle: int, *, compatibility: bool = True):
        records = super().observe(cycle, compatibility=compatibility)
        self.records.extend(records)
        return records


class ProgramMemoryStub:
    def __init__(self, program, response_delay=4):
        self.program = program
        self.response_delay = response_delay
        self.active_cycles = 0

    def service(self, valid, address):
        if not valid:
            self.active_cycles = 0
            return 0, 0
        self.active_cycles += 1
        ready = int(self.active_cycles >= self.response_delay)
        return ready, self.program[address & 0xFF]


def run_core_prefix(core, program, cycles):
    memory = ProgramMemoryStub(program)
    core.reset = 1
    core.start = 1
    for cycle in range(cycles):
        ready, data = memory.service(core.program_mem_read_valid, core.program_mem_read_address)
        core.program_mem_read_ready = ready
        core.program_mem_read_data = data
        core.observe(cycle)
        core.evaluate_clocked()
        core.commit()
        if cycle == 0:
            core.reset = 0


def test_core_matches_matadd_prefix_through_first_memory_request():
    core = CapturingCore(threads_per_block=4)
    core.block_id = 0
    core.thread_count = 4
    run_core_prefix(core, MATADD_PROGRAM, cycles=76)

    fixture = Path(__file__).resolve().parents[2] / "test/fixtures/traces/02b6c2c/matadd/compatibility.jsonl"
    expected = [
        record
        for record in read_jsonl(fixture)
        if record.core == 0 and record.cycle <= 75
    ]
    compare_traces(expected, core.records)
