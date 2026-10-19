from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = REPO_ROOT / "test"
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from rtl_trace import records_from_log


SMALL_LOG = """\
================================== Cycle 0 ==================================

+--------------------- Core 0 ---------------------+

+-------- Thread 0 --------+
PC: 0
Instruction: ADD R1, R2, R3
Instruction Bits: 0011000100100011
Core State: IDLE
Fetcher State: IDLE
LSU State: IDLE
Registers: R0 = 0, R1 = 0, R2 = 0, R3 = 0, R4 = 0, R5 = 0, R6 = 0, R7 = 0, R8 = 0, R9 = 0, R10 = 0, R11 = 0, R12 = 0, %blockIdx = 0, %blockDim = 4, %threadIdx = 0
RS = 0, RT = 0
ALU Out: 0
Core Done: 0
"""


def test_normalization_uses_raw_bits_not_assembly_formatting(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text(SMALL_LOG)
    second.write_text(SMALL_LOG.replace("ADD R1, R2, R3", "ADD    R1,R2,R3"))

    first_record = records_from_log(first)[0]
    second_record = records_from_log(second)[0]
    assert first_record.to_dict() == second_record.to_dict()
    assert first_record.instruction_bits == 0b0011000100100011
    assert first_record.decoded.name == "ADD"


def test_optional_lsu_and_constant_fields_are_captured(tmp_path):
    log = tmp_path / "trace.txt"
    log.write_text(SMALL_LOG.replace("ALU Out: 0", "LSU Out: 9\nConstant: 7"))
    record = records_from_log(log)[0]
    assert record.alu_out is None
    assert record.lsu_out == 9
    assert record.constant == 7


def test_missing_raw_instruction_bits_is_an_error(tmp_path):
    log = tmp_path / "trace.txt"
    log.write_text(SMALL_LOG.replace("Instruction Bits: 0011000100100011\n", ""))
    try:
        records_from_log(log)
    except ValueError as error:
        assert "Instruction Bits" in str(error)
    else:
        raise AssertionError("expected missing Instruction Bits to fail")
