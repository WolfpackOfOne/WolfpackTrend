# WolfpackTrend - Dow 30 Trend-Following Strategy

## Project Overview

A modular trend-following strategy using the Dow 30 stocks, implemented with LEAN's framework architecture:

- **Alpha Model**: Composite trend signals from 3 horizons (20/63/252 day SMAs), normalized by ATR
- **Portfolio Construction**: Targets 10% annualized volatility with exposure constraints
- **Execution**: Market orders via ImmediateExecutionModel
- **Logging**: Daily metrics saved to ObjectStore for research analysis

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
│   └── logger.py           # PortfolioLogger (ObjectStore integration)
└── claude.md               # This file
```

## Strategy Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| SMA Short | 20 days | Short-term trend |
| SMA Medium | 63 days | Medium-term trend |
| SMA Long | 252 days | Long-term trend |
| ATR Period | 14 days | Volatility normalization |
| Signal Weights | 0.5/0.3/0.2 | Short/Medium/Long |
| Target Vol | 10% annual | Portfolio volatility target |
| Max Gross | 150% | Maximum gross exposure |
| Max Net | 50% | Maximum absolute net exposure |
| Max Per-Name | 10% | Maximum single stock weight |
| Min Signal | 0.05 | Skip signals below this magnitude |

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

## Backtest Configuration

Current settings in `main.py`:
- **Start Date**: 2022-01-01
- **End Date**: 2024-01-01
- **Starting Cash**: $100,000
- **Warmup**: 252 days (for SMA252)
- **Benchmark**: SPY

## Key Implementation Notes

1. **Signal Generation**: Signals are computed once per day using `tanh(composite_score)` for smooth bounded magnitude in (-1, +1)

2. **Volatility Targeting**: Uses diagonal approximation (ignores correlations) with 63-day rolling returns

3. **Constraint Order**: Per-name cap → Gross cap → Net cap (order matters)

4. **Slippage Tracking**: Compares price at signal generation vs actual fill price

5. **No History Calls**: Rolling returns maintained incrementally to avoid performance issues

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
