import hashlib
import json
from pathlib import Path

from tiny_gpu.trace import read_jsonl


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "test" / "fixtures" / "traces" / "02b6c2c"


def test_manifest_and_fixtures_are_consistent():
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text())
    assert manifest["rtl_commit"] == "02b6c2c"
    for kernel, expected_cycles in (("matadd", 178), ("matmul", 491), ("partial", 60)):
        for mode, entry in manifest["fixtures"][kernel].items():
            path = REPO_ROOT / entry["path"]
            assert path.name == f"{mode}.jsonl"
            assert path.read_bytes() == (FIXTURE_ROOT / kernel / f"{mode}.jsonl").read_bytes()
            assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
            records = read_jsonl(path)
            assert len(records) == entry["records"]
            assert max(record.cycle for record in records) + 1 == expected_cycles
            assert max(record.cycle for record in records) + 1 == entry["cycles"]
            assert entry["mode"] == mode


def test_full_fixtures_include_every_lane_and_architecture_state():
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text())
    for kernel, expected_records in (("matadd", 1424), ("matmul", 1964)):
        entry = manifest["fixtures"][kernel]["full"]
        records = read_jsonl(FIXTURE_ROOT / kernel / "full.jsonl")
        assert len(records) == expected_records == entry["records"]
        assert entry["lanes"] == [0, 1, 2, 3]
        assert all(record.nzp is not None for record in records)
        state_records = [record for record in records if "arch_state" in record.extra]
        assert len(state_records) == entry["cycles"]
        assert len({record.cycle for record in state_records}) == entry["cycles"]


def test_matadd_first_fetch_cycle_matches_rtl_fixture():
    records = read_jsonl(FIXTURE_ROOT / "matadd" / "compatibility.jsonl")
    first_fetch = min(record.cycle for record in records if record.core_state == "FETCH")
    assert first_fetch == 2
