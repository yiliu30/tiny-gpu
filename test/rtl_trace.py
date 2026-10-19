"""Normalize RTL text logs into the Python model's canonical trace schema."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

try:
    from .log_to_vcd import CycleSnapshot, parse_log
except ImportError:
    from log_to_vcd import CycleSnapshot, parse_log

from tiny_gpu import isa
from tiny_gpu.trace import TraceRecord


def _record_for_thread(cycle: CycleSnapshot, core, thread) -> TraceRecord:
    """Convert one thread snapshot into the canonical Python trace schema."""

    if core.pc is None:
        raise ValueError(f"cycle {cycle.index}, core {core.index}: missing PC")
    if core.instruction_bits is None:
        raise ValueError(
            f"cycle {cycle.index}, core {core.index}: missing raw Instruction Bits; "
            "regenerate the RTL log with test/helpers/format.py"
        )
    if core.done is None:
        raise ValueError(f"cycle {cycle.index}, core {core.index}: missing Core Done")
    if thread.lane is None:
        raise ValueError(f"cycle {cycle.index}, core {core.index}: missing %threadIdx")
    if thread.lsu_state is None or thread.rs is None or thread.rt is None:
        raise ValueError(f"cycle {cycle.index}, core {core.index}: incomplete lane trace")

    registers: dict[str, int] = {}
    for name in isa.REGISTER_NAMES:
        if name not in thread.registers:
            raise ValueError(f"cycle {cycle.index}, core {core.index}: missing register {name}")
        registers[name] = thread.registers[name]

    return TraceRecord(
        cycle=cycle.index,
        core=core.index,
        lane=thread.lane,
        thread_id=thread.log_thread,
        core_state=core.state or "",
        fetcher_state=core.fetcher_state or "",
        pc=core.pc,
        instruction_bits=core.instruction_bits,
        decoded=isa.split_instruction(core.instruction_bits),
        done=core.done,
        lsu_state=thread.lsu_state,
        registers=registers,
        rs=thread.rs,
        rt=thread.rt,
        alu_out=thread.alu_out,
        lsu_out=thread.lsu_out,
        constant=thread.constant,
    )


def records_from_log(path: Path) -> list[TraceRecord]:
    """Convert every core and thread in a Verilog text log into trace records."""

    records: list[TraceRecord] = []
    for cycle in parse_log(path):
        for core in cycle.cores.values():
            lanes = set()
            for thread in core.threads:
                record = _record_for_thread(cycle, core, thread)
                if record.lane in lanes:
                    raise ValueError(
                        f"{path}: cycle {cycle.index}, core {core.index}: duplicate lane {record.lane}"
                    )
                lanes.add(record.lane)
                records.append(record)
    if not records:
        raise ValueError(f"{path}: no lane records found")
    return records

