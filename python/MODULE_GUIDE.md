# Verilog-to-Python module guide

This is the reading path from the tiny-gpu Verilog register-transfer-level (RTL)
design to the Python model. Open each Python file beside its Verilog counterpart
and read the module docstring first; every modeled hardware file names its
source module.

The design uses four parallel thread positions, called **lanes**, inside each
compute core. When several lanes or cores want to use one external memory
connection, a **memory consumer** is a unit making the request and a **memory
channel** is one connection to external memory.

## Module map

| Verilog module | Python module | Responsibility | Important state and outputs |
| --- | --- | --- | --- |
| `gpu.sv` | `tiny_gpu/gpu.py` | Top-level graphics-processing-unit wiring, external memory service, and lane plus fetch relays | `done`, controller ports, relay arrays, `full_trace_state()` |
| `dcr.sv` | `tiny_gpu/dcr.py` | Device control register | 8-bit thread count |
| `dispatch.sv` | `tiny_gpu/dispatch.py` | Split threads into blocks and assign them to available cores | `blocks_dispatched`, `blocks_done`, `core_start`, `core_reset`, `done` |
| `core.sv` | `tiny_gpu/core.py` | Shared control plus four lane-local execution paths | instruction, lane records, full lane observation |
| `scheduler.sv` | `tiny_gpu/scheduler.py` | Core stage progression and block completion | `current_pc`, `core_state`, `done` |
| `fetcher.sv` | `tiny_gpu/fetcher.py` | Program-memory fetch handshake | fetcher state, read valid and address, instruction |
| `decoder.sv` | `tiny_gpu/decoder.py` | Decode the 16-bit instruction | arithmetic-logic-unit, program-counter, load-store-unit, and condition-bit controls |
| `registers.sv` | `tiny_gpu/registers.py` | Thirteen writable registers plus three identity registers | `rs`, `rt`, register file |
| `alu.sv` | `tiny_gpu/alu.py` | Arithmetic-logic unit for add, subtract, multiply, divide, and compare | `alu_out` |
| `lsu.sv` | `tiny_gpu/lsu.py` | Load-store-unit request and response handshakes | load-store state, read and write valid and address, `lsu_out` |
| `pc.sv` | `tiny_gpu/pc.py` | Per-lane next-program-counter and negative-zero-positive condition update | `next_pc`, `nzp` |
| `controller.sv` | `tiny_gpu/controller.py` | Arbitrate multiple consumers onto limited memory channels | channel state, current consumer, serving mask, memory ports |

Support modules are intentionally not hardware:

- `isa.py` contains instruction-set architecture encodings and names.
- `memory.py` provides external testbench memory.
- `trace.py` defines canonical trace records and comparison.
- `exporters.py` writes Value Change Dump waveforms and Perfetto timelines.
- `kernels.py` contains bundled program and data images.
- `cli.py` is the command-line runner.
- `harness.py` defines the explicit simulation phase protocol.

## One simulated cycle

`Gpu.run_until_testbench_done()` and the command-line interface follow the
`cocotb` observation order exactly. A **clocked** value changes only at a clock
edge. A **combinational** value is derived from current inputs without saved
state.

1. `service_external_memory()` returns responses for requests captured at the
   preceding clock edge. Writes become visible at this point.
2. `settle()` is the combinational-settle point. The current model has no
   separate combinational evaluator, so this is intentionally a no-op.
3. `observe()` captures the pre-edge trace, including one global architectural
   snapshot per cycle.
4. `evaluate_clocked()` asks every clocked module for its next state while all
   modules still see the old state.
5. `commit()` publishes all staged nonblocking assignments together. A
   nonblocking assignment computes a value during evaluation but makes it
   visible only at the clock edge.

The Verilog testbench checks `done` before the rising clock edge. The Python
loop records that pre-edge value, evaluates one more edge, and exits on the next
iteration. That is why the final record is one trailing cycle after `done`
first becomes high in the committed state.

## Program-memory path

The instruction path is:

`fetcher -> program controller -> external program memory -> program controller -> fetcher`

The fetcher asserts `read_valid` and supplies an address. The controller scans
consumers in ascending order, claims one with its blocking ownership mask, and
drives one external read channel. The external memory response appears before
the next pre-edge capture; the controller relays it to the selected consumer.

## Data-memory path and relay delay

The load-store path is:

`lane load-store unit -> core output -> top-level load-store relay -> data controller -> external data memory -> data controller -> top-level response relay -> lane load-store unit`

Two timing boundaries must be preserved:

- The top-level relay registers `valid`, `address`, and write data before the
  controller sees them.
- Controller response valid and data are registered again on the way back to the
  core.

The compatibility traces keep these boundaries instead of flattening them. They
are why the controller must not service a request in the same observation cycle
in which the request first becomes visible.

## Controller arbitration

`controller.py` mirrors the Verilog statement order inside one clocked process:

- Consumers are scanned from index 0 upward for each channel.
- A read is checked before a write for each consumer.
- `serving` is a blocking-assignment ownership mask shared by all channels. A
  blocking assignment becomes visible immediately inside the same process.
- Channels are processed sequentially in that one clocked process.
- Read and write relay states wait for the consumer request to deassert before
  releasing ownership.

Changing any of these rules changes which lane receives a response first and
breaks the complete-lane reference traces.

## Core and lane behavior

All lanes share one scheduler, fetcher, decoder, and fetched-instruction view.
Each lane owns an arithmetic-logic unit, load-store unit, register file, program
counter, negative-zero-positive condition register, and next-program-counter
value. The scheduler advances the core through `IDLE`, `FETCH`, `DECODE`,
`REQUEST`, `WAIT`, `EXECUTE`, `UPDATE`, and `DONE`.

At `UPDATE`, the scheduler selects `next_pc[threads_per_block - 1]` to model the
Verilog design's assumption that all active threads converge to the same next
instruction. In a partial final block, inactive lanes retain stale
next-program-counter values. The model preserves that pinned behavior rather
than repairing it.

## Dispatcher behavior

The dispatcher computes `ceil(thread_count / 4)` blocks, resets a core before
launching its next block, and marks the kernel done when `blocks_done ==
total_blocks`. The final block receives the remaining thread count, which may be
smaller than four.

## Trace coverage

A compatibility record reproduces the original text log: all enabled lanes for
matrix addition (`matadd`), but only global thread 1 for matrix multiplication
(`matmul`), plus only the selected output. A full record adds:

- arithmetic-logic-unit output, load-store-unit output, constant, and
  negative-zero-positive values for every enabled lane;
- `arch_state` on the first record of each cycle.

`arch_state` mirrors the Verilog JSON snapshot: device control register,
dispatcher, both controllers, program and data memory ports, fetch relays,
load-store relays, and top-level `done`. Icarus Verilog exposes unpacked arrays
in reverse index order; `test/helpers/format.py` reverses those values so fixture
arrays always use natural consumer and channel order.

## Reading a divergence

`compare_traces()` reports the first missing or unexpected record, or the first
mismatching field. Use the reported cycle, core, and lane to inspect the same
observation in both fixtures. If the divergence is in `arch_state`, first decide
whether it is a controller timing issue, a relay ordering issue, or a dispatcher
boundary issue before changing lane arithmetic.
