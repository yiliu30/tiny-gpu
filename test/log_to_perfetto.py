#!/usr/bin/env python3
"""Convert a tiny-gpu textual cycle trace into Chrome Trace Event JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .log_to_vcd import CycleSnapshot, parse_log
except ImportError:
    from log_to_vcd import CycleSnapshot, parse_log


PROCESS_ID = 1


def build_trace(cycles: list[CycleSnapshot], source: Path) -> dict[str, object]:
    events: list[dict[str, object]] = []
    core_ids = sorted({core for cycle in cycles for core in cycle.cores})
    lanes_by_core: dict[int, list[int]] = {core: [] for core in core_ids}

    for cycle in cycles:
        for core_id, core in cycle.cores.items():
            for thread in core.threads:
                if thread.lane is not None and thread.lane not in lanes_by_core[core_id]:
                    lanes_by_core[core_id].append(thread.lane)
    for lanes in lanes_by_core.values():
        lanes.sort()

    events.append({
        "ph": "M",
        "name": "process_name",
        "pid": PROCESS_ID,
        "args": {"name": f"tiny-gpu · {source.stem}"},
    })
    events.append({
        "ph": "M",
        "name": "process_sort_index",
        "pid": PROCESS_ID,
        "args": {"sort_index": 0},
    })

    track_ids: dict[tuple[int, str], int] = {}
    thread_id = 1
    for core_id in core_ids:
        track_ids[(core_id, "state")] = thread_id
        events.append({
            "ph": "M",
            "name": "thread_name",
            "pid": PROCESS_ID,
            "tid": thread_id,
            "args": {"name": f"Core {core_id} · state"},
        })
        events.append({
            "ph": "M",
            "name": "thread_sort_index",
            "pid": PROCESS_ID,
            "tid": thread_id,
            "args": {"sort_index": core_id * 100},
        })
        thread_id += 1

        for lane in lanes_by_core[core_id]:
            track_ids[(core_id, f"lane{lane}")] = thread_id
            events.append({
                "ph": "M",
                "name": "thread_name",
                "pid": PROCESS_ID,
                "tid": thread_id,
                "args": {"name": f"Core {core_id} · Lane {lane}"},
            })
            events.append({
                "ph": "M",
                "name": "thread_sort_index",
                "pid": PROCESS_ID,
                "tid": thread_id,
                "args": {"sort_index": core_id * 100 + lane + 1},
            })
            thread_id += 1

    # Perfetto's Chrome JSON importer treats timestamps as microseconds. Using
    # fractional values makes one cycle equal to one nanosecond in the UI.
    timestamp_scale = 1 / 1000

    for cycle in cycles:
        for core_id, core in cycle.cores.items():
            events.append({
                "ph": "X",
                "name": core.state,
                "cat": "core stage",
                "pid": PROCESS_ID,
                "tid": track_ids[(core_id, "state")],
                "ts": cycle.index * timestamp_scale,
                "dur": timestamp_scale,
                "args": {
                    "cycle": cycle.index,
                    "core": core_id,
                    "stage": core.state,
                    "fetcher": core.fetcher_state,
                    "instruction": core.instruction_text,
                    "pc": core.pc,
                    "done": core.done,
                },
            })

            for thread in core.threads:
                if thread.lane is None:
                    continue
                args: dict[str, object] = {
                    "cycle": cycle.index,
                    "core": core_id,
                    "lane": thread.lane,
                    "stage": core.state,
                    "instruction": core.instruction_text,
                    "pc": core.pc,
                    "lsu_state": thread.lsu_state,
                    "rs": thread.rs,
                    "rt": thread.rt,
                    "alu_out": thread.alu_out,
                }
                args.update(thread.registers)
                events.append({
                    "ph": "X",
                    "name": core.instruction or "NOP",
                    "cat": "lane execution",
                    "pid": PROCESS_ID,
                    "tid": track_ids[(core_id, f"lane{thread.lane}")],
                    "ts": cycle.index * timestamp_scale,
                    "dur": timestamp_scale,
                    "args": args,
                })

    return {
        "traceEvents": events,
        "displayTimeUnit": "ns",
        "metadata": {
            "name": f"tiny-gpu trace: {source.name}",
            "one_cycle": "1 ns",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="tiny-gpu cycle log to convert")
    parser.add_argument("-o", "--output", type=Path, help="output JSON path (default: beside the log)")
    args = parser.parse_args()

    cycles = parse_log(args.log)
    output = args.output or args.log.with_name(f"{args.log.stem}.perfetto.json")
    trace = build_trace(cycles, args.log)
    output.write_text(json.dumps(trace, separators=(",", ":")) + "\n")

    tracks = sum(1 for event in trace["traceEvents"] if event.get("name") == "thread_name")
    print(f"Wrote {output}")
    print(f"  {len(cycles)} cycles, {tracks} tracks, {len(trace['traceEvents'])} trace events")


if __name__ == "__main__":
    main()
