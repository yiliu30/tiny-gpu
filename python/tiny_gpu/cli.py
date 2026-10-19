"""Run a bundled kernel and write a canonical trace."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .exporters import write_perfetto, write_vcd
from .gpu import Gpu
from .kernels import MATADD_INPUT, MATADD_PROGRAM, MATMUL_INPUT, MATMUL_PROGRAM
from .trace import TraceRecord, write_jsonl


PARTIAL_PROGRAM = [
    0b1001000100000111,  # CONST R1, #7
    0b1111000000000000,  # RET
]

FORMAT_SUFFIXES = {
    "jsonl": ".jsonl",
    "vcd": ".vcd",
    "perfetto": ".perfetto.json",
}


def simulate(kernel: str, *, mode: str = "full") -> tuple[Gpu, list[TraceRecord], int]:
    full = mode == "full"
    compatibility = mode == "compatibility"

    if kernel == "matadd":
        gpu = Gpu()
        gpu.load_program(MATADD_PROGRAM)
        gpu.load_data(MATADD_INPUT)
        gpu.boot(thread_count=8)
        records, cycles = gpu.run_until_testbench_done(
            compatibility=compatibility,
            full=full,
        )
        return gpu, records, cycles

    if kernel == "matmul":
        gpu = Gpu()
        gpu.load_program(MATMUL_PROGRAM)
        gpu.load_data(MATMUL_INPUT)
        gpu.boot(thread_count=4)
        records, cycles = gpu.run_until_testbench_done(
            compatibility=compatibility,
            full=full,
        )
        return gpu, records, cycles

    if kernel == "partial":
        gpu = Gpu()
        gpu.load_program(PARTIAL_PROGRAM)
        gpu.boot(thread_count=5)
        records: list[TraceRecord] = []
        cycles = 60
        for cycle in range(cycles):
            gpu.service_external_memory()
            gpu.settle()
            records.extend(
                gpu.observe(
                    cycle,
                    compatibility=compatibility,
                    full=full,
                )
            )
            gpu.evaluate_clocked()
            gpu.commit()
        return gpu, records, cycles

    raise ValueError(f"unknown kernel {kernel!r}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel", choices=("matadd", "matmul", "partial"))
    parser.add_argument(
        "--mode",
        choices=("full", "compatibility"),
        default="full",
        help="full captures every enabled lane and architectural state",
    )
    parser.add_argument(
        "--format",
        choices=tuple(FORMAT_SUFFIXES),
        default="jsonl",
        dest="trace_format",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="output path (default: <kernel>-<mode> with the format suffix)",
    )
    args = parser.parse_args(argv)

    gpu, records, cycles = simulate(args.kernel, mode=args.mode)
    output = args.output or Path(
        f"{args.kernel}-{args.mode}{FORMAT_SUFFIXES[args.trace_format]}"
    )
    source = f"{args.kernel} {args.mode} Python trace"
    if args.trace_format == "jsonl":
        output.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl(output, records)
    elif args.trace_format == "vcd":
        write_vcd(output, records, source=source)
    else:
        write_perfetto(output, records, source=source)

    print(f"Wrote {output}")
    print(f"  {cycles} cycles, {len(records)} records, mode={args.mode}")
    if args.kernel == "matadd":
        print(f"  result: {gpu.data_memory.memory[16:24]}")
    elif args.kernel == "matmul":
        print(f"  result: {gpu.data_memory.memory[8:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
