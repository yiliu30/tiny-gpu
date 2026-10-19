#!/usr/bin/env python3
"""Convert a tiny-gpu textual cycle trace into a VCD waveform."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


CORE_STATES = ("IDLE", "FETCH", "DECODE", "REQUEST", "WAIT", "EXECUTE", "UPDATE", "DONE")
FETCHER_STATES = ("IDLE", "FETCHING", "FETCHED")
LSU_STATES = ("IDLE", "REQUESTING", "WAITING", "DONE")
INSTRUCTIONS = ("NOP", "BRnzp", "CMP", "ADD", "SUB", "MUL", "DIV", "LDR", "STR", "CONST", "RET")
REGISTERS = tuple(f"R{i}" for i in range(13)) + ("%blockIdx", "%blockDim", "%threadIdx")

CYCLE_RE = re.compile(r"^=+ Cycle (\d+) =+$")
CORE_RE = re.compile(r"^\+-+ Core (\d+) -+\+$")
THREAD_RE = re.compile(r"^\+-+ Thread (\d+) -+\+$")


@dataclass
class ThreadSnapshot:
    """Values logged for one thread during one simulated cycle."""

    log_thread: int
    lane: Optional[int] = None
    lsu_state: Optional[str] = None
    registers: dict[str, int] = field(default_factory=dict)
    rs: Optional[int] = None
    rt: Optional[int] = None
    alu_out: Optional[int] = None
    lsu_out: Optional[int] = None
    constant: Optional[int] = None


@dataclass
class CoreSnapshot:
    """Values logged for one compute core during one simulated cycle."""

    index: int
    state: Optional[str] = None
    fetcher_state: Optional[str] = None
    instruction: Optional[str] = None
    instruction_bits: Optional[int] = None
    instruction_text: Optional[str] = None
    pc: Optional[int] = None
    done: Optional[int] = None
    threads: list[ThreadSnapshot] = field(default_factory=list)


@dataclass
class CycleSnapshot:
    """All core and thread values captured at one simulated cycle."""

    index: int
    cores: dict[int, CoreSnapshot] = field(default_factory=dict)


@dataclass
class Signal:
    """One waveform signal and its most recently emitted value."""

    identifier: str
    width: int
    value: Optional[int] = None
    last_value: str = ""

    def encode(self, value: object) -> str:
        """Encode a value in the binary form expected by a Value Change Dump file."""

        if value is None:
            return "x" if self.width == 1 else "bx"
        number = int(value)
        if self.width == 1:
            return str(number)
        return f"b{number:0{self.width}b}"


def parse_log(path: Path) -> list[CycleSnapshot]:
    """Parse the human-readable tiny-gpu cycle log into structured snapshots."""

    cycles: list[CycleSnapshot] = []
    cycle: Optional[CycleSnapshot] = None
    core: Optional[CoreSnapshot] = None
    thread: Optional[ThreadSnapshot] = None

    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()

        match = CYCLE_RE.match(line)
        if match:
            cycle = CycleSnapshot(index=int(match.group(1)))
            cycles.append(cycle)
            core = None
            thread = None
            continue

        if cycle is None:
            continue

        match = CORE_RE.match(line)
        if match:
            core = CoreSnapshot(index=int(match.group(1)))
            cycle.cores[core.index] = core
            thread = None
            continue

        match = THREAD_RE.match(line)
        if match:
            if core is None:
                raise ValueError(f"{path}:{line_number}: thread outside a core")
            thread = ThreadSnapshot(log_thread=int(match.group(1)))
            core.threads.append(thread)
            continue

        if core is None:
            continue

        if line.startswith("PC: "):
            core.pc = int(line.removeprefix("PC: "))
        elif line.startswith("Instruction: "):
            core.instruction_text = line.removeprefix("Instruction: ")
            core.instruction = core.instruction_text.split()[0]
        elif line.startswith("Instruction Bits: "):
            core.instruction_bits = int(line.removeprefix("Instruction Bits: "), 2)
        elif line.startswith("Core State: "):
            core.state = line.removeprefix("Core State: ")
        elif line.startswith("Fetcher State: "):
            core.fetcher_state = line.removeprefix("Fetcher State: ")
        elif line.startswith("Core Done: "):
            core.done = int(line.removeprefix("Core Done: "))
            thread = None
        elif thread is not None and line.startswith("LSU State: "):
            thread.lsu_state = line.removeprefix("LSU State: ")
        elif thread is not None and line.startswith("Registers: "):
            for item in line.removeprefix("Registers: ").split(", "):
                name, separator, value = item.partition(" = ")
                if not separator:
                    raise ValueError(f"{path}:{line_number}: malformed register entry {item!r}")
                thread.registers[name] = int(value)
            thread.lane = thread.registers.get("%threadIdx", thread.log_thread)
        elif thread is not None and line.startswith("RS = "):
            rs, rt = line.removeprefix("RS = ").split(", RT = ")
            thread.rs = int(rs)
            thread.rt = int(rt)
        elif thread is not None and line.startswith("ALU Out: "):
            thread.alu_out = int(line.removeprefix("ALU Out: "))
        elif thread is not None and line.startswith("LSU Out: "):
            thread.lsu_out = int(line.removeprefix("LSU Out: "))
        elif thread is not None and line.startswith("Constant: "):
            thread.constant = int(line.removeprefix("Constant: "))

    if not cycles:
        raise ValueError(f"{path}: no cycle records found")

    for expected, snapshot in enumerate(cycles):
        if snapshot.index != expected:
            raise ValueError(f"{path}: expected cycle {expected}, found {snapshot.index}")
        for current_core in snapshot.cores.values():
            if current_core.state not in CORE_STATES:
                raise ValueError(f"{path}: cycle {snapshot.index} has unknown core state {current_core.state!r}")
            if current_core.fetcher_state not in FETCHER_STATES:
                raise ValueError(f"{path}: cycle {snapshot.index} has unknown fetcher state {current_core.fetcher_state!r}")
            for current_thread in current_core.threads:
                if current_thread.lsu_state not in LSU_STATES:
                    raise ValueError(f"{path}: cycle {snapshot.index} has unknown LSU state {current_thread.lsu_state!r}")

    return cycles


class VcdWriter:
    """Write parsed cycle snapshots as a Value Change Dump waveform file."""

    def __init__(self, cycles: list[CycleSnapshot]) -> None:
        """Create a writer and discover the cores, lanes, and instructions to emit."""

        self.cycles = cycles
        self.scopes: dict[tuple[str, ...], list[tuple[str, Signal]]] = {}
        self.signals: dict[str, Signal] = {}
        self.counter = 0
        self.instructions = set(INSTRUCTIONS)
        self.core_ids = sorted({core for cycle in cycles for core in cycle.cores})
        self.lane_ids: dict[int, list[int]] = {core: [] for core in self.core_ids}

        for cycle in cycles:
            for core_id, core in cycle.cores.items():
                for thread in core.threads:
                    if thread.lane is not None and thread.lane not in self.lane_ids[core_id]:
                        self.lane_ids[core_id].append(thread.lane)
                if core.instruction:
                    self.instructions.add(core.instruction)
        for lanes in self.lane_ids.values():
            lanes.sort()

        self._build_signals()

    def _add(self, scope: tuple[str, ...], name: str, width: int) -> Signal:
        identifier = f"s{self.counter}"
        self.counter += 1
        signal = Signal(identifier=identifier, width=width)
        self.scopes.setdefault(scope, []).append((name, signal))
        self.signals[f"{'.'.join(scope)}.{name}"] = signal
        return signal

    def _build_signals(self) -> None:
        for core_id in self.core_ids:
            core_scope = (f"core{core_id}",)
            for state in CORE_STATES:
                self._add(core_scope, f"state_{state}", 1)
            for state in FETCHER_STATES:
                self._add(core_scope, f"fetcher_{state}", 1)
            for instruction in sorted(self.instructions):
                self._add(core_scope, f"instr_{instruction}", 1)
            self._add(core_scope, "pc", 8)
            self._add(core_scope, "done", 1)

            for lane in self.lane_ids[core_id]:
                lane_scope = (f"core{core_id}", f"lane{lane}")
                for state in LSU_STATES:
                    self._add(lane_scope, f"lsu_{state}", 1)
                for register in REGISTERS:
                    width = 8
                    self._add(lane_scope, register.lstrip("%"), width)
                for name in ("rs", "rt", "alu_out"):
                    self._add(lane_scope, name, 8)

    def _signal(self, *path: str) -> Signal:
        return self.signals[".".join(path)]

    def _write_scope(self, output: list[str], scope: tuple[str, ...], indent: str) -> None:
        output.append(f"{indent}$scope module {scope[-1]} $end")
        for name, signal in self.scopes[scope]:
            output.append(f"{indent}  $var wire {signal.width} {signal.identifier} {name} $end")
        children = sorted({child for child in self.scopes if len(child) == len(scope) + 1 and child[:-1] == scope})
        for child in children:
            self._write_scope(output, child, indent + "  ")
        output.append(f"{indent}$upscope $end")

    def _set_one_hot(self, scope: tuple[str, ...], prefix: str, states: tuple[str, ...], active: Optional[str]) -> None:
        for state in states:
            self._signal(*scope, f"{prefix}_{state}").value = int(state == active)

    def _apply_cycle(self, cycle: CycleSnapshot) -> None:
        for signal in self.signals.values():
            signal.value = None

        for core_id, core in cycle.cores.items():
            core_scope = (f"core{core_id}",)
            self._set_one_hot(core_scope, "state", CORE_STATES, core.state)
            self._set_one_hot(core_scope, "fetcher", FETCHER_STATES, core.fetcher_state)
            for instruction in self.instructions:
                self._signal(*core_scope, f"instr_{instruction}").value = int(instruction == core.instruction)
            self._signal(*core_scope, "pc").value = core.pc
            self._signal(*core_scope, "done").value = core.done

            threads_by_lane = {thread.lane: thread for thread in core.threads if thread.lane is not None}
            for lane in self.lane_ids[core_id]:
                thread = threads_by_lane.get(lane)
                lane_scope = (f"core{core_id}", f"lane{lane}")
                if thread is None:
                    continue
                self._set_one_hot(lane_scope, "lsu", LSU_STATES, thread.lsu_state)
                for register in REGISTERS:
                    self._signal(*lane_scope, register.lstrip("%")).value = thread.registers.get(register)
                self._signal(*lane_scope, "rs").value = thread.rs
                self._signal(*lane_scope, "rt").value = thread.rt
                self._signal(*lane_scope, "alu_out").value = thread.alu_out

    def write(self, path: Path, source: Path) -> None:
        """Write the complete waveform file and record where it came from."""

        lines = [
            "$date",
            "  generated by tiny-gpu test/log_to_vcd.py",
            "$end",
            "$version",
            "  tiny-gpu trace to VCD",
            "$end",
            "$comment",
            f"  source: {source}",
            "  one time unit equals one simulated cycle",
            "$end",
            "$timescale 1 ns $end",
        ]
        lines.append("$scope module tiny_gpu $end")
        for core_id in self.core_ids:
            self._write_scope(lines, (f"core{core_id}",), "  ")
        lines.append("$upscope $end")
        lines.append("$enddefinitions $end")

        for cycle in self.cycles:
            self._apply_cycle(cycle)
            lines.append(f"#{cycle.index}")
            for scope in self.scopes:
                for name, signal in self.scopes[scope]:
                    encoded = signal.encode(signal.value)
                    if encoded != signal.last_value:
                        separator = "" if signal.width == 1 else " "
                        lines.append(f"{encoded}{separator}{signal.identifier}")
                        signal.last_value = encoded

        lines.append(f"#{self.cycles[-1].index + 1}")
        path.write_text("\n".join(lines) + "\n")


def main() -> None:
    """Convert the command-line log path into a Value Change Dump file."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="tiny-gpu cycle log to convert")
    parser.add_argument("-o", "--output", type=Path, help="output VCD path (default: beside the log)")
    args = parser.parse_args()

    cycles = parse_log(args.log)
    output = args.output or args.log.with_suffix(".vcd")
    writer = VcdWriter(cycles)
    writer.write(output, args.log)

    lanes = sum(len(lanes) for lanes in writer.lane_ids.values())
    print(f"Wrote {output}")
    print(f"  {len(cycles)} cycles, {len(writer.core_ids)} cores, {lanes} logged lanes, {len(writer.signals)} signals")


if __name__ == "__main__":
    main()
