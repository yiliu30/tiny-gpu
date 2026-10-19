from pathlib import Path

from tiny_gpu.cli import main, simulate
from tiny_gpu.trace import compare_traces, read_jsonl


FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "test/fixtures/traces/02b6c2c"


def test_matmul_compatibility_cli_matches_thread_one_fixture(tmp_path):
    output = tmp_path / "matmul-compatibility.jsonl"

    assert (
        main(
            [
                "matmul",
                "--mode",
                "compatibility",
                "--format",
                "jsonl",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    records = read_jsonl(output)
    expected = read_jsonl(FIXTURE_ROOT / "matmul" / "compatibility.jsonl")
    compare_traces(expected, records)
    assert len(records) == 491
    assert {record.thread_id for record in records} == {1}


def test_thread_filter_is_independent_of_full_field_selection():
    _, records, cycles = simulate("matmul", mode="full", thread_id=1)

    assert cycles == 491
    assert len(records) == 491
    assert {record.thread_id for record in records} == {1}
    assert all(record.nzp is not None for record in records)
