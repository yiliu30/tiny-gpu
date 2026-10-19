# tiny-gpu Python model

A deterministic, cycle-accurate Python model of the tiny-gpu hardware at Verilog
commit `02b6c2c`. The model preserves the timing visible in the original
register-transfer-level (RTL) design: the state that exists before each clock
edge, the values evaluated at that edge, and the order in which memory and
control changes become visible.

The Python files intentionally follow the hardware module layout in `src/*.sv`,
so the two implementations can be read side by side. See
[MODULE_GUIDE.md](MODULE_GUIDE.md) for the detailed reading path, memory
handshakes, arbitration rules, and preserved hardware quirks.

## Terms used in this guide

- **Register-transfer level (RTL):** hardware code that describes state
  registers and the logic evaluated between clock edges.
- **Module:** one Verilog file and the hardware block it describes. Each hardware
  module has a same-named Python file when that block is modeled.
- **Lane:** one thread position inside a compute core. This design supports four
  parallel lanes per core.
- **Kernel:** one program launched across a requested number of threads.
- **Block:** a group of threads that one core executes together.
- **Cycle-accurate:** the model reproduces the state visible in each simulated
  clock cycle, not only the final program result.
- **Architectural state:** the controller, dispatcher, fetch, memory, and
  completion values that are visible outside the individual lanes.

## Hardware module layout

| Python module | Verilog counterpart | Responsibility |
| --- | --- | --- |
| `tiny_gpu/gpu.py` | `src/gpu.sv` | Top-level graphics-processing-unit wiring, external memory service, and trace capture |
| `tiny_gpu/dcr.py` | `src/dcr.sv` | Device control register storing the requested thread count |
| `tiny_gpu/dispatch.py` | `src/dispatch.sv` | Split threads into blocks and assign blocks to available cores |
| `tiny_gpu/core.py` | `src/core.sv` | Shared core control plus one set of lane-local execution units |
| `tiny_gpu/scheduler.py` | `src/scheduler.sv` | Advance the core through fetch, decode, memory wait, execute, update, and completion |
| `tiny_gpu/fetcher.py` | `src/fetcher.sv` | Request the next program-memory instruction and hold it until decoding |
| `tiny_gpu/decoder.py` | `src/decoder.sv` | Decode a 16-bit instruction into control signals |
| `tiny_gpu/registers.py` | `src/registers.sv` | Thirteen writable registers plus block and thread identity registers |
| `tiny_gpu/alu.py` | `src/alu.sv` | Arithmetic-logic unit (`Alu`) for add, subtract, multiply, divide, and compare operations |
| `tiny_gpu/lsu.py` | `src/lsu.sv` | Load-store unit (`Lsu`) for data-memory read and write handshakes |
| `tiny_gpu/pc.py` | `src/pc.sv` | Per-lane program counter (`PcUnit`) and negative, zero, positive (NZP) condition bits |
| `tiny_gpu/controller.py` | `src/controller.sv` | Arbitrate several memory consumers onto a limited number of external channels |

Support modules are not hardware blocks:

- `isa.py` contains instruction-set architecture constants, opcode names, and
  instruction-field extraction.
- `memory.py` provides external program and data memory for the testbench.
- `trace.py` defines canonical records, deterministic JavaScript Object Notation
  (JSON) Lines input and output, and first-difference comparison.
- `exporters.py` writes waveform and timeline trace formats.
- `kernels.py` contains machine-code images for the bundled examples.
- `cli.py` provides the command-line interface (CLI).
- `harness.py` defines the explicit simulation phase order.

## Quick start

The package requires Python 3.10 or newer and has no runtime dependencies.

```bash
cd python
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest -q
```

Run a bundled kernel and write a trace:

```bash
# JSON Lines: one JavaScript Object Notation object per line.
tiny-gpu-trace matadd --format jsonl -o matadd.jsonl

# Value Change Dump waveform for GTKWave, Surfer, or another waveform viewer.
tiny-gpu-trace matadd --format vcd -o matadd.vcd

# Timeline file to open at https://ui.perfetto.dev/.
tiny-gpu-trace matmul --format perfetto -o matmul.perfetto.json
```

The bundled kernels are matrix addition (`matadd`), matrix multiplication
(`matmul`), and a short partial-final-block example (`partial`).

The default `--mode full` captures every enabled lane and one complete
architectural snapshot per cycle. `--mode compatibility` reproduces only the
fields emitted by the original Verilog text logs. Compatibility mode is useful
for checking the historical log format; full mode is better for learning and
for complete-lane debugging.

## Verified baselines

The Python model matches the checked-in Verilog reference traces exactly,
including the first and last observed cycles.

| Kernel | Mode | Cycles | Records | Lanes | Result |
| --- | --- | ---: | ---: | --- | --- |
| Matrix addition (`matadd`) | compatibility | 178 | 1,424 | 4 lanes across 2 cores | `[0, 2, 4, 6, 8, 10, 12, 14]` |
| Matrix addition (`matadd`) | full | 178 | 1,424 | 4 lanes across 2 cores | same |
| Matrix multiplication (`matmul`) | compatibility | 491 | 491 | global thread 1 | `[7, 10, 15, 22]` |
| Matrix multiplication (`matmul`) | full | 491 | 1,964 | 4 lanes on 1 core | same |
| Partial final block (`partial`) | compatibility | 60 | 303 | 5 threads across 2 cores | stale-program-counter behavior preserved |

Full records add arithmetic-logic-unit output, load-store-unit output, constant,
and negative-zero-positive condition values for every enabled lane. The first
record of each cycle also carries one `arch_state` architectural snapshot.

## Trace formats

- JSON Lines is the canonical format used by the Python comparator. Each line is
  one independent JSON record.
- Value Change Dump is a standard waveform format. It contains core stages,
  fetch and instruction signals, the program counter, load-store state,
  registers, arithmetic and memory outputs, condition bits, and flattened
  architectural state.
- Perfetto uses a browser timeline. It contains one core-stage track and one
  track per enabled lane. Full matrix addition has 10 tracks; full matrix
  multiplication has 5. One simulated cycle is represented as 1 microsecond.

The canonical writers consume Python `TraceRecord` objects directly. They do not
parse the older Verilog text logs.

## Simulation order

Each simulated cycle follows the same five phases as the Verilog testbench:

1. Return responses for external program and data memory requests captured at
   the preceding clock edge. Writes become visible during this phase.
2. Let combinational values settle.
3. Capture the trace state visible before the next clock edge.
4. Evaluate every clocked module while all modules still see the old state.
5. Publish all staged updates together, matching Verilog nonblocking
   assignments. A nonblocking assignment computes a new value now but makes it
   visible at the clock edge.

The Verilog testbench checks the top-level `done` signal before the current edge
commits. The Python runner therefore captures one final trailing cycle. Do not
replace this with a conventional `while not done` loop, because that would drop
the last cycle visible in the reference trace.

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

## Verification

The checked-in reference traces are called fixtures. They live in
`test/fixtures/traces/02b6c2c/` and include record counts, lane lists, SHA-256
integrity hashes, and source-log provenance.

Two kinds of verification are used:

- The fast Python test suite compares the model against the fixtures and checks
  module behavior without requiring a Verilog simulator.
- A differential test runs the Verilog design, regenerates the traces, and fails
  if any normalized fixture or Python result differs.

To regenerate fixtures from Verilog logs:

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

Verilog logs are intentionally ignored by version control; normalized fixtures
are committed. `test/run_rtl_differential.sh` runs the complete regeneration and
comparison. The full differential workflow requires Icarus Verilog, the `sv2v`
SystemVerilog-to-Verilog converter, and the `cocotb` Python verification
library.

Continuous integration (CI) has two workflows:

- `.github/workflows/python-tests.yml` runs the fast Python suite on Python 3.10
  and 3.12 for every push and pull request.
- `.github/workflows/rtl-differential.yml` runs the Verilog differential test on
  a schedule or by manual dispatch, because installing and running the Verilog
  tools takes longer.

## Scope

This is an executable architectural model, not synthesizable RTL. It preserves
the pinned two-core, four-lanes-per-core compatibility profile and does not add
caches, pipelining, branch divergence, or general handling of unknown values.
Branch divergence means threads taking different future instruction paths. The
only explicit unknown values are the top-level relay outputs that are still
unknown (`X`) in cycle 0 of the Verilog trace; Python represents them as `null`
and then makes them known on the launch edge.
