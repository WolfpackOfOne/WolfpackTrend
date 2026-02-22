#!/bin/bash
# Run a full phase gate check: compile, push, backtest, fetch stats, compare.
#
# Usage:
#   QC_PROJECT_NAME="<qc-project-name>" QC_PROJECT_ID="<qc-project-id>" \
#     ./tools/parity/run_phase_gate.sh <phase_number> <phase_name>
#   Example:
#   QC_PROJECT_NAME="My QC Project" QC_PROJECT_ID="12345678" \
#     ./tools/parity/run_phase_gate.sh 02 structure_atoms

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PHASE_NUM="${1:?Usage: run_phase_gate.sh <phase_number> <phase_name>}"
PHASE_NAME="${2:?Usage: run_phase_gate.sh <phase_number> <phase_name>}"

QC_ROOT_DIR="${QC_ROOT_DIR:-$HOME/Documents/QuantConnect}"
QC_PROJECT_NAME="${QC_PROJECT_NAME:?Set QC_PROJECT_NAME to your QuantConnect project name}"
QC_PROJECT_ID="${QC_PROJECT_ID:?Set QC_PROJECT_ID to your QuantConnect cloud-id}"

PHASE_DIR="${PROJECT_DIR}/backtests/atomic_refactor/phase_${PHASE_NUM}_${PHASE_NAME}"
BASELINE_SUMMARY="${PROJECT_DIR}/backtests/atomic_refactor/phase_00_baseline/metrics/summary.json"

echo "=== Phase ${PHASE_NUM}: ${PHASE_NAME} ==="
echo ""

# Step 1: Compile check
echo ">>> Step 1: Compile check"
cd "${PROJECT_DIR}"
python -m py_compile main.py
for f in models/*.py; do python -m py_compile "$f"; done
# Compile new domain modules if they exist
for dir in core signals risk execution loggers; do
    if [ -d "$dir" ]; then
        for f in "$dir"/*.py; do python -m py_compile "$f"; done
    fi
done
if [ -d "tools/parity" ]; then
    for f in tools/parity/*.py; do python -m py_compile "$f"; done
fi
echo "  Compile: OK"
echo ""

# Step 2: Create artifact directories
echo ">>> Step 2: Create artifact directories"
mkdir -p "${PHASE_DIR}/metrics"
echo "  Directories: OK"
echo ""

# Step 3: Push and run cloud backtest
echo ">>> Step 3: Push to cloud and run backtest"
cd "${QC_ROOT_DIR}"
source venv/bin/activate
cd MyProjects
lean cloud push --project "${QC_PROJECT_NAME}" --force
BACKTEST_NAME="Atomic-P${PHASE_NUM}-${PHASE_NAME}-$(date +%Y%m%d-%H%M%S)"
OUTPUT=$(lean cloud backtest "${QC_PROJECT_NAME}" --name "${BACKTEST_NAME}" 2>&1)
echo "${OUTPUT}"

# Extract backtest ID from output
BACKTEST_ID=$(echo "${OUTPUT}" | grep "Backtest id:" | awk '{print $NF}')
if [ -z "${BACKTEST_ID}" ]; then
    echo "ERROR: Could not extract backtest ID"
    exit 1
fi
echo "  Backtest ID: ${BACKTEST_ID}"
echo ""

# Step 4: Fetch stats from API
echo ">>> Step 4: Fetch backtest statistics"
cd "${PROJECT_DIR}"
python tools/parity/fetch_backtest_stats.py \
    --project-id "${QC_PROJECT_ID}" \
    --backtest-id "${BACKTEST_ID}" \
    --output "${PHASE_DIR}/metrics/summary.json"
echo ""

# Step 5: Compare to baseline
echo ">>> Step 5: Parity comparison (tolerant mode)"
python tools/parity/compare_metrics.py \
    --baseline "${BASELINE_SUMMARY}" \
    --candidate "${PHASE_DIR}/metrics/summary.json" \
    --mode tolerant

echo ""
echo "=== Phase ${PHASE_NUM} gate complete ==="
