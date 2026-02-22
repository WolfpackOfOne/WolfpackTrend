#!/usr/bin/env python3
"""Compare baseline and candidate backtest metrics for parity checking.

Modes:
    --mode exact:    All statistics must match exactly (string equality).
    --mode tolerant: Numeric values compared within tolerance; strings must match exactly.

Usage:
    python tools/parity/compare_metrics.py \
        --baseline backtests/atomic_refactor/phase_00_baseline/metrics/summary.json \
        --candidate backtests/atomic_refactor/phase_XX_name/metrics/summary.json \
        --mode tolerant
"""
import argparse
import json
import re
import sys


# Fields that must always match exactly (no tolerance)
EXACT_FIELDS = {
    "Total Orders",
    "Start Equity",
    "Lowest Capacity Asset",
    "Drawdown Recovery",
}

# Numeric tolerance for tolerant mode
TOLERANCES = {
    "default": 1e-6,
    "End Equity": 0.01,         # $0.01
    "Net Profit": 1e-4,         # 0.01% (displayed as percentage string)
    "Compounding Annual Return": 1e-4,
    "Drawdown": 1e-4,
    "Sharpe Ratio": 1e-4,
    "Sortino Ratio": 1e-4,
    "Alpha": 1e-4,
    "Beta": 1e-4,
    "Annual Standard Deviation": 1e-4,
    "Annual Variance": 1e-6,
    "Information Ratio": 1e-4,
    "Tracking Error": 1e-4,
    "Treynor Ratio": 1e-4,
    "Portfolio Turnover": 1e-4,
    "Total Fees": 0.01,
}


def parse_numeric(value):
    """Extract numeric value from QC statistics string (e.g., '$5445.59', '-21.145%', '0.012%')."""
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    s = s.replace("$", "").replace("%", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def compare_statistics(baseline_stats, candidate_stats, mode):
    """Compare two statistics dicts. Returns (passed, results)."""
    results = []
    all_keys = sorted(set(list(baseline_stats.keys()) + list(candidate_stats.keys())))
    passed = True

    for key in all_keys:
        b_val = baseline_stats.get(key)
        c_val = candidate_stats.get(key)

        if b_val is None and c_val is not None:
            results.append(("FAIL", key, f"missing in baseline, present in candidate: {c_val}"))
            passed = False
            continue
        if c_val is None and b_val is not None:
            results.append(("FAIL", key, f"present in baseline ({b_val}), missing in candidate"))
            passed = False
            continue

        if mode == "exact" or key in EXACT_FIELDS:
            if str(b_val) == str(c_val):
                results.append(("PASS", key, f"{b_val}"))
            else:
                results.append(("FAIL", key, f"baseline={b_val}, candidate={c_val}"))
                passed = False
        else:
            # Tolerant mode: try numeric comparison
            b_num = parse_numeric(b_val)
            c_num = parse_numeric(c_val)
            if b_num is not None and c_num is not None:
                tol = TOLERANCES.get(key, TOLERANCES["default"])
                diff = abs(b_num - c_num)
                if diff <= tol:
                    results.append(("PASS", key, f"{b_val} (diff={diff:.2e}, tol={tol})"))
                else:
                    results.append(("FAIL", key, f"baseline={b_val}, candidate={c_val}, diff={diff:.2e}, tol={tol}"))
                    passed = False
            else:
                # String comparison for non-numeric
                if str(b_val) == str(c_val):
                    results.append(("PASS", key, f"{b_val}"))
                else:
                    results.append(("FAIL", key, f"baseline={b_val}, candidate={c_val}"))
                    passed = False

    return passed, results


def compare_trade_statistics(baseline_ts, candidate_ts, mode):
    """Compare totalPerformance.tradeStatistics dicts."""
    results = []
    all_keys = sorted(set(list(baseline_ts.keys()) + list(candidate_ts.keys())))
    passed = True

    for key in all_keys:
        b_val = baseline_ts.get(key)
        c_val = candidate_ts.get(key)

        if b_val is None or c_val is None:
            if b_val != c_val:
                results.append(("FAIL", f"trade.{key}", f"baseline={b_val}, candidate={c_val}"))
                passed = False
            continue

        if mode == "exact":
            if str(b_val) == str(c_val):
                results.append(("PASS", f"trade.{key}", f"{b_val}"))
            else:
                results.append(("FAIL", f"trade.{key}", f"baseline={b_val}, candidate={c_val}"))
                passed = False
        else:
            b_num = parse_numeric(b_val)
            c_num = parse_numeric(c_val)
            if b_num is not None and c_num is not None:
                tol = 1e-4
                diff = abs(b_num - c_num)
                if diff <= tol:
                    results.append(("PASS", f"trade.{key}", f"{b_val}"))
                else:
                    results.append(("FAIL", f"trade.{key}", f"baseline={b_val}, candidate={c_val}, diff={diff:.2e}"))
                    passed = False
            else:
                if str(b_val) == str(c_val):
                    results.append(("PASS", f"trade.{key}", f"{b_val}"))
                else:
                    results.append(("FAIL", f"trade.{key}", f"baseline={b_val}, candidate={c_val}"))
                    passed = False

    return passed, results


def main():
    parser = argparse.ArgumentParser(description="Compare backtest metrics for parity")
    parser.add_argument("--baseline", required=True, help="Path to baseline summary.json")
    parser.add_argument("--candidate", required=True, help="Path to candidate summary.json")
    parser.add_argument("--mode", choices=["exact", "tolerant"], default="tolerant")
    args = parser.parse_args()

    with open(args.baseline) as f:
        baseline = json.load(f)
    with open(args.candidate) as f:
        candidate = json.load(f)

    print(f"Parity Check: {args.mode} mode")
    print(f"  Baseline:  {baseline.get('backtest_name', 'unknown')}")
    print(f"  Candidate: {candidate.get('backtest_name', 'unknown')}")
    print()

    overall_pass = True

    # Compare top-level statistics
    print("=== Statistics ===")
    stats_pass, stats_results = compare_statistics(
        baseline.get("statistics", {}),
        candidate.get("statistics", {}),
        args.mode,
    )
    for status, key, detail in stats_results:
        marker = "  " if status == "PASS" else ">>"
        print(f"  {marker} [{status}] {key}: {detail}")
    if not stats_pass:
        overall_pass = False
    print()

    # Compare trade statistics if available
    b_tp = baseline.get("total_performance", {}).get("trade_statistics", {})
    c_tp = candidate.get("total_performance", {}).get("trade_statistics", {})
    if b_tp or c_tp:
        print("=== Trade Statistics ===")
        ts_pass, ts_results = compare_trade_statistics(b_tp, c_tp, args.mode)
        fails = [r for r in ts_results if r[0] == "FAIL"]
        passes = [r for r in ts_results if r[0] == "PASS"]
        print(f"  {len(passes)} passed, {len(fails)} failed")
        for status, key, detail in fails:
            print(f"  >> [FAIL] {key}: {detail}")
        if not ts_pass:
            overall_pass = False
        print()

    # Compare tradeable dates
    b_dates = baseline.get("tradeable_dates")
    c_dates = candidate.get("tradeable_dates")
    if b_dates is not None and c_dates is not None:
        if b_dates == c_dates:
            print(f"=== Tradeable Dates: PASS ({b_dates}) ===")
        else:
            print(f"=== Tradeable Dates: FAIL (baseline={b_dates}, candidate={c_dates}) ===")
            overall_pass = False
        print()

    # Final verdict
    if overall_pass:
        print("RESULT: PASS - All parity checks passed")
        sys.exit(0)
    else:
        print("RESULT: FAIL - Parity check failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
