# WolfpackTrend - Dow 30 Trend-Following Strategy

## Repository
- **GitHub URL:** https://github.com/WolfpackOfOne/WolfpackTrend.git
- **Default Branch:** main

## Project Overview

A modular trend-following strategy using the Dow 30 stocks, implemented with LEAN's framework architecture:

- **Alpha Model**: Composite trend signals from 3 horizons (20/63/252 day SMAs), normalized by ATR
- **Portfolio Construction**: Targets 10% annualized volatility with exposure constraints
- **Execution**: Signal-strength execution (strong=limit at market; moderate/weak=limit with 0.5%/1.5% offsets)
- **Logging**: Daily metrics saved to ObjectStore for research analysis
- **Lean Engine**: `/Users/graham/Documents/QuantConnect/Lean/Algorithm`

## Project Structure

```
WolfpackTrend 1/
├── main.py                 # Algorithm entrypoint
├── config.json             # QC cloud project config (DO NOT COMMIT)
├── models/
│   ├── __init__.py         # Exports all models
│   ├── universe.py         # DOW30 tickers list
│   ├── alpha.py            # CompositeTrendAlphaModel
│   ├── portfolio.py        # TargetVolPortfolioConstructionModel
│   ├── execution.py        # SignalStrengthExecutionModel
│   └── logger.py           # PortfolioLogger (ObjectStore integration)
└── claude.md               # This file
```

## Strategy Parameters

### Signal Generation (Alpha Model)

| Parameter | Value | Description |
|-----------|-------|-------------|
| SMA Short | 20 days | Short-term trend |
| SMA Medium | 63 days | Medium-term trend |
| SMA Long | 252 days | Long-term trend |
| ATR Period | 14 days | Volatility normalization |
| Signal Weights | 0.2/0.5/0.3 | Short/Medium/Long |
| Min Signal | 0.05 | Skip signals below this magnitude |
| Rebalance Interval | 5 trading days | Full signal recalculation frequency |

### Portfolio Construction

| Parameter | Value | Description |
|-----------|-------|-------------|
| Target Vol | 10% annual | Portfolio volatility target |
| Max Gross | 150% | Maximum gross exposure |
| Max Net | 50% | Maximum absolute net exposure |
| Max Per-Name | 10% | Maximum single stock weight |
| Scaling Days | 5 | Trading days to scale into full position |

### Execution (Signal-Strength Based)

| Parameter | Value | Description |
|-----------|-------|-------------|
| Strong Threshold | 0.70 | Signals >= this use limit orders at market price |
| Strong Offset | 0.0% | No offset = market price |
| Moderate Threshold | 0.30 | Signals >= this use 0.5% limit orders |
| Moderate Offset | 0.5% | Limit offset for moderate signals |
| Weak Offset | 1.5% | Limit offset for weak signals |
| Default Signal | 0.50 | Fallback for unknown symbols |
| Stale Limit Open Checks | 2 | Cancel an unfilled limit after 2 market-open checks |

### Scaling Schedules (Signal-Dependent)

Positions scale into weekly targets over 5 trading days:
- **Strong (>= 0.7)**: Front-loaded (sqrt curve) — ~45% on day 1
- **Moderate (0.3–0.7)**: Mild front-load — ~30% on day 1
- **Weak (< 0.3)**: Linear — 20% per day evenly

## LEAN CLI Commands

### Setup (Run Once Per Terminal Session)
```bash
cd ~/Documents/QuantConnect
source venv/bin/activate
cd MyProjects
```

### Push to Cloud
```bash
lean cloud push --project "WolfpackTrend 1"
```

If you get a collaboration lock error:
```bash
lean cloud push --project "WolfpackTrend 1" --force
```

### Run Cloud Backtest
```bash
lean cloud backtest "WolfpackTrend 1" --name "Description of this run"
```

### Pull from Cloud
```bash
lean cloud pull --project "WolfpackTrend 1"
```

### Full Workflow
```bash
cd ~/Documents/QuantConnect
source venv/bin/activate
cd MyProjects
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Test Run"
```

## ObjectStore Data

The strategy logs daily metrics to ObjectStore for research analysis:

### Files Created
| File | Description |
|------|-------------|
| `wolfpack/daily_snapshots.csv` | Daily NAV, exposure, P&L, volatility |
| `wolfpack/positions.csv` | All positions daily (~15k rows for 2 years) |
| `wolfpack/signals.csv` | Alpha signals with indicator values |
| `wolfpack/slippage.csv` | Per-order slippage (expected vs fill price) |

### Reading in Research Notebook
```python
from io import StringIO
import pandas as pd

# Read daily snapshots
snapshots_str = qb.ObjectStore.Read("wolfpack/daily_snapshots.csv")
df_snapshots = pd.read_csv(StringIO(snapshots_str), parse_dates=['date'])

# Read positions
positions_str = qb.ObjectStore.Read("wolfpack/positions.csv")
df_positions = pd.read_csv(StringIO(positions_str), parse_dates=['date'])

# Read signals
signals_str = qb.ObjectStore.Read("wolfpack/signals.csv")
df_signals = pd.read_csv(StringIO(signals_str), parse_dates=['date'])

# Read slippage
slippage_str = qb.ObjectStore.Read("wolfpack/slippage.csv")
df_slippage = pd.read_csv(StringIO(slippage_str), parse_dates=['date'])
```

### Daily Snapshots Columns
- `date` - Trading date
- `nav` - Total portfolio value
- `cash` - Available cash
- `gross_exposure` - (long + short) / nav
- `net_exposure` - (long - short) / nav
- `long_exposure` - Long value / nav
- `short_exposure` - Short value / nav
- `daily_pnl` - NAV change from previous day
- `cumulative_pnl` - NAV - starting cash
- `daily_slippage` - Sum of order slippage for the day
- `num_positions` - Count of active positions
- `estimated_vol` - Portfolio volatility estimate

### Positions Columns
- `date` - Trading date
- `symbol` - Ticker symbol
- `invested` - 1 if invested, 0 if flat
- `quantity` - Position quantity
- `price` - Last price
- `market_value` - Quantity * price
- `weight` - Market value / NAV
- `unrealized_pnl` - Current unrealized P&L
- `daily_pnl` - Daily unrealized P&L delta (legacy)
- `daily_unrealized_pnl` - Daily unrealized P&L delta
- `daily_realized_pnl` - Daily realized P&L delta (from `holding.Profit`)
- `daily_fees` - Daily fees delta (from `holding.TotalFees`)
- `daily_dividends` - Daily dividends delta (informational under Adjusted pricing; do not subtract from NAV reconciliation)
- `daily_total_net_pnl` - Daily realized + unrealized − fees
- `avg_price` - Average entry price

## Backtest Configuration

Current settings in `main.py`:
- **Start Date**: 2022-01-01
- **End Date**: 2024-01-01
- **Starting Cash**: $100,000
- **Warmup**: 252 days (for SMA252)
- **Benchmark**: SPY

## Key Implementation Notes

1. **Signal Generation**: Signals are computed every 5 trading days using `tanh(composite_score)` for smooth bounded magnitude in (-1, +1). Cached signals are re-emitted daily to drive the scaling pipeline.

2. **Daily Scaling**: Alpha emits daily (fresh or cached), PCM scales targets from 0% to 100% over 5 trading days. Strong signals scale faster (front-loaded), weak signals scale linearly.

3. **Signal-Strength Execution**: Strong signals (>=0.7) get limit orders at market price (0% offset). Moderate (0.3-0.7) get limit orders at 0.5% offset. Weak (<0.3) get limit orders at 1.5% offset. Exits always use market orders.

4. **Stale Order Cancellation**: Unfilled limit orders are reviewed via `Schedule.On` at market open; each order is cancelled only after 2 market-open checks so daily bars have time to fill.

5. **Volatility Targeting**: Uses diagonal approximation (ignores correlations) with 63-day rolling returns

6. **Constraint Order**: Per-name cap → Gross cap → Net cap (order matters)

7. **Slippage Tracking**: Compares price at signal generation vs actual fill price

8. **No History Calls**: Rolling returns maintained incrementally to avoid performance issues

9. **Trading-Day Counters**: Both rebalance interval and scaling use trading-day counters (not calendar days), ensuring 100% scaling is always reached before the next rebalance, even during holiday weeks.

## Common Issues

### "Cannot push - collaboration lock"
Use `--force` flag:
```bash
lean cloud push --project "WolfpackTrend 1" --force
```

### "lean: command not found"
Virtual environment not activated:
```bash
source ~/Documents/QuantConnect/venv/bin/activate
```

### Data not available locally
Use cloud backtest instead of local - cloud has full data access.

## Git Version Control

### Repository Information
- **GitHub URL:** https://github.com/WolfpackOfOne/WolfpackTrend.git
- **Repository Name:** WolfpackTrend
- **Default Branch:** main
- **Working Directory:** `/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1`

### Files Tracked in Git
- `main.py` - Main algorithm
- `models/*.py` - Alpha, portfolio, logger, universe modules
- `claude.md` - This documentation
- `.gitignore` - Ignore patterns

### Files NOT Tracked (in .gitignore)
- `config.json` - Contains QC organization/cloud IDs
- `backtests/` - Backtest results (regeneratable)
- `__pycache__/` - Python cache
- `.DS_Store` - macOS metadata

### Common Git Commands
```bash
# Check status
git status

# View recent commits
git log --oneline -10

# Stage and commit changes
git add .
git commit -m "Description of changes"

# Push to GitHub
git push

# Pull from GitHub
git pull
```

### Development Workflow
```bash
# 1. Pull latest from GitHub
cd "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1"
git pull

# 2. Make changes to algorithm

# 3. Test with QuantConnect cloud
cd ~/Documents/QuantConnect
source venv/bin/activate
cd MyProjects
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Test"

# 4. Commit if successful
cd "WolfpackTrend 1"
git add .
git commit -m "Describe your changes"
git push

# 5. Sync to QC cloud (already done in step 3)
```

### Syncing Between Systems
Three separate systems to keep in sync:

| System | Location | Sync Command |
|--------|----------|--------------|
| Local Git | `.git/` | `git push` / `git pull` |
| GitHub | WolfpackOfOne/WolfpackTrend | (via git) |
| QC Cloud | WolfpackTrend 1 project | `lean cloud push/pull` |

**Important:** Git and QC cloud are independent. Sync both if you want changes everywhere.
