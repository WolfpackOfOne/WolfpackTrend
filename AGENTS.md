# WolfpackTrend Agent Instructions

This file defines repository-specific instructions for coding agents working in this project.

## Project Summary
- Strategy: modular trend-following equity strategy built on LEAN.
- Universe: static ticker list in `shared/universe.py` (`EQUITY_UNIVERSE`, currently 30 names), re-exported via `models/universe.py`.
- Entrypoint: `main.py` (`WolfpackTrendAlgorithm`).
- Lean engine path: `$HOME/Documents/QuantConnect/Lean/Algorithm`.

## Architecture
- `main.py`: algorithm setup, model wiring, scheduled stale-order cancellation, event logging.
- `signals/alpha.py`: `CompositeTrendAlphaModel` (20/63/252 SMA composite trend, ATR normalization).
- `risk/portfolio.py`: `TargetVolPortfolioConstructionModel` (10% vol targeting, constraints, 5-day scaling).
- `execution/execution.py`: `SignalStrengthExecutionModel` (signal-tiered limit logic + stale cancellation).
- `loggers/portfolio_logger.py`: `PortfolioLogger` writing CSV data to ObjectStore.
- `models/*.py`: compatibility adapters that re-export domain modules for framework-facing imports.

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
- `<TEAM_ID>/daily_snapshots.csv`
- `<TEAM_ID>/positions.csv`
- `<TEAM_ID>/signals.csv`
- `<TEAM_ID>/slippage.csv`
- `<TEAM_ID>/trades.csv`
- `<TEAM_ID>/targets.csv`
- `<TEAM_ID>/order_events.csv`

## Development Workflow
Use QuantConnect cloud for authoritative backtests.

```bash
cd ~/Documents/QuantConnect
source venv/bin/activate
cd MyProjects
lean cloud push --project "<qc-project-name>" --force
lean cloud backtest "<qc-project-name>" --name "<run name>"
```

If needed, sync from cloud:

```bash
lean cloud pull --project "<qc-project-name>"
```

## Verification Expectations
For code changes, run lightweight local validation before handing off:

```bash
python -m py_compile main.py
for f in models/*.py core/*.py signals/*.py risk/*.py execution/*.py loggers/*.py shared/*.py templates/*.py; do
    python -m py_compile "$f"
done
```

Then provide a cloud backtest command (or run one if requested).

## Git And File Hygiene
- Repo: `https://github.com/<your-org>/<your-repo>.git` (branch `main`).
- Do not commit secrets or environment-specific artifacts.
- Keep `config.json`, `backtests/`, `live/`, `.lean/`, and cache/log artifacts untracked.
- Prefer focused commits that align with one logical strategy or infrastructure change.

## Scope Guidance For Agents
- Preserve modular separation between alpha, portfolio construction, execution, and logging.
- Avoid changing core parameters, universe membership, or ObjectStore schema unless explicitly asked.
- When modifying execution/scaling logic, check downstream effects in both `risk/portfolio.py` and `execution/execution.py` (and keep `models/` adapters consistent).
- Keep research notebooks/docs aligned if behavior or output columns change.
