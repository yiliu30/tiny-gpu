#!/usr/bin/env python3
"""Prove that a one-field Verilog mutation fails canonical trace comparison."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from tiny_gpu.gpu import Gpu
from tiny_gpu.kernels import MATADD_INPUT, MATADD_PROGRAM
from tiny_gpu.trace import TraceComparisonError, compare_traces, read_jsonl


def main() -> int:
    """Inject one field mismatch and confirm that comparison reports it."""

    fixture = REPO_ROOT / "test/fixtures/traces/02b6c2c/matadd/full.jsonl"
    expected = read_jsonl(fixture)
    expected[100].pc = (expected[100].pc + 1) & 0xFF

    gpu = Gpu()
    gpu.load_program(MATADD_PROGRAM)
    gpu.load_data(MATADD_INPUT)
    gpu.boot(thread_count=8)
    actual, _ = gpu.run_until_testbench_done(full=True)

    try:
        compare_traces(expected, actual, strict_fields=True)
    except TraceComparisonError as error:
        divergence = error.divergence
        if divergence.kind != "field" or divergence.field != "pc":
            raise
        print(
            "Injected mismatch detected at "
            f"cycle {divergence.cycle}, core {divergence.core}, "
            f"lane {divergence.lane}: {divergence.field}"
        )
        return 0

    print("ERROR: injected mismatch was not detected", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
