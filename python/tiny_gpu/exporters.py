"""Write canonical traces as Value Change Dump waveforms or Perfetto timeline JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import isa
from .trace import TraceRecord


CORE_STATES = tuple(isa.CORE_STATE_NAMES)
FETCHER_STATES = tuple(isa.FETCHER_STATE_NAMES)
LSU_STATES = tuple(isa.LSU_STATE_NAMES)
INSTRUCTIONS = tuple(isa.OPCODE_NAMES.values())
REGISTER_SIGNALS = tuple(name.lstrip("%") for name in isa.REGISTER_NAMES)


@dataclass
class _VcdSignal:
    """One waveform signal and its encoded Value Change Dump value."""

    identifier: str
    width: int
    value: int | None = None
    encoded: str = ""

    def encode(self) -> str:
        """Encode the current value using the waveform format's binary syntax."""

        if self.value is None:
            return "x" if self.width == 1 else "bx"
        value = int(self.value)
        if self.width == 1:
            return str(value & 1)
        return f"b{value:0{self.width}b}"


class CanonicalVcdWriter:
    """Convert canonical trace records into a deterministic Value Change Dump file."""

    def __init__(self, records: Sequence[TraceRecord]) -> None:
        """Discover cores, lanes, registers, and architectural fields in the trace."""

        if not records:
            raise ValueError("cannot write an empty Value Change Dump trace")
        self.records = list(records)
        self.scopes: dict[tuple[str, ...], list[tuple[str, _VcdSignal]]] = {}
        self.signals: list[_VcdSignal] = []
        self.counter = 0
        self.core_ids = sorted({record.core for record in records})
        self.lanes_by_core: dict[int, list[int]] = {
            core: sorted({record.lane for record in records if record.core == core})
            for core in self.core_ids
        }
        self.arch_values = _architecture_values(records)
        self._build_signals()

    def _add(self, scope: tuple[str, ...], name: str, width: int) -> _VcdSignal:
        signal = _VcdSignal(identifier=f"s{self.counter}", width=width)
        self.counter += 1
        self.signals.append(signal)
        self.scopes.setdefault(scope, []).append((name, signal))
        return signal

    def _build_signals(self) -> None:
        for core in self.core_ids:
            core_scope = (f"core{core}",)
            for state in CORE_STATES:
                self._add(core_scope, f"state_{state}", 1)
            for state in FETCHER_STATES:
                self._add(core_scope, f"fetcher_{state}", 1)
            for instruction in INSTRUCTIONS:
                self._add(core_scope, f"instr_{instruction}", 1)
            self._add(core_scope, "pc", 8)
            self._add(core_scope, "done", 1)

            for lane in self.lanes_by_core[core]:
                lane_scope = (f"core{core}", f"lane{lane}")
                for state in LSU_STATES:
                    self._add(lane_scope, f"lsu_{state}", 1)
                for register in REGISTER_SIGNALS:
                    self._add(lane_scope, register, 8)
                self._add(lane_scope, "thread_id", 8)
                self._add(lane_scope, "rs", 8)
                self._add(lane_scope, "rt", 8)
                self._add(lane_scope, "alu_out", 8)
                self._add(lane_scope, "lsu_out", 8)
                self._add(lane_scope, "constant", 8)
                self._add(lane_scope, "nzp", 3)

        if self.arch_values:
            for path, values in sorted(self.arch_values.items()):
                known = [value for value in values.values() if value is not None]
                width = max((max(1, value.bit_length()) for value in known), default=1)
                self._add(("architecture",), path, width)

    def _signal(self, scope: tuple[str, ...], name: str) -> _VcdSignal:
        for signal_name, signal in self.scopes[scope]:
            if signal_name == name:
                return signal
        raise KeyError(f"unknown Value Change Dump signal {'.'.join(scope)}.{name}")

    def _apply_cycle(self, cycle: int) -> None:
        for signal in self.signals:
            signal.value = None

        cycle_records = [record for record in self.records if record.cycle == cycle]
        cores: dict[int, TraceRecord] = {}
        lanes: dict[tuple[int, int], TraceRecord] = {}
        for record in cycle_records:
            cores.setdefault(record.core, record)
            lanes[(record.core, record.lane)] = record

        for core, record in cores.items():
            core_scope = (f"core{core}",)
            _set_one_hot(self.scopes, core_scope, "state", CORE_STATES, record.core_state)
            _set_one_hot(
                self.scopes,
                core_scope,
                "fetcher",
                FETCHER_STATES,
                record.fetcher_state,
            )
            for instruction in INSTRUCTIONS:
                self._signal(core_scope, f"instr_{instruction}").value = int(
                    instruction == record.decoded.name
                )
            self._signal(core_scope, "pc").value = record.pc
            self._signal(core_scope, "done").value = record.done

        for (core, lane), record in lanes.items():
            lane_scope = (f"core{core}", f"lane{lane}")
            _set_one_hot(self.scopes, lane_scope, "lsu", LSU_STATES, record.lsu_state)
            for register in isa.REGISTER_NAMES:
                self._signal(lane_scope, register.lstrip("%")).value = record.registers.get(register)
            self._signal(lane_scope, "thread_id").value = record.thread_id
            self._signal(lane_scope, "rs").value = record.rs
            self._signal(lane_scope, "rt").value = record.rt
            self._signal(lane_scope, "alu_out").value = record.alu_out
            self._signal(lane_scope, "lsu_out").value = record.lsu_out
            self._signal(lane_scope, "constant").value = record.constant
            self._signal(lane_scope, "nzp").value = record.nzp

        for path, values in self.arch_values.items():
            self._signal(("architecture",), path).value = values.get(cycle)

    def _write_scope(self, output: list[str], scope: tuple[str, ...], indent: str) -> None:
        output.append(f"{indent}$scope module {scope[-1]} $end")
        for name, signal in self.scopes[scope]:
            output.append(f"{indent}  $var wire {signal.width} {signal.identifier} {name} $end")
        children = sorted(
            child
            for child in self.scopes
            if len(child) == len(scope) + 1 and child[:-1] == scope
        )
        for child in children:
            self._write_scope(output, child, indent + "  ")
        output.append(f"{indent}$upscope $end")

    def write(self, path: Path, *, source: str = "canonical Python trace") -> None:
        """Write signal definitions and value changes to the requested path."""

        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "$date",
            "  generated deterministically by tiny-gpu-python-model",
            "$end",
            "$version",
            "  canonical trace Value Change Dump",
            "$end",
            "$comment",
            f"  source: {source}",
            "  one time unit equals one simulated cycle",
            "$end",
            "$timescale 1 ns $end",
            "$scope module tiny_gpu $end",
        ]
        for scope in sorted(self.scopes):
            if len(scope) == 1:
                self._write_scope(lines, scope, "  ")
        lines.extend(("$upscope $end", "$enddefinitions $end"))

        for cycle in sorted({record.cycle for record in self.records}):
            self._apply_cycle(cycle)
            lines.append(f"#{cycle}")
            for signal in self.signals:
                encoded = signal.encode()
                if encoded != signal.encoded:
                    separator = "" if signal.width == 1 else " "
                    lines.append(f"{encoded}{separator}{signal.identifier}")
                    signal.encoded = encoded

        lines.append(f"#{max(record.cycle for record in self.records) + 1}")
        path.write_text("\n".join(lines) + "\n")


def write_vcd(
    path: Path,
    records: Iterable[TraceRecord],
    *,
    source: str = "canonical Python trace",
) -> None:
    """Write canonical trace records as a Value Change Dump waveform file."""

    CanonicalVcdWriter(list(records)).write(path, source=source)


def build_perfetto(records: Sequence[TraceRecord], *, source: str) -> dict[str, object]:
    """Build a Perfetto timeline with one core-stage track and one track per lane."""

    if not records:
        raise ValueError("cannot write an empty Perfetto trace")

    core_ids = sorted({record.core for record in records})
    lanes_by_core = {
        core: sorted({record.lane for record in records if record.core == core})
        for core in core_ids
    }
    events: list[dict[str, object]] = [
        {
            "ph": "M",
            "name": "process_name",
            "pid": 1,
            "args": {"name": f"tiny-gpu · {source}"},
        },
        {
            "ph": "M",
            "name": "process_sort_index",
            "pid": 1,
            "args": {"sort_index": 0},
        },
    ]

    track_ids: dict[tuple[int, str], int] = {}
    track_id = 1
    for core in core_ids:
        track_ids[(core, "state")] = track_id
        events.append(_track_event(track_id, f"Core {core} · state", core * 100))
        track_id += 1
        for lane in lanes_by_core[core]:
            track_ids[(core, f"lane{lane}")] = track_id
            events.append(
                _track_event(
                    track_id,
                    f"Core {core} · Lane {lane}",
                    core * 100 + lane + 1,
                )
            )
            track_id += 1

    architecture = {
        record.cycle: record.extra["arch_state"]
        for record in records
        if "arch_state" in record.extra
    }
    cores_by_cycle: dict[tuple[int, int], TraceRecord] = {}
    lanes_by_cycle: dict[tuple[int, int, int], TraceRecord] = {}
    for record in records:
        cores_by_cycle.setdefault((record.cycle, record.core), record)
        lanes_by_cycle[(record.cycle, record.core, record.lane)] = record

    for (cycle, core), record in sorted(cores_by_cycle.items()):
        events.append(
            {
                "ph": "X",
                "name": record.core_state,
                "cat": "core stage",
                "pid": 1,
                "tid": track_ids[(core, "state")],
                "ts": cycle,
                "dur": 1,
                "args": {
                    "cycle": cycle,
                    "core": core,
                    "stage": record.core_state,
                    "fetcher": record.fetcher_state,
                    "instruction": record.decoded.name,
                    "pc": record.pc,
                    "done": record.done,
                },
            }
        )

    first_lane_by_cycle: set[int] = set()
    for (cycle, core, lane), record in sorted(lanes_by_cycle.items()):
        args: dict[str, object] = {
            "cycle": cycle,
            "core": core,
            "lane": lane,
            "thread_id": record.thread_id,
            "stage": record.core_state,
            "instruction": record.decoded.name,
            "instruction_bits": f"{record.instruction_bits:016b}",
            "pc": record.pc,
            "lsu_state": record.lsu_state,
            "rs": record.rs,
            "rt": record.rt,
            "alu_out": record.alu_out,
            "lsu_out": record.lsu_out,
            "constant": record.constant,
            "nzp": record.nzp,
        }
        args.update(record.registers)
        if cycle not in first_lane_by_cycle and cycle in architecture:
            args["arch_state"] = architecture[cycle]
            first_lane_by_cycle.add(cycle)
        events.append(
            {
                "ph": "X",
                "name": record.decoded.name,
                "cat": "lane execution",
                "pid": 1,
                "tid": track_ids[(core, f"lane{lane}")],
                "ts": cycle,
                "dur": 1,
                "args": args,
            }
        )

    return {
        "traceEvents": events,
        "displayTimeUnit": "us",
        "metadata": {
            "name": source,
            "one_cycle": "1 us",
            "format": "canonical tiny-gpu Perfetto trace",
        },
    }


def write_perfetto(
    path: Path,
    records: Iterable[TraceRecord],
    *,
    source: str = "canonical Python trace",
) -> None:
    """Write canonical trace records as a Perfetto timeline JSON file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    trace = build_perfetto(list(records), source=source)
    path.write_text(json.dumps(trace, separators=(",", ":")) + "\n")


def _track_event(track_id: int, name: str, sort_index: int) -> dict[str, object]:
    """Build the metadata event that names and orders one timeline track."""

    return {
        "ph": "M",
        "name": "thread_name",
        "pid": 1,
        "tid": track_id,
        "args": {"name": name, "sort_index": sort_index},
    }


def _set_one_hot(
    scopes: Mapping[tuple[str, ...], Sequence[tuple[str, _VcdSignal]]],
    scope: tuple[str, ...],
    prefix: str,
    states: Sequence[str],
    active: str,
) -> None:
    """Set one-hot waveform values for every state signal in a scope."""

    signals = dict(scopes[scope])
    for state in states:
        signals[f"{prefix}_{state}"].value = int(state == active)


def _architecture_values(
    records: Sequence[TraceRecord],
) -> dict[str, dict[int, int | None]]:
    """Flatten each cycle's architectural snapshot into per-signal value series."""

    flattened_by_cycle: dict[int, dict[str, int | None]] = {}
    for record in records:
        if "arch_state" not in record.extra:
            continue
        state = record.extra["arch_state"]
        if not isinstance(state, Mapping):
            raise ValueError("arch_state must be a mapping")
        flattened: dict[str, int | None] = {}
        _flatten_state(state, "", flattened)
        flattened_by_cycle[record.cycle] = flattened

    paths = sorted({path for values in flattened_by_cycle.values() for path in values})
    return {
        path: {
            cycle: values.get(path)
            for cycle, values in flattened_by_cycle.items()
        }
        for path in paths
    }


def _flatten_state(value: Any, prefix: str, output: dict[str, int | None]) -> None:
    """Flatten nested architecture dictionaries and lists into underscore-separated names."""

    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{prefix}_{key}" if prefix else str(key)
            _flatten_state(item, child, output)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _flatten_state(item, f"{prefix}_{index}", output)
    elif value is None:
        output[prefix] = None
    elif isinstance(value, int) and not isinstance(value, bool):
        output[prefix] = value
    else:
        raise ValueError(f"unsupported architecture state value at {prefix!r}: {value!r}")
