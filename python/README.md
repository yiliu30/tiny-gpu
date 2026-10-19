# tiny-gpu Python model

This package is the first stage of a Python model for tiny-gpu. It provides a
readable bridge to the Verilog register-transfer-level (RTL) hardware model.
Each Python module mirrors one hardware source file where that module exists, so
the two implementations can be read side by side.

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

This stage does not yet model a complete graphics processing unit (GPU). Later
stages add core control, memory arbitration, block dispatch, and the top-level
GPU.

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
checked against logs produced by the Verilog design. Open a module beside its
same-named file in `src/` to follow the hardware-to-Python mapping.
