# RTL/Python module guide

This guide is the reading path from Verilog to Python. Open the files in each
row side by side; the Python module docstring also names its RTL counterpart.

## Module map

| RTL module | Python module | Responsibility | Important state/outputs |
| --- | --- | --- | --- |
| `gpu.sv` | `tiny_gpu/gpu.py` | Top-level wiring, external memory service, LSU and fetcher relays | `done`, controller ports, relay arrays, `full_trace_state()` |
| `dcr.sv` | `tiny_gpu/dcr.py` | Device control register | 8-bit thread count |
| `dispatch.sv` | `tiny_gpu/dispatch.py` | Split threads into blocks and assign them to idle cores | `blocks_dispatched`, `blocks_done`, `core_start`, `core_reset`, `done` |
| `core.sv` | `tiny_gpu/core.py` | Shared control plus four lane-local pipelines | instruction, lane records, full lane observation |
| `scheduler.sv` | `tiny_gpu/scheduler.py` | Core stage progression and block completion | `current_pc`, `core_state`, `done` |
| `fetcher.sv` | `tiny_gpu/fetcher.py` | Program-memory fetch handshake | fetcher state, read valid/address, instruction |
| `decoder.sv` | `tiny_gpu/decoder.py` | Decode the 16-bit instruction | ALU/PC/LSU/NZP control signals |
| `registers.sv` | `tiny_gpu/registers.py` | 13 writable registers plus three special registers | `rs`, `rt`, register file |
| `alu.sv` | `tiny_gpu/alu.py` | ADD/SUB/MUL/DIV and compare output | `alu_out` |
| `lsu.sv` | `tiny_gpu/lsu.py` | Load/store request and response handshakes | LSU state, read/write valid and address, `lsu_out` |
| `pc.sv` | `tiny_gpu/pc.py` | Per-lane next-PC and NZP update | `next_pc`, `nzp` |
| `controller.sv` | `tiny_gpu/controller.py` | Arbitrate multiple consumers onto limited memory channels | channel state, current consumer, serving mask, memory ports |

Support modules are intentionally not hardware: `isa.py` (encodings and names),
`memory.py` (external testbench memory), `trace.py` (records/comparison),
`exporters.py` (VCD/Perfetto), `kernels.py` (bundled programs/data), `cli.py`
(runner), and `harness.py` (explicit phase protocol).

## One simulated cycle

`Gpu.run_until_testbench_done()` and the CLI follow the cocotb observation
contract exactly:

1. `service_external_memory()` returns responses for the requests captured on
   the preceding edge. Writes become visible at this point.
2. `settle()` is the combinational-settle point. The current model has no
   separate combinational evaluator, so this is intentionally a no-op.
3. `observe()` captures the pre-edge trace, including the global architecture
   snapshot once per cycle.
4. `evaluate_clocked()` asks every clocked module for its next state while all
   blocks still see the old state.
5. `commit()` publishes all staged nonblocking assignments together.

The testbench checks `done` before the rising edge. The Python loop records that
pre-edge value, evaluates one more edge, and then exits on the next iteration.
That is why the last record is one trailing cycle after `done` first becomes
high in the committed state.

## Program-memory path

`fetcher -> program controller -> external program memory -> program controller
-> fetcher`

The fetcher asserts `read_valid` and an address. The controller scans consumers
in ascending order, claims one with its blocking ownership mask, and drives one
external read channel. The external memory response appears before the next
pre-edge capture; the controller relays it to the selected consumer.

## Data-memory path and relay delay

`lane LSU -> core output -> top-level LSU relay -> data controller -> external
data memory -> data controller -> top-level response relay -> lane LSU`

There are two timing boundaries worth preserving:

- The top-level relay registers `valid`, `address`, and write data before the
  controller sees them.
- Controller response valid/data are registered again on the way back to the
  core.

The compatibility traces do not flatten these boundaries. They are the reason
the controller must not service a request in the same observation cycle in
which it first becomes visible.

## Controller arbitration

`controller.py` mirrors the RTL statement order inside one clocked process:

- Consumers are scanned from index 0 upward for each channel.
- A read is checked before a write for each consumer.
- `serving` is a blocking-assignment ownership mask shared by all channels.
- Channels are processed sequentially in the same clocked process.
- Read and write relay states wait for the consumer request to deassert before
  releasing ownership.

Changing any of these rules changes which lane receives a response first and
will break full-lane fixtures.

## Core and lane behavior

All lanes share one scheduler, fetcher, decoder, and fetched-instruction view.
Each lane owns an ALU, LSU, register file, PC, NZP register, and next-PC value.
The scheduler advances the core through `IDLE`, `FETCH`, `DECODE`, `REQUEST`,
`WAIT`, `EXECUTE`, `UPDATE`, and `DONE`.

At `UPDATE`, the scheduler selects `next_pc[threads_per_block - 1]` to model the
RTL's assumption that all active threads converge. In a partial final block,
inactive lanes retain stale `next_pc` values. The model preserves that pinned
behavior rather than repairing it.

## Dispatcher behavior

The dispatcher computes `ceil(thread_count / 4)` blocks, resets a core before
launching its next block, and marks the kernel done when `blocks_done ==
total_blocks`. The final block receives the remaining thread count, which may
be smaller than four.

## Trace coverage

Compatibility records reproduce the original text log: all enabled lanes for
matadd, but only global thread 1 for matmul, plus only the mux-selected output.

Full records additionally contain:

- `alu_out`, `lsu_out`, `constant`, and `nzp` for every enabled lane;
- `arch_state` on the first record of each cycle.

`arch_state` mirrors the RTL JSON snapshot: DCR, dispatcher, both controllers,
program/data memory ports, fetcher relays, LSU relays, and top-level `done`.
Icarus exposes unpacked arrays in reverse index order; `test/helpers/format.py`
reverses those values so the fixture arrays always use natural consumer/channel
order.

## Reading a divergence

`compare_traces()` reports the first missing/unexpected record or the first
mismatching field. Use the reported `(cycle, core, lane)` to inspect the same
cycle in both fixtures. If the divergence is in `arch_state`, decide whether it
is a controller timing issue, a relay ordering issue, or a dispatcher boundary
before changing lane arithmetic.
