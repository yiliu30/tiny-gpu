import json
import re
from pathlib import Path

import pytest

from tiny_gpu.cli import main
from tiny_gpu.exporters import build_perfetto, write_perfetto, write_vcd
from tiny_gpu.gpu import Gpu
from tiny_gpu.kernels import (
    MATADD_INPUT,
    MATADD_PROGRAM,
    MATMUL_INPUT,
    MATMUL_PROGRAM,
)
from tiny_gpu.trace import read_jsonl


def _run(program, data, threads):
    gpu = Gpu()
    gpu.load_program(program)
    gpu.load_data(data)
    gpu.boot(thread_count=threads)
    records, _ = gpu.run_until_testbench_done(full=True)
    return records


@pytest.fixture(scope="module")
def matadd_records():
    return _run(MATADD_PROGRAM, MATADD_INPUT, 8)


@pytest.fixture(scope="module")
def matmul_records():
    return _run(MATMUL_PROGRAM, MATMUL_INPUT, 4)


def test_perfetto_exposes_core_and_lane_tracks(matadd_records, matmul_records):
    matadd = build_perfetto(matadd_records, source="matadd full")
    matmul = build_perfetto(matmul_records, source="matmul full")
    matadd_tracks = [
        event for event in matadd["traceEvents"] if event.get("name") == "thread_name"
    ]
    matmul_tracks = [
        event for event in matmul["traceEvents"] if event.get("name") == "thread_name"
    ]
    assert len(matadd_tracks) == 10
    assert len(matmul_tracks) == 5
    assert matadd["displayTimeUnit"] == "us"
    assert matadd["metadata"]["one_cycle"] == "1 us"


def test_perfetto_json_round_trip(tmp_path, matadd_records):
    path = tmp_path / "matadd.perfetto.json"
    write_perfetto(path, matadd_records, source="matadd full")
    trace = json.loads(path.read_text())
    lane_events = [
        event
        for event in trace["traceEvents"]
        if event.get("cat") == "lane execution"
    ]
    assert len(lane_events) == len(matadd_records)
    assert "arch_state" in lane_events[0]["args"]


def test_vcd_is_structurally_valid_and_contains_full_lane_signals(tmp_path, matadd_records):
    path = tmp_path / "matadd.vcd"
    write_vcd(path, matadd_records, source="matadd full")
    text = path.read_text()

    declarations = re.findall(r"\$var wire (\d+) (\S+) (\S+) \$end", text)
    identifiers = [identifier for _, identifier, _ in declarations]
    names = {name for _, _, name in declarations}
    assert len(identifiers) == len(set(identifiers))
    assert "$enddefinitions $end" in text
    assert text.endswith("#178\n")
    assert {
        "pc",
        "condition_flags",
        "lsu_out",
        "constant",
        "data_controller_state_0",
    } <= names
    assert _parse_vcd(text) == (178, 398)


def _parse_vcd(text: str) -> tuple[int, int]:
    header, body = text.split("$enddefinitions $end\n", 1)
    identifiers = {
        line.split()[3]
        for line in header.splitlines()
        if line.strip().startswith("$var wire ")
    }
    times: list[int] = []
    for line in body.splitlines():
        if not line:
            continue
        if line.startswith("#"):
            times.append(int(line[1:]))
            continue
        if line[0] in "01xz":
            identifier = line[1:]
        elif line.startswith(("b", "B")):
            _, identifier = line.split()
        else:
            raise AssertionError(f"unsupported VCD value line: {line!r}")
        assert identifier in identifiers, f"undefined VCD identifier {identifier}"

    assert times == sorted(times)
    assert times[0] == 0
    return times[-1], len(identifiers)


def test_cli_writes_jsonl_vcd_and_perfetto(tmp_path):
    jsonl = tmp_path / "matadd.jsonl"
    vcd = tmp_path / "matadd.vcd"
    perfetto = tmp_path / "matadd.perfetto.json"

    assert main(["matadd", "--format", "jsonl", "--output", str(jsonl)]) == 0
    assert main(["matadd", "--format", "vcd", "--output", str(vcd)]) == 0
    assert main(["matadd", "--format", "perfetto", "--output", str(perfetto)]) == 0

    assert len(read_jsonl(jsonl)) == 1424
    assert vcd.read_text().startswith("$date\n")
    trace = json.loads(perfetto.read_text())
    assert sum(event.get("name") == "thread_name" for event in trace["traceEvents"]) == 10
