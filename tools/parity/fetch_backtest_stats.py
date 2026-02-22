#!/usr/bin/env python3
"""Fetch backtest statistics from QuantConnect API and save as summary JSON.

Usage:
    python tools/parity/fetch_backtest_stats.py \
        --project-id <qc-project-id> \
        --backtest-id <id> \
        --output backtests/atomic_refactor/phase_XX_name/metrics/summary.json
"""
import argparse
import base64
import hashlib
import json
import os
import sys
import time

import requests


def get_credentials():
    cred_path = os.path.expanduser("~/.lean/credentials")
    with open(cred_path) as f:
        return json.load(f)


def get_headers(user_id, api_token):
    timestamp = str(int(time.time()))
    token_hash = hashlib.sha256(f"{api_token}:{timestamp}".encode()).hexdigest()
    auth_str = base64.b64encode(f"{user_id}:{token_hash}".encode()).decode()
    return {"Authorization": f"Basic {auth_str}", "Timestamp": timestamp}


def fetch_backtest(project_id, backtest_id):
    creds = get_credentials()
    headers = get_headers(creds["user-id"], creds["api-token"])
    resp = requests.post(
        "https://www.quantconnect.com/api/v2/backtests/read",
        headers=headers,
        json={"projectId": project_id, "backtestId": backtest_id},
    )
    data = resp.json()
    if not data.get("success"):
        print(f"API error: {data.get('errors')}", file=sys.stderr)
        sys.exit(1)
    return data["backtest"]


def extract_summary(bt):
    summary = {
        "backtest_id": bt["backtestId"],
        "backtest_name": bt["name"],
        "project_id": bt["projectId"],
        "created": bt["created"],
        "backtest_start": bt["backtestStart"],
        "backtest_end": bt["backtestEnd"],
        "tradeable_dates": bt["tradeableDates"],
        "statistics": bt["statistics"],
    }
    tp = bt.get("totalPerformance", {})
    if tp:
        summary["total_performance"] = {
            "trade_statistics": tp.get("tradeStatistics", {}),
            "portfolio_statistics": tp.get("portfolioStatistics", {}),
        }
    return summary


def main():
    parser = argparse.ArgumentParser(description="Fetch backtest stats from QC API")
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--backtest-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    bt = fetch_backtest(args.project_id, args.backtest_id)
    summary = extract_summary(bt)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)

    print(f"Saved summary to {args.output}")
    stats = summary["statistics"]
    print(f"  End Equity: {stats.get('End Equity')}")
    print(f"  Net Profit: {stats.get('Net Profit')}")
    print(f"  Total Orders: {stats.get('Total Orders')}")
    print(f"  Total Fees: {stats.get('Total Fees')}")
    print(f"  Sharpe: {stats.get('Sharpe Ratio')}")
    print(f"  Drawdown: {stats.get('Drawdown')}")


if __name__ == "__main__":
    main()
