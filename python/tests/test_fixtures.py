import hashlib
import json
from pathlib import Path

from tiny_gpu.trace import read_jsonl


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "test" / "fixtures" / "traces" / "02b6c2c"


def test_manifest_and_compatibility_fixtures_are_consistent():
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text())
    assert manifest["rtl_commit"] == "02b6c2c"
    for kernel, expected_cycles in (("matadd", 178), ("matmul", 491)):
        entry = manifest["fixtures"][kernel]["compatibility"]
        path = FIXTURE_ROOT / kernel / "compatibility.jsonl"
        assert path.read_bytes() == (REPO_ROOT / entry["path"]).read_bytes()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        records = read_jsonl(path)
        assert len(records) == entry["records"]
        assert max(record.cycle for record in records) + 1 == expected_cycles
        assert max(record.cycle for record in records) + 1 == entry["cycles"]


def test_matadd_first_fetch_cycle_matches_rtl_fixture():
    records = read_jsonl(FIXTURE_ROOT / "matadd" / "compatibility.jsonl")
    first_fetch = min(record.cycle for record in records if record.core_state == "FETCH")
    assert first_fetch == 2

