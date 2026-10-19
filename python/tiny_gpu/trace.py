"""Canonical trace records, JSONL I/O, and first-divergence comparison."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .isa import InstructionFields


@dataclass(frozen=True, order=True)
class TraceKey:
    cycle: int
    core: int
    lane: int


@dataclass
class TraceRecord:
    cycle: int
    core: int
    lane: int
    thread_id: int
    core_state: str
    fetcher_state: str
    pc: int
    instruction_bits: int
    decoded: InstructionFields
    done: int
    lsu_state: str
    registers: Mapping[str, int]
    rs: int
    rt: int
    alu_out: int | None = None
    lsu_out: int | None = None
    constant: int | None = None
    nzp: int | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> TraceKey:
        return TraceKey(self.cycle, self.core, self.lane)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "cycle": self.cycle,
            "core": self.core,
            "lane": self.lane,
            "thread_id": self.thread_id,
            "core_state": self.core_state,
            "fetcher_state": self.fetcher_state,
            "pc": self.pc,
            "instruction_bits": self.instruction_bits,
            "instruction": self.decoded.name,
            "decoded": self.decoded.to_dict(),
            "done": self.done,
            "lsu_state": self.lsu_state,
            "registers": dict(self.registers),
            "rs": self.rs,
            "rt": self.rt,
        }
        optional = {
            "alu_out": self.alu_out,
            "lsu_out": self.lsu_out,
            "constant": self.constant,
            "nzp": self.nzp,
        }
        result.update({name: value for name, value in optional.items() if value is not None})
        result.update(self.extra)
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TraceRecord":
        known = {
            "cycle",
            "core",
            "lane",
            "thread_id",
            "core_state",
            "fetcher_state",
            "pc",
            "instruction_bits",
            "instruction",
            "decoded",
            "done",
            "lsu_state",
            "registers",
            "rs",
            "rt",
            "alu_out",
            "lsu_out",
            "constant",
            "nzp",
        }
        return cls(
            cycle=int(value["cycle"]),
            core=int(value["core"]),
            lane=int(value["lane"]),
            thread_id=int(value["thread_id"]),
            core_state=str(value["core_state"]),
            fetcher_state=str(value["fetcher_state"]),
            pc=int(value["pc"]),
            instruction_bits=int(value["instruction_bits"]),
            decoded=InstructionFields(**value["decoded"]),
            done=int(value["done"]),
            lsu_state=str(value["lsu_state"]),
            registers={str(key): int(item) for key, item in value["registers"].items()},
            rs=int(value["rs"]),
            rt=int(value["rt"]),
            alu_out=int(value["alu_out"]) if "alu_out" in value else None,
            lsu_out=int(value["lsu_out"]) if "lsu_out" in value else None,
            constant=int(value["constant"]) if "constant" in value else None,
            nzp=int(value["nzp"]) if "nzp" in value else None,
            extra={key: item for key, item in value.items() if key not in known},
        )


def write_jsonl(path: Path, records: Iterable[TraceRecord]) -> None:
    lines = [
        json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":"))
        for record in records
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


def read_jsonl(path: Path) -> list[TraceRecord]:
    records: list[TraceRecord] = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(TraceRecord.from_dict(json.loads(line)))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(f"{path}:{line_number}: invalid trace record: {error}") from error
    return records


@dataclass(frozen=True)
class TraceDivergence:
    kind: str
    cycle: int
    core: int
    lane: int
    field: str | None
    expected: Any
    actual: Any


class TraceComparisonError(AssertionError):
    def __init__(self, divergence: TraceDivergence) -> None:
        self.divergence = divergence
        if divergence.kind == "field":
            detail = (
                f"{divergence.field}: expected {divergence.expected!r}, "
                f"got {divergence.actual!r}"
            )
        else:
            detail = f"expected {divergence.expected!r}, got {divergence.actual!r}"
        super().__init__(
            f"first trace divergence at cycle {divergence.cycle}, "
            f"core {divergence.core}, lane {divergence.lane} ({detail})"
        )


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key in sorted(value):
            path = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten(value[key], path))
        return result
    return {prefix: value}


def _index(records: Sequence[TraceRecord], label: str) -> dict[TraceKey, TraceRecord]:
    indexed: dict[TraceKey, TraceRecord] = {}
    for record in records:
        if record.key in indexed:
            raise ValueError(f"{label} trace contains duplicate key {record.key}")
        indexed[record.key] = record
    return indexed


def compare_traces(
    expected: Sequence[TraceRecord],
    actual: Sequence[TraceRecord],
    *,
    strict_fields: bool = False,
) -> None:
    """Raise the first missing, unexpected, or field-level divergence."""

    expected_by_key = _index(expected, "expected")
    actual_by_key = _index(actual, "actual")
    all_keys = sorted(set(expected_by_key) | set(actual_by_key))

    for key in all_keys:
        expected_record = expected_by_key.get(key)
        actual_record = actual_by_key.get(key)
        if expected_record is None:
            raise TraceComparisonError(
                TraceDivergence("unexpected", key.cycle, key.core, key.lane, None, None, actual_record)
            )
        if actual_record is None:
            raise TraceComparisonError(
                TraceDivergence("missing", key.cycle, key.core, key.lane, None, expected_record, None)
            )

        expected_fields = _flatten(expected_record.to_dict())
        actual_fields = _flatten(actual_record.to_dict())
        for name, expected_value in expected_fields.items():
            actual_value = actual_fields.get(name, "<missing>")
            if actual_value != expected_value:
                raise TraceComparisonError(
                    TraceDivergence(
                        "field",
                        key.cycle,
                        key.core,
                        key.lane,
                        name,
                        expected_value,
                        actual_value,
                    )
                )
        if strict_fields:
            unexpected_fields = sorted(set(actual_fields) - set(expected_fields))
            if unexpected_fields:
                name = unexpected_fields[0]
                raise TraceComparisonError(
                    TraceDivergence(
                        "field",
                        key.cycle,
                        key.core,
                        key.lane,
                        name,
                        "<missing>",
                        actual_fields[name],
                    )
                )

