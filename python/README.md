# tiny-gpu Python model

This package contains the first four stages of a Python model for tiny-gpu. It
provides a readable bridge to the Verilog register-transfer-level (RTL)
hardware model. Each Python module mirrors one hardware source file where that
module exists, so the two implementations can be read side by side.

Stage A models the small building blocks and the shared simulation machinery:

- `alu.py`: the arithmetic-logic unit (`Alu`), which performs addition,
  subtraction, multiplication, division, and comparison operations.
- `decoder.py`: the instruction decoder (`Decoder`), which turns a 16-bit
  instruction into control signals.
- `registers.py`: one lane's register file (`RegisterFile`), including the
  read-only block and thread identity registers and the arithmetic-logic or
  load-store result selected for a write.
- `pc.py`: one lane's program counter (`PcUnit`) and its negative, zero, and
  positive (NZP) condition bits used by branch instructions.
- `harness.py`: the ordered simulation phases that keep observations and clock
  updates in the same order as the Verilog testbench.
- `trace.py`: canonical trace records, deterministic JavaScript Object Notation
  (JSON) Lines input/output (one JSON value per line), and first-difference
  comparison.
- `memory.py`: external memory used by the testbench.
- `isa.py`: instruction-set architecture constants and field extraction.

Stage B adds the shared control path for one compute core:

- `fetcher.py`: requests the 16-bit instruction selected by the program counter
  and holds it until decoding begins.
- `scheduler.py`: advances the core through fetch, decode, memory request,
  memory wait, execute, and update states.
- `core.py`: joins the shared decoder, scheduler, and fetcher with one
  arithmetic-logic unit, register file, program counter, and load-store stub per
  lane. A lane is one parallel thread position within a block.
- `kernels.py`: binary instruction images for the bundled matrix-addition and
  matrix-multiplication examples.

During Stage B, a temporary load-store placeholder rejected `LDR` and `STR`
instead of silently returning zero load data. Stage C replaces it with the real
load-store unit described below.

Stage C adds the data-memory path and shared arbitration:

- `lsu.py`: one load-store unit (LSU) per lane. A load reads a data-memory value;
  a store writes one. The unit requests access, waits for the response, holds
  the returned value, and then returns to idle.
- `controller.py`: a shared memory controller. A **consumer** is a unit that
  requests memory access, and a **channel** is one external memory connection.
  The controller gives each active consumer sole ownership of a channel until
  its request is acknowledged and released, so two lanes cannot use the same
  channel at once.

Stage D adds the complete top-level graphics processing unit (GPU) wiring:

- `dcr.py`: the device control register (`Dcr`). This register stores the total
  number of threads that the next kernel should launch.
- `dispatch.py`: the block dispatcher (`Dispatch`). A **thread** is one parallel
  execution position, and a **block** is a group of threads that one core runs
  together. The dispatcher assigns each block to an available core and reports
  completion when all blocks finish.
- `gpu.py`: the complete `Gpu` wrapper. It connects the device control register,
  dispatcher, compute cores, program-memory controller, data-memory controller,
  and external memories.

The model now runs full kernels through the same launch sequence as the Verilog
testbench: reset, write the thread count, assert start, run until the dispatcher
reports completion, and capture pre-edge trace records. It reproduces all 178
matrix-addition cycles and all 491 compatibility-filtered matrix-multiplication
cycles. Later Stage E adds complete-lane traces and command-line export tools.
`Gpu.run_until_testbench_done()` delegates to the shared `SimulationHarness`.
`Gpu` also validates the pinned compatibility profile at construction time and
rejects unsupported address widths, data widths, channel counts, core counts,
and lanes per core instead of producing a misleading trace.

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
preserves the behavior of the reference RTL instead of correcting it.

Run the fast, simulator-independent tests with:

```bash
cd python
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest -q
```

The trace fixture and normalization tools in `test/` let the Python model be
checked against logs produced by the Verilog design. Stage C compares all 178
cycles and checks that the result stored in data memory is
`[0, 2, 4, 6, 8, 10, 12, 14]`. Stage D adds the top-level GPU and checks the
491-cycle, single-thread matrix-multiplication compatibility trace with the
result `[7, 10, 15, 22]`. Open a module beside its same-named file in `src/` to
follow the hardware-to-Python mapping.
