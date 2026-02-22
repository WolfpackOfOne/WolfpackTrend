# Team Configuration Implementation Guide

This document explains how to convert the WolfpackTrend project from a single-user setup to a multi-team setup where every team runs **identical code** but writes to and reads from their own folder in QuantConnect's ObjectStore.

---

## Overview

**The Problem:** The current code hardcodes `"wolfpack/"` as the ObjectStore prefix everywhere. If 7 teams all run the same code, they overwrite each other's data.

**The Solution:** Create a single `config.py` file containing `TEAM_ID = "team_1"`. Every file that touches ObjectStore reads from this config. Each team changes only this one value.

**ObjectStore paths change from:**
```
wolfpack/daily_snapshots.csv
wolfpack/positions.csv
wolfpack/signals.csv
...
```

**To:**
```
team_1/daily_snapshots.csv
team_1/positions.csv
team_1/signals.csv
...
```

The production (master) version uses `TEAM_ID = "production"`.

### Non-Goals

This change does NOT touch strategy behavior:

- No changes to alpha logic
- No changes to portfolio/risk logic
- No changes to execution tiers or stale-order behavior
- No changes to CSV schema/columns

Only the ObjectStore key prefix changes.

---

## Step-by-Step Implementation

### Step 1: Create `config.py`

Create a new file called `config.py` in the project root (same level as `main.py`):

```python
# config.py
# -------------------------------------------------------
# Team Configuration
# -------------------------------------------------------
# Each team sets this to their team name. This controls
# where backtest CSVs are saved in ObjectStore and where
# research notebooks read from.
#
# Valid values:
#   "production"  - Master/instructor version
#   "team_1"      - Team 1
#   "team_2"      - Team 2
#   "team_3"      - Team 3
#   "team_4"      - Team 4
#   "team_5"      - Team 5
#   "team_6"      - Team 6
#   "team_7"      - Team 7
# -------------------------------------------------------
TEAM_ID = "production"
```

---

### Step 2: Update `main.py`

Three changes are needed in `main.py`:

#### 2a. Add the import (line 1)

**Current:**
```python
from AlgorithmImports import *
from models import EQUITY_UNIVERSE, CompositeTrendAlphaModel, TargetVolPortfolioConstructionModel, SignalStrengthExecutionModel, PortfolioLogger
```

**Change to:**
```python
from AlgorithmImports import *
from models import EQUITY_UNIVERSE, CompositeTrendAlphaModel, TargetVolPortfolioConstructionModel, SignalStrengthExecutionModel, PortfolioLogger
from config import TEAM_ID
```

#### 2b. Pass `TEAM_ID` to `PortfolioLogger` (line 36)

**Current:**
```python
self.logger = PortfolioLogger()
```

**Change to:**
```python
self.logger = PortfolioLogger(team_id=TEAM_ID)
```

#### 2c. Update the ObjectStore cleanup block (lines 38-53)

**Current:**
```python
# Clear ObjectStore to remove stale files from previous runs
if self.ObjectStore.ContainsKey("wolfpack/daily_snapshots.csv"):
    self.ObjectStore.Delete("wolfpack/daily_snapshots.csv")
if self.ObjectStore.ContainsKey("wolfpack/positions.csv"):
    self.ObjectStore.Delete("wolfpack/positions.csv")
if self.ObjectStore.ContainsKey("wolfpack/trades.csv"):
    self.ObjectStore.Delete("wolfpack/trades.csv")
if self.ObjectStore.ContainsKey("wolfpack/signals.csv"):
    self.ObjectStore.Delete("wolfpack/signals.csv")
if self.ObjectStore.ContainsKey("wolfpack/slippage.csv"):
    self.ObjectStore.Delete("wolfpack/slippage.csv")
if self.ObjectStore.ContainsKey("wolfpack/targets.csv"):
    self.ObjectStore.Delete("wolfpack/targets.csv")
if self.ObjectStore.ContainsKey("wolfpack/order_events.csv"):
    self.ObjectStore.Delete("wolfpack/order_events.csv")
self.Debug("ObjectStore: Cleared previous wolfpack data files")
```

**Change to:**
```python
# Clear ObjectStore to remove stale files from previous runs
_csv_files = [
    "daily_snapshots.csv", "positions.csv", "trades.csv",
    "signals.csv", "slippage.csv", "targets.csv", "order_events.csv"
]
for _f in _csv_files:
    _key = f"{TEAM_ID}/{_f}"
    if self.ObjectStore.ContainsKey(_key):
        self.ObjectStore.Delete(_key)
self.Debug(f"ObjectStore: Cleared previous {TEAM_ID}/ data files")
```

#### 2d. Add team context to initialization log

After the existing initialization log block, add TEAM_ID to the debug output so it's visible in every backtest log:

**Current:**
```python
self.Debug("=" * 60)
self.Debug("WOLFPACK TREND STRATEGY INITIALIZED")
self.Debug(f"Period: {self.StartDate.strftime('%Y-%m-%d')} to {self.EndDate.strftime('%Y-%m-%d')}")
self.Debug(f"Starting Cash: ${self.Portfolio.Cash:,.0f}")
self.Debug(f"Universe: {len(EQUITY_UNIVERSE)} stocks")
self.Debug("=" * 60)
```

**Change to:**
```python
self.Debug("=" * 60)
self.Debug("WOLFPACK TREND STRATEGY INITIALIZED")
self.Debug(f"Team: {TEAM_ID}")
self.Debug(f"Period: {self.StartDate.strftime('%Y-%m-%d')} to {self.EndDate.strftime('%Y-%m-%d')}")
self.Debug(f"Starting Cash: ${self.Portfolio.Cash:,.0f}")
self.Debug(f"Universe: {len(EQUITY_UNIVERSE)} stocks")
self.Debug("=" * 60)
```

This makes it immediately obvious which team a backtest belongs to.

---

### Step 3: Update `loggers/portfolio_logger.py`

The `PortfolioLogger` class needs to accept `team_id` and pass it down to every sub-logger.

#### 3a. Update `__init__` signature

**Current:**
```python
class PortfolioLogger:
    def __init__(self):
        self._snapshot_logger = SnapshotLogger()
        self._position_logger = PositionLogger()
        self._signal_logger = SignalLogger()
        self._slippage_logger = SlippageLogger()
        self._order_event_logger = OrderEventLogger()
        self._target_logger = TargetLogger()
```

**Change to:**
```python
class PortfolioLogger:
    def __init__(self, team_id="production"):
        self.team_id = team_id
        self._snapshot_logger = SnapshotLogger(team_id=team_id)
        self._position_logger = PositionLogger(team_id=team_id)
        self._signal_logger = SignalLogger(team_id=team_id)
        self._slippage_logger = SlippageLogger(team_id=team_id)
        self._order_event_logger = OrderEventLogger(team_id=team_id)
        self._target_logger = TargetLogger(team_id=team_id)
```

No other changes needed in this file.

---

### Step 4: Update all 6 sub-logger files

Every sub-logger needs the same two changes:
1. Accept `team_id` in `__init__`
2. Use `f"{self.team_id}/filename.csv"` in the `save()` method instead of `"wolfpack/filename.csv"`

#### 4a. `loggers/snapshot_logger.py`

**Current `__init__`:**
```python
class SnapshotLogger:
    def __init__(self):
        self.snapshots = []
```

**Change to:**
```python
class SnapshotLogger:
    def __init__(self, team_id="production"):
        self.team_id = team_id
        self.snapshots = []
```

**Current `save()`:**
```python
algorithm.ObjectStore.Save("wolfpack/daily_snapshots.csv", csv_content)
```

**Change to:**
```python
algorithm.ObjectStore.Save(f"{self.team_id}/daily_snapshots.csv", csv_content)
```

---

#### 4b. `loggers/position_logger.py`

**Current `__init__`:**
```python
class PositionLogger:
    def __init__(self):
        self.positions = []
        self.trades = []
        self.prev_positions = {}
        self.prev_symbol_totals = {}
```

**Change to:**
```python
class PositionLogger:
    def __init__(self, team_id="production"):
        self.team_id = team_id
        self.positions = []
        self.trades = []
        self.prev_positions = {}
        self.prev_symbol_totals = {}
```

**Current `save()` (two paths):**
```python
algorithm.ObjectStore.Save("wolfpack/positions.csv", csv_content)
```
```python
algorithm.ObjectStore.Save("wolfpack/trades.csv", csv_content)
```

**Change to:**
```python
algorithm.ObjectStore.Save(f"{self.team_id}/positions.csv", csv_content)
```
```python
algorithm.ObjectStore.Save(f"{self.team_id}/trades.csv", csv_content)
```

---

#### 4c. `loggers/signal_logger.py`

**Current `__init__`:**
```python
class SignalLogger:
    def __init__(self):
        self.signals = []
```

**Change to:**
```python
class SignalLogger:
    def __init__(self, team_id="production"):
        self.team_id = team_id
        self.signals = []
```

**Current `save()`:**
```python
algorithm.ObjectStore.Save("wolfpack/signals.csv", csv_content)
```

**Change to:**
```python
algorithm.ObjectStore.Save(f"{self.team_id}/signals.csv", csv_content)
```

---

#### 4d. `loggers/slippage_logger.py`

**Current `__init__`:**
```python
class SlippageLogger:
    def __init__(self):
        self.slippage = []
        self.daily_slippage = 0.0
        self.last_slippage_date = None
```

**Change to:**
```python
class SlippageLogger:
    def __init__(self, team_id="production"):
        self.team_id = team_id
        self.slippage = []
        self.daily_slippage = 0.0
        self.last_slippage_date = None
```

**Current `save()`:**
```python
algorithm.ObjectStore.Save("wolfpack/slippage.csv", csv_content)
```

**Change to:**
```python
algorithm.ObjectStore.Save(f"{self.team_id}/slippage.csv", csv_content)
```

---

#### 4e. `loggers/target_logger.py`

**Current `__init__`:**
```python
class TargetLogger:
    def __init__(self):
        self.targets = []
```

**Change to:**
```python
class TargetLogger:
    def __init__(self, team_id="production"):
        self.team_id = team_id
        self.targets = []
```

**Current `save()`:**
```python
algorithm.ObjectStore.Save("wolfpack/targets.csv", csv_content)
```

**Change to:**
```python
algorithm.ObjectStore.Save(f"{self.team_id}/targets.csv", csv_content)
```

---

#### 4f. `loggers/order_event_logger.py`

**Current `__init__`:**
```python
class OrderEventLogger:
    def __init__(self):
        self.order_events = []
```

**Change to:**
```python
class OrderEventLogger:
    def __init__(self, team_id="production"):
        self.team_id = team_id
        self.order_events = []
```

**Current `save()`:**
```python
algorithm.ObjectStore.Save("wolfpack/order_events.csv", csv_content)
```

**Change to:**
```python
algorithm.ObjectStore.Save(f"{self.team_id}/order_events.csv", csv_content)
```

---

### Step 5: Update Research Notebooks (28 notebooks)

All research notebooks need to read from `{TEAM_ID}/` instead of `wolfpack/`. There are 3 patterns across the notebooks.

**Important:** After changing `config.py`, students must **restart** the Research notebook kernel (`Kernel > Restart`) for the import to pick up the new value.

#### Pattern A: "Helper" notebooks (22 notebooks)

These notebooks define a `read_csv_from_store(key)` helper function and call it with hardcoded `"wolfpack/..."` paths.

**Notebooks using this pattern:**
- `research/position_monitor.ipynb`
- `research/slippage_analysis.ipynb`
- `research/pnl_attribution.ipynb`
- `research/risk/beta_vs_spy.ipynb`
- `research/risk/correlation_risk.ipynb`
- `research/risk/portfolio_volatility.ipynb`
- `research/exposure/01_concentration_risk.ipynb`
- `research/exposure/02_portfolio_vol_vs_target.ipynb`
- `research/exposure/03_exposure_regime_dashboard.ipynb`
- `research/signal/signal_distribution_dashboard.ipynb`
- `research/signal/signal_profitability_stats.ipynb`
- `research/signal/signal_tier_execution_quality.ipynb`
- `research/signal/signal_what_and_why.ipynb`
- `research/trading/daily_fill_aggressiveness.ipynb`
- `research/trading/order_lifecycle.ipynb`
- `research/trading/rebalance_week_health.ipynb`
- `research/trading/scaling_adherence.ipynb`
- `research/trading/stale_signal_risk.ipynb`
- `research/trading/weekly_execution_progress.ipynb`
- `research/trading/limit_spread_vs_fill.ipynb`
- `research/universe_selection/01_signal_evolution_by_equity.ipynb`
- `research/universe_selection/02_weekly_selection_diagnostics.ipynb`
- `research/universe_selection/03_symbol_stickiness_and_why.ipynb`

**Change required:** In the imports/setup cell (usually the first code cell), add:

```python
from config import TEAM_ID
```

Then change every call from:
```python
df = read_csv_from_store("wolfpack/positions.csv")
```
To:
```python
df = read_csv_from_store(f"{TEAM_ID}/positions.csv")
```

Do this for every `read_csv_from_store(...)` call in the notebook. The file names after the prefix stay the same (e.g., `positions.csv`, `daily_snapshots.csv`, etc.).

---

#### Pattern B: "Direct" notebooks (4 notebooks)

These notebooks call `qb.ObjectStore.Read("wolfpack/...")` directly without a helper function.

**Notebooks using this pattern:**
- `research/timeseries_plotter.ipynb`
- `research/performance_metrics.ipynb`
- `research/risk/risk_metrics.ipynb`
- `research/exposure/04_exposure_split_plots.ipynb`

**Change required:** In the imports/setup cell, add:

```python
from config import TEAM_ID
```

Then change every `ObjectStore.Read` call from:
```python
snapshots_str = qb.ObjectStore.Read("wolfpack/daily_snapshots.csv")
```
To:
```python
snapshots_str = qb.ObjectStore.Read(f"{TEAM_ID}/daily_snapshots.csv")
```

---

#### Pattern C: "Dict" notebook (1 notebook)

**Notebook:** `research/column_inspector.ipynb`

This notebook uses a dictionary to map friendly names to ObjectStore paths.

**Change required:** In the imports/setup cell, add:

```python
from config import TEAM_ID
```

Then change the dictionary from:
```python
DATA_FILES = {
    'daily_snapshots': 'wolfpack/daily_snapshots.csv',
    'positions': 'wolfpack/positions.csv',
    'signals': 'wolfpack/signals.csv',
    'slippage': 'wolfpack/slippage.csv'
}
```
To:
```python
DATA_FILES = {
    'daily_snapshots': f'{TEAM_ID}/daily_snapshots.csv',
    'positions': f'{TEAM_ID}/positions.csv',
    'signals': f'{TEAM_ID}/signals.csv',
    'slippage': f'{TEAM_ID}/slippage.csv'
}
```

---

## Complete File Change Summary

| File | What Changes |
|------|-------------|
| `config.py` | **NEW FILE** - Contains `TEAM_ID = "production"` |
| `main.py` | Add `from config import TEAM_ID`, pass to logger, update cleanup loop, log team context |
| `loggers/portfolio_logger.py` | Accept `team_id` param, pass to all sub-loggers |
| `loggers/snapshot_logger.py` | Accept `team_id` param, use in `save()` path |
| `loggers/position_logger.py` | Accept `team_id` param, use in `save()` paths (2 paths) |
| `loggers/signal_logger.py` | Accept `team_id` param, use in `save()` path |
| `loggers/slippage_logger.py` | Accept `team_id` param, use in `save()` path |
| `loggers/target_logger.py` | Accept `team_id` param, use in `save()` path |
| `loggers/order_event_logger.py` | Accept `team_id` param, use in `save()` path |
| 28 research notebooks | Add `from config import TEAM_ID`, use f-string in ObjectStore paths |

**Total: 37 files touched** (1 new + 8 Python files + 28 notebooks)

---

## What Students Do

When a team receives their copy of the project, they do exactly ONE thing:

1. Open `config.py`
2. Change `TEAM_ID = "production"` to `TEAM_ID = "team_3"` (or their team number)
3. Save the file

That's it. Everything else works automatically:
- Backtests write CSVs to `team_3/daily_snapshots.csv`, `team_3/positions.csv`, etc.
- Research notebooks read from the same `team_3/` folder
- No team's data overwrites another team's data

---

## ObjectStore Folder Structure (After All Teams Run)

```
ObjectStore/
├── production/
│   ├── daily_snapshots.csv
│   ├── positions.csv
│   ├── trades.csv
│   ├── signals.csv
│   ├── slippage.csv
│   ├── targets.csv
│   └── order_events.csv
├── team_1/
│   ├── daily_snapshots.csv
│   ├── positions.csv
│   └── ...
├── team_2/
│   └── ...
├── team_3/
│   └── ...
├── team_4/
│   └── ...
├── team_5/
│   └── ...
├── team_6/
│   └── ...
└── team_7/
    └── ...
```

---

## Verification Checklist

Use this to confirm the implementation is correct before distributing to teams.

### 1. Local compile sanity

Run from the project root to catch syntax errors:

```bash
python -m py_compile main.py
python -m py_compile config.py
python -m py_compile loggers/snapshot_logger.py loggers/position_logger.py loggers/signal_logger.py loggers/slippage_logger.py loggers/target_logger.py loggers/order_event_logger.py loggers/portfolio_logger.py
```

### 2. Grep audit — no remaining hardcoded paths

Run this to verify no `"wolfpack/"` strings remain in algorithm or notebook code:

```bash
rg -n '"wolfpack/' main.py loggers/ research/
```

This should return **zero results**. If any remain, they were missed during the update.

### 3. Cloud functional check (run once per project)

For the production project and at least one team project:

1. Push code: `lean cloud push --project "<qc-project-name>" --force`
2. Run a short backtest: `lean cloud backtest "<qc-project-name>" --name "Team config test"`
3. Confirm the backtest log shows: `Team: production` (or `Team: team_1`)
4. Confirm the log shows: `ObjectStore: Cleared previous production/ data files`
5. Open a research notebook and run the first cell — confirm it loads data without error

### 4. Isolation check

- Team 1's backtest must NOT clear or overwrite production keys
- Production's backtest must NOT clear or overwrite team keys
- Each project's cleanup loop only deletes keys under its own `TEAM_ID/` prefix

---

## Rollout Plan for Class

1. Implement all changes in the master code (Steps 1-5 above)
2. Set `TEAM_ID = "production"` in `config.py` and validate with a backtest
3. Push the same code to all 8 QC cloud projects
4. For each team project, edit `config.py` to the correct team ID (`team_1` through `team_7`)
5. Run one smoke backtest in each project to populate ObjectStore
6. Verify at least one notebook loads data correctly per project
7. Assign each team their project

---

## Common Pitfalls and Fixes

| Pitfall | Fix |
|---------|-----|
| Student forgets to change `config.py` | Data writes to `production/` — harmless if projects are isolated, but remind them to check the backtest log for `Team: production` |
| Notebook shows "key not found" after changing `config.py` | Restart the notebook kernel (`Kernel > Restart`) so the import picks up the new value |
| One notebook still hardcodes `wolfpack/...` | Run `rg -n "wolfpack/" research/` to find and fix it |
| Cleanup code deletes wrong team's keys | Impossible — the cleanup loop uses the same `TEAM_ID` from `config.py`, so it only deletes its own prefix |
| Typo in team ID (`Team1`, `team-1`, etc.) | Data writes to a nonstandard folder; notebooks can't find it. Students should use exactly `team_1` through `team_7` as shown in `config.py` comments |

---

## Important Notes for the Instructor

1. **QC Cloud projects are independent.** Each of the 8 QC projects has its own ObjectStore. Teams cannot accidentally overwrite each other even if they forget to change `TEAM_ID`, because each project's ObjectStore is isolated. The `TEAM_ID` prefix is still useful for clarity and if you ever consolidate data.

2. **Notebook kernel restart required.** If a student changes `config.py` after already opening a notebook, they must restart the notebook kernel (`Kernel > Restart`) for the new `TEAM_ID` to take effect.

3. **The `models/logger.py` compatibility shim** (which re-exports `PortfolioLogger` from `loggers/`) does NOT need changes. It just re-exports the class; the `team_id` parameter flows through normally.

4. **No algorithm logic changes.** The alpha model, portfolio construction, execution model, and universe are completely untouched. Only the logging/storage layer changes.

5. **Documentation references.** The `claude.md` file and any other docs that mention `wolfpack/` paths should be updated to reference `{TEAM_ID}/` paths, but this is cosmetic and not required for the code to work.

---

## Design Decision: Why `config.py` Instead of QC Project Parameters

An alternative approach is to use QuantConnect's built-in project parameters (`self.GetParameter("team_id")`) so that the code is byte-for-byte identical across all projects. While this is the "correct" QC pattern for algorithms, it has a critical limitation: **research notebooks cannot reliably read project parameters.** `QuantBook.GetParameter()` does not work the same way as in the algorithm context, so notebooks would still need a hardcoded fallback — defeating the purpose.

The `config.py` approach works identically in both the algorithm and research contexts. Students edit one file, one line, and everything just works.
