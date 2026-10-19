import json

import pytest

from tiny_gpu.isa import InstructionFields, split_instruction
from tiny_gpu.trace import (
    TraceComparisonError,
    TraceRecord,
    compare_traces,
    read_jsonl,
    write_jsonl,
)


def record(cycle=0, core=0, lane=0, pc=0, registers=None):
    bits = 0
    return TraceRecord(
        cycle=cycle,
        core=core,
        lane=lane,
        thread_id=lane,
        core_state="FETCH",
        fetcher_state="FETCHED",
        pc=pc,
        instruction_bits=bits,
        decoded=split_instruction(bits),
        done=0,
        lsu_state="IDLE",
        registers=registers or {"R0": 0},
        rs=0,
        rt=0,
        alu_out=0,
    )


def test_jsonl_round_trip_is_deterministic(tmp_path):
    path = tmp_path / "trace.jsonl"
    original = [record(), record(cycle=1, lane=1, pc=1)]
    write_jsonl(path, original)
    loaded = read_jsonl(path)
    assert loaded == original
    first_text = path.read_text()
    write_jsonl(path, loaded)
    assert path.read_text() == first_text
    assert json.loads(first_text.splitlines()[0])["instruction"] == "NOP"


def test_comparator_reports_first_missing_cycle():
    expected = [record(cycle=0), record(cycle=1)]
    actual = [record(cycle=0)]
    with pytest.raises(TraceComparisonError) as error:
        compare_traces(expected, actual)
    assert error.value.divergence.kind == "missing"
    assert error.value.divergence.cycle == 1


def test_comparator_reports_first_unexpected_lane():
    expected = [record(lane=0)]
    actual = [record(lane=0), record(lane=1)]
    with pytest.raises(TraceComparisonError) as error:
        compare_traces(expected, actual)
    assert error.value.divergence.kind == "unexpected"
    assert error.value.divergence.lane == 1


def test_comparator_reports_first_field_with_expected_and_actual():
    expected = [record(pc=3, registers={"R0": 1, "R1": 2})]
    actual = [record(pc=4, registers={"R0": 1, "R1": 99})]
    with pytest.raises(TraceComparisonError) as error:
        compare_traces(expected, actual)
    divergence = error.value.divergence
    assert divergence.kind == "field"
    assert (divergence.cycle, divergence.core, divergence.lane) == (0, 0, 0)
    assert divergence.field == "pc"
    assert (divergence.expected, divergence.actual) == (3, 4)


def test_strict_comparison_rejects_unexpected_actual_field():
    expected = [record()]
    actual = [record()]
    actual[0].extra["unexpected"] = 1

    compare_traces(expected, actual)

    with pytest.raises(TraceComparisonError) as error:
        compare_traces(expected, actual, strict_fields=True)
    divergence = error.value.divergence
    assert divergence.kind == "field"
    assert divergence.field == "unexpected"
    assert (divergence.expected, divergence.actual) == ("<missing>", 1)

