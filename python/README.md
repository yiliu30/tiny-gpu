# tiny-gpu Python model

A deterministic, cycle-accurate Python model of the RTL at commit `02b6c2c`.
Hardware modules map one-to-one to `src/*.sv` so the two implementations can be
read side by side. See [MODULE_GUIDE.md](MODULE_GUIDE.md) for the module map,
execution phases, memory handshakes, and known RTL quirks.

## Quick start

The package targets Python 3.10+ and has no runtime dependencies.

```bash
cd python
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest -q
```

Run a bundled kernel and write a trace:

```bash
# Canonical JSONL records.
tiny-gpu-trace matadd --format jsonl -o matadd.jsonl

# Waveform viewer (GTKWave, Surfer, etc.).
tiny-gpu-trace matadd --format vcd -o matadd.vcd

# Timeline viewer: open the file at https://ui.perfetto.dev/.
tiny-gpu-trace matmul --format perfetto -o matmul.perfetto.json
```

`--mode full` is the default and captures every enabled lane plus architectural
state. `--mode compatibility` reproduces the fields emitted by the original RTL
test logs. Supported kernels are `matadd`, `matmul`, and the bounded
`partial` block scenario.

## Verified baselines

The Python model matches the pinned RTL fixtures exactly, including the first
and last observed cycles.

| Kernel | Mode | Cycles | Records | Lanes | Result |
| --- | --- | ---: | ---: | --- | --- |
| matadd | compatibility | 178 | 1424 | 4 lanes x 2 cores | `[0, 2, 4, 6, 8, 10, 12, 14]` |
| matadd | full | 178 | 1424 | 4 lanes x 2 cores | same |
| matmul | compatibility | 491 | 491 | global thread 1 | `[7, 10, 15, 22]` |
| matmul | full | 491 | 1964 | 4 lanes x 1 core | same |
| partial | compatibility | 60 | 303 | 5 threads total | stale-PC quirk preserved |

Full records add `alu_out`, `lsu_out`, `constant`, and `nzp` for every enabled
lane. One record per cycle carries the global `arch_state` object containing
the dispatcher, controllers, fetchers, LSU relay, memory ports, DCR, and
top-level `done` signal.

## Trace formats

- JSONL is the canonical source and the format consumed by the comparator.
- VCD contains core stages, fetches, instructions, PC, lane LSU state,
  registers, ALU/LSU/constant outputs, NZP, and flattened architectural state.
- Perfetto contains one core-stage track and one track per enabled lane. Full
  matadd has 10 tracks; full matmul has 5. One simulated cycle is 1 us.

The writers consume `TraceRecord` objects directly. They do not parse RTL text
logs.

## Simulation contract

Each cycle performs these phases in order:

1. Service external program and data memory.
2. Settle combinational values.
3. Capture the pre-edge trace.
4. Evaluate clocked processes.
5. Commit staged nonblocking assignments.

The RTL testbench checks `done` before the current edge commits, so the Python
runner deliberately captures the final trailing cycle. Do not replace this with
a conventional `while not done` loop.

`Gpu.run_until_testbench_done()` delegates to the shared `SimulationHarness`.
`Gpu` validates the pinned compatibility profile at construction and rejects
unsupported address widths, data widths, channel counts, core counts, and lanes
per core before simulation starts.

## Pinned comparison semantics

`compare_traces()` always requires every expected field to match. Its default
partial mode ignores fields that appear only in the actual record, which permits
comparison against older logs that captured fewer values. Use
`strict_fields=True` for complete parity; it reports an unexpected actual field
as a divergence.

The arithmetic-logic unit reproduces the pinned RTL comparison behavior. It
wraps `rs - rt` to eight bits and compares that unsigned result with zero. A
nonzero wrapped result sets the positive bit, including for a mathematical
negative difference, so the negative bit is never set. This deliberately
preserves the reference RTL instead of correcting it.

## Fixtures and differential testing

The committed fixtures live in `test/fixtures/traces/02b6c2c/`. They include
compatibility and full traces, counts, lanes, SHA-256 hashes, and source-log
provenance.

To regenerate them from RTL logs with stable names:

```bash
mkdir -p build
TINY_GPU_LOG_FILE=test/logs/matadd_compatibility.txt make test_matadd
TINY_GPU_LOG_FILE=test/logs/matmul_compatibility.txt make test_matmul
TINY_GPU_LOG_FILE=test/logs/partial_compatibility.txt make test_partial_block
TINY_GPU_FULL_TRACE=1 TINY_GPU_LOG_FILE=test/logs/matadd_full.txt make test_matadd
TINY_GPU_FULL_TRACE=1 TINY_GPU_LOG_FILE=test/logs/matmul_full.txt make test_matmul

python3 test/generate_trace_fixtures.py \
  --matadd-log test/logs/matadd_compatibility.txt \
  --matmul-log test/logs/matmul_compatibility.txt \
  --matadd-full-log test/logs/matadd_full.txt \
  --matmul-full-log test/logs/matmul_full.txt \
  --partial-log test/logs/partial_compatibility.txt
```

RTL logs are intentionally gitignored; the normalized fixtures are committed.
`test/run_rtl_differential.sh` performs the full regeneration and fails if any
fixture changes. The RTL differential workflow is manual/scheduled because it
requires Icarus Verilog, sv2v, and cocotb, while the fast Python suite does not.

## Scope

This is an executable architectural model, not synthesizable RTL. It preserves
the pinned two-core, four-lanes-per-core compatibility profile and does not add
caches, pipelining, branch divergence, or arbitrary `X` propagation. The only
explicit unknown values are the RTL relay outputs that are still `X` in cycle 0;
they are represented as `null` and then become known on the launch edge.
