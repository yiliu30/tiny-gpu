#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

mkdir -p build test/logs
LOG_DIR="${TINY_GPU_LOG_DIR:-test/logs}"

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required to detect stale fixtures" >&2
  exit 1
fi

GIT=(git -c safe.directory="$REPO_ROOT")

for log in \
  matadd_compatibility.txt \
  matmul_compatibility.txt \
  partial_compatibility.txt \
  matadd_full.txt \
  matmul_full.txt; do
  : > "$LOG_DIR/$log"
done

TINY_GPU_LOG_FILE="$LOG_DIR/matadd_compatibility.txt" make test_matadd
TINY_GPU_LOG_FILE="$LOG_DIR/matmul_compatibility.txt" make test_matmul
TINY_GPU_LOG_FILE="$LOG_DIR/partial_compatibility.txt" make test_partial_block
TINY_GPU_FULL_TRACE=1 TINY_GPU_LOG_FILE="$LOG_DIR/matadd_full.txt" make test_matadd
TINY_GPU_FULL_TRACE=1 TINY_GPU_LOG_FILE="$LOG_DIR/matmul_full.txt" make test_matmul

python3 test/generate_trace_fixtures.py \
  --matadd-log "$LOG_DIR/matadd_compatibility.txt" \
  --matmul-log "$LOG_DIR/matmul_compatibility.txt" \
  --matadd-full-log "$LOG_DIR/matadd_full.txt" \
  --matmul-full-log "$LOG_DIR/matmul_full.txt" \
  --partial-log "$LOG_DIR/partial_compatibility.txt"

FIXTURE_STATUS="$("${GIT[@]}" status --porcelain -- test/fixtures/traces/02b6c2c)"
if [[ -n "$FIXTURE_STATUS" ]]; then
  "${GIT[@]}" diff -- test/fixtures/traces/02b6c2c
  echo "ERROR: Verilog-generated fixtures differ from committed fixtures" >&2
  exit 1
fi

python3 test/verify_differential_failure.py

(
  cd python
  python3 -m pytest -q
)
