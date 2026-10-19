#!/usr/bin/env python3
"""Generate deterministic canonical trace fixtures from RTL text logs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

try:
    from .rtl_trace import records_from_log
except ImportError:
    from rtl_trace import records_from_log

from tiny_gpu.trace import write_jsonl


DEFAULT_OUTPUT = REPO_ROOT / "test" / "fixtures" / "traces" / "02b6c2c"
RTL_COMMIT = "02b6c2c"


def _manifest_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fixture_entry(
    *,
    source_log: Path,
    output: Path,
    mode: str,
    description: str,
    records,
) -> dict[str, object]:
    """Build one manifest entry describing a generated trace fixture."""

    return {
        "path": _manifest_path(output),
        "mode": mode,
        "description": description,
        "cycles": max(record.cycle for record in records) + 1,
        "records": len(records),
        "lanes": sorted({record.lane for record in records}),
        "sha256": _sha256(output),
        "source_log": source_log.name,
        "source_log_sha256": _sha256(source_log),
    }


def generate(
    *,
    matadd_log: Path,
    matmul_log: Path,
    matadd_full_log: Path | None = None,
    matmul_full_log: Path | None = None,
    partial_log: Path | None = None,
    output_dir: Path = DEFAULT_OUTPUT,
) -> dict[str, object]:
    """Normalize Verilog logs into fixtures and return the generated manifest."""

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "rtl_commit": RTL_COMMIT,
        "generator": "test/generate_trace_fixtures.py",
        "fixtures": {},
    }

    for kernel, source_log, description in (
        (
            "matadd",
            matadd_log,
            "Compatibility log: all enabled lanes, cycles 0-177",
        ),
        (
            "matmul",
            matmul_log,
            "Compatibility log: testbench-filtered global thread 1, cycles 0-490",
        ),
    ):
        records = records_from_log(source_log)
        output = output_dir / kernel / "compatibility.jsonl"
        write_jsonl(output, records)
        manifest["fixtures"][kernel] = {
            "compatibility": _fixture_entry(
                source_log=source_log,
                output=output,
                mode="compatibility",
                description=description,
                records=records,
            )
        }

    for kernel, source_log, description in (
        (
            "matadd",
            matadd_full_log,
            "Full log: every enabled lane and architectural state, cycles 0-177",
        ),
        (
            "matmul",
            matmul_full_log,
            "Full log: every enabled lane and architectural state, cycles 0-490",
        ),
    ):
        if source_log is None:
            continue
        records = records_from_log(source_log)
        output = output_dir / kernel / "full.jsonl"
        output.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl(output, records)
        manifest["fixtures"][kernel]["full"] = _fixture_entry(
            source_log=source_log,
            output=output,
            mode="full",
            description=description,
            records=records,
        )

    if partial_log is not None:
        records = records_from_log(partial_log)
        output = output_dir / "partial" / "compatibility.jsonl"
        write_jsonl(output, records)
        manifest["fixtures"]["partial"] = {
            "compatibility": _fixture_entry(
                source_log=partial_log,
                output=output,
                mode="compatibility",
                description=(
                    "Compatibility log: bounded five-thread final block; "
                    "one active lane in the second block"
                ),
                records=records,
            )
        }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    """Generate trace fixtures from the two command-line log paths."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matadd-log", type=Path, required=True)
    parser.add_argument("--matmul-log", type=Path, required=True)
    parser.add_argument("--matadd-full-log", type=Path)
    parser.add_argument("--matmul-full-log", type=Path)
    parser.add_argument("--partial-log", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    manifest = generate(
        matadd_log=args.matadd_log,
        matmul_log=args.matmul_log,
        matadd_full_log=args.matadd_full_log,
        matmul_full_log=args.matmul_full_log,
        partial_log=args.partial_log,
        output_dir=args.output_dir,
    )
    print(f"Wrote {args.output_dir / 'manifest.json'}")
    for kernel, entry in manifest["fixtures"].items():
        for mode, fixture in entry.items():
            print(
                f"  {kernel}/{mode}: {fixture['cycles']} cycles, "
                f"{fixture['records']} records"
            )


if __name__ == "__main__":
    main()
