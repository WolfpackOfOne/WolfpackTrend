# WolfpackTrend Agent Instructions

This file defines repository-specific instructions for coding agents working in this project.

## Project Summary
- Strategy: modular trend-following equity strategy built on LEAN.
- Universe: static ticker list in `models/universe.py` (`DOW30`, currently 30 names).
- Entrypoint: `main.py` (`Dow30TrendAlgorithm`).
- Lean engine path: `/Users/graham/Documents/QuantConnect/Lean/Algorithm`.

## Architecture
- `main.py`: algorithm setup, model wiring, scheduled stale-order cancellation, event logging.
- `models/alpha.py`: `CompositeTrendAlphaModel` (20/63/252 SMA composite trend, ATR normalization).
- `models/portfolio.py`: `TargetVolPortfolioConstructionModel` (10% vol targeting, constraints, 5-day scaling).
- `models/execution.py`: `SignalStrengthExecutionModel` (signal-tiered limit logic + stale cancellation).
- `models/logger.py`: `PortfolioLogger` writing CSV data to ObjectStore.

## Strategy Invariants
- Signal model uses 3 horizons (20/63/252 SMA) with ATR normalization and `tanh(score / 3.0)`.
- New directional signal only when all trend horizons agree (all bullish or all bearish).
- Signals are recalculated every 5 trading days, then emitted daily for scaling.
- Portfolio targets 10% annualized volatility with constraint order:
  1. Per-name cap
  2. Gross cap
  3. Net cap
- Scaling runs across 5 trading days and must remain trading-day-based (not calendar-day-based).
- Execution tiers:
  - Strong (`>= 0.70`): limit at market price
  - Moderate (`>= 0.30`): limit with 0.5% offset
  - Weak (`< 0.30`): limit with 1.5% offset
- Exits use market orders.
- Stale order cancellation must preserve `week_id` cycle behavior, with legacy fallback checks only when `week_id` is unavailable.

## Backtest Defaults (Current)
- Start date: `2022-01-01`
- End date: `2024-01-01`
- Starting cash: `$100,000`
- Warmup: `252` days
- Benchmark: `SPY`

## ObjectStore Outputs
Keep these keys stable unless a migration is explicitly requested:
- `wolfpack/daily_snapshots.csv`
- `wolfpack/positions.csv`
- `wolfpack/signals.csv`
- `wolfpack/slippage.csv`
- `wolfpack/trades.csv`
- `wolfpack/targets.csv`
- `wolfpack/order_events.csv`

## Development Workflow
Use QuantConnect cloud for authoritative backtests.

```bash
cd ~/Documents/QuantConnect
source venv/bin/activate
cd MyProjects
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "<run name>"
```

If needed, sync from cloud:

```bash
lean cloud pull --project "WolfpackTrend 1"
```

## Verification Expectations
For code changes, run lightweight local validation before handing off:

```bash
python -m py_compile main.py models/*.py
```

Then provide a cloud backtest command (or run one if requested).

## Git And File Hygiene
- Repo: `https://github.com/WolfpackOfOne/WolfpackTrend.git` (branch `main`).
- Do not commit secrets or environment-specific artifacts.
- Keep `config.json`, `backtests/`, `live/`, `.lean/`, and cache/log artifacts untracked.
- Prefer focused commits that align with one logical strategy or infrastructure change.

## Scope Guidance For Agents
- Preserve modular separation between alpha, portfolio construction, execution, and logging.
- Avoid changing core parameters, universe membership, or ObjectStore schema unless explicitly asked.
- When modifying execution/scaling logic, check downstream effects in both `models/portfolio.py` and `models/execution.py`.
- Keep research notebooks/docs aligned if behavior or output columns change.
