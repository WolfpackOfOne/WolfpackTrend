# Parity Verification Tools

Tools for verifying that code refactors produce identical backtest results. Located in `tools/parity/`.

## Overview

The parity system compares backtest statistics from the QC API rather than ObjectStore CSVs (which require an Institutional account). It checks **27 summary statistics** and **41 trade statistics** for exact or near-exact match.

## Tools

### fetch_backtest_stats.py

Fetches backtest statistics from the QuantConnect API.

```bash
python tools/parity/fetch_backtest_stats.py \
    --project-id 27898063 \
    --backtest-id <BACKTEST_ID> \
    --output backtests/atomic_refactor/phase_XX/metrics/summary.json
```

- Uses timestamped SHA256 hash authentication with credentials from `~/.lean/credentials`
- Saves full statistics JSON including summary stats and trade statistics

### compare_metrics.py

Compares baseline metrics against a candidate backtest.

```bash
python tools/parity/compare_metrics.py \
    --baseline backtests/atomic_refactor/phase_00_baseline/metrics/summary.json \
    --candidate backtests/atomic_refactor/phase_XX/metrics/summary.json \
    --mode exact
```

Modes:
- `exact` - All metrics must match exactly (string comparison)
- `tolerant` - Allows small floating-point differences (1e-6 relative tolerance)

### run_phase_gate.sh

End-to-end convenience script for a full phase gate check.

```bash
./tools/parity/run_phase_gate.sh <phase_number> <phase_name>
# Example:
./tools/parity/run_phase_gate.sh 07 execution_wiring
```

Steps performed:
1. Compile check (all `.py` files)
2. Create artifact directories
3. Push to QC cloud and run backtest
4. Fetch statistics from API
5. Compare against baseline

## Baseline

The baseline backtest was captured at the start of the atomic refactor:

| Metric | Value |
|--------|-------|
| Backtest ID | `fb9ff158c10c66a59070e184dcdcba13` |
| End Equity | $78,854.70 |
| Net Profit | -21.145% |
| Total Orders | 8,203 |
| Total Fees | $5,445.59 |
| Sharpe Ratio | -1.534 |
| Max Drawdown | 23.600% |

Baseline metrics are stored in `backtests/atomic_refactor/phase_00_baseline/metrics/summary.json`.

## Verified Phases

All phases passed exact parity. See `backtests/atomic_refactor/progress.md` for the full tracking table with backtest IDs.

| Phase | Backtest ID |
|-------|-------------|
| P00 Baseline | `fb9ff158c10c66a59070e184dcdcba13` |
| P07 Execution Wiring | `8fda2fc0aef4e225f4480c31c666e13e` |
| P08 Logger Domain | `369edec8e9109f5882368df8d31a153b` |
| P11 Execution Domain | `c48c6d42a68d8c68fae345924dd30b3d` |
| P15 Final Certification | `dee508a69ce4b03bbde65e46f2f5f9ee` |

## QC API Authentication

The fetch script authenticates using:
- User ID and API token from `~/.lean/credentials`
- Timestamp-based SHA256 hash: `SHA256(apiToken + timestamp)`
- Basic auth header: `base64(userId:hash)`

Project ID: `27898063`
