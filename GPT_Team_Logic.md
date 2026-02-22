# GPT Team Logic Implementation Guide

## 1. Goal

Make one codebase run unchanged across 8 QuantConnect cloud projects, with data isolation by project via a single project parameter.

- 7 student team projects: `team_1` to `team_7`
- 1 instructor master project: `production`
- ObjectStore key format: `wolfpack/<team_id>/<file>.csv`

Examples:
- `wolfpack/team_1/daily_snapshots.csv`
- `wolfpack/production/daily_snapshots.csv`

## 2. Locked Decisions

These are fixed from your requirements:

1. Team identity source is a QuantConnect project parameter.
2. ObjectStore layout is `wolfpack/team_1/...` style.
3. Master environment ID is `production`.
4. Every notebook uses one shared variable (defined once near the top) to resolve keys.

## 3. Non-Goals

Do not change strategy behavior.

- No changes to alpha logic
- No changes to portfolio/risk logic
- No changes to execution tiers or stale-order behavior
- No changes to CSV schema/columns

Only change where ObjectStore keys are built/read.

## 4. Current Hardcoded Key Locations

### Algorithm-side writes/deletes

- `main.py` clears hardcoded keys in `Initialize()`.
- `loggers/snapshot_logger.py` writes `wolfpack/daily_snapshots.csv`.
- `loggers/position_logger.py` writes `wolfpack/positions.csv` and `wolfpack/trades.csv`.
- `loggers/signal_logger.py` writes `wolfpack/signals.csv`.
- `loggers/slippage_logger.py` writes `wolfpack/slippage.csv`.
- `loggers/target_logger.py` writes `wolfpack/targets.csv`.
- `loggers/order_event_logger.py` writes `wolfpack/order_events.csv`.

### Notebook-side reads (currently hardcoded)

All of these currently reference `wolfpack/...` directly and must be routed through the shared key builder:

- `research/column_inspector.ipynb`
- `research/exposure/01_concentration_risk.ipynb`
- `research/exposure/02_portfolio_vol_vs_target.ipynb`
- `research/exposure/03_exposure_regime_dashboard.ipynb`
- `research/exposure/04_exposure_split_plots.ipynb`
- `research/performance_metrics.ipynb`
- `research/pnl_attribution.ipynb`
- `research/position_monitor.ipynb`
- `research/risk/beta_vs_spy.ipynb`
- `research/risk/correlation_risk.ipynb`
- `research/risk/portfolio_volatility.ipynb`
- `research/risk/risk_metrics.ipynb`
- `research/signal/signal_distribution_dashboard.ipynb`
- `research/signal/signal_profitability_stats.ipynb`
- `research/signal/signal_tier_execution_quality.ipynb`
- `research/signal/signal_what_and_why.ipynb`
- `research/slippage_analysis.ipynb`
- `research/timeseries_plotter.ipynb`
- `research/trading/daily_fill_aggressiveness.ipynb`
- `research/trading/limit_spread_vs_fill.ipynb`
- `research/trading/order_lifecycle.ipynb`
- `research/trading/rebalance_week_health.ipynb`
- `research/trading/scaling_adherence.ipynb`
- `research/trading/stale_signal_risk.ipynb`
- `research/trading/weekly_execution_progress.ipynb`
- `research/universe_selection/01_signal_evolution_by_equity.ipynb`
- `research/universe_selection/02_weekly_selection_diagnostics.ipynb`
- `research/universe_selection/03_symbol_stickiness_and_why.ipynb`

## 5. Target Data Contract

Keep file names unchanged under each team folder:

- `daily_snapshots.csv`
- `positions.csv`
- `signals.csv`
- `slippage.csv`
- `trades.csv`
- `targets.csv`
- `order_events.csv`

Key pattern:

```text
wolfpack/<team_id>/<file_name>
```

## 6. Recommended Implementation Pattern

### Step 1: Add one canonical key builder

Create a small shared helper (recommended file: `core/objectstore_keys.py`) so the whole project uses one source of truth.

Recommended contents:

```python
OBJECTSTORE_FILES = (
    "daily_snapshots.csv",
    "positions.csv",
    "signals.csv",
    "slippage.csv",
    "trades.csv",
    "targets.csv",
    "order_events.csv",
)

VALID_TEAM_IDS = {"production", "team_1", "team_2", "team_3", "team_4", "team_5", "team_6", "team_7"}


def normalize_team_id(raw):
    team_id = (raw or "production").strip().lower()
    return team_id or "production"


def validate_team_id(team_id):
    if team_id not in VALID_TEAM_IDS:
        raise ValueError(
            f"Invalid team_id '{team_id}'. Expected one of: {sorted(VALID_TEAM_IDS)}"
        )


def build_prefix(team_id):
    return f"wolfpack/{team_id}"


def build_key(prefix, file_name):
    return f"{prefix}/{file_name}"
```

Why this helps:

- Removes duplicated string literals.
- Prevents one file from accidentally writing to a different key namespace.
- Makes auditing easy.

### Step 2: Read `team_id` parameter once in `main.py`

In `Initialize()`:

1. Read project parameter via `GetParameter("team_id", "production")`.
2. Normalize and validate.
3. Store on algorithm instance (for reuse), for example:
   - `self.team_id`
   - `self.objectstore_prefix`
4. Log resolved value using `Debug()`.

Recommended logic:

```python
raw_team_id = self.GetParameter("team_id", "production")
self.team_id = normalize_team_id(raw_team_id)
validate_team_id(self.team_id)
self.objectstore_prefix = build_prefix(self.team_id)
self.Debug(f"Team context: team_id={self.team_id}, prefix={self.objectstore_prefix}")
```

### Step 3: Route startup cleanup through dynamic keys

Replace hardcoded deletes in `main.py` with a loop over `OBJECTSTORE_FILES`.

Concept:

```python
for file_name in OBJECTSTORE_FILES:
    key = build_key(self.objectstore_prefix, file_name)
    if self.ObjectStore.ContainsKey(key):
        self.ObjectStore.Delete(key)
```

Important behavior: this only clears the current project/team namespace.

### Step 4: Pass prefix into logging components

Make `PortfolioLogger` accept an ObjectStore prefix (or key function) and pass it to all sub-loggers.

Recommended signature change:

```python
PortfolioLogger(objectstore_prefix)
```

Then each logger writes with:

```python
algorithm.ObjectStore.Save(f"{self.objectstore_prefix}/daily_snapshots.csv", csv_content)
```

Apply to all seven save locations.

### Step 5: Keep filenames and columns identical

Do not rename files or columns. Only prepend team folder.

## 7. Notebook Standardization Pattern

Each notebook should define team context once in a top configuration cell, then all reads call a key helper.

### Standard top cell (copy into every notebook)

```python
TEAM_ID = "production"

try:
    # QuantBook is a wrapper over QCAlgorithm; use parameter if available
    param_value = qb.GetParameter("team_id")
    if isinstance(param_value, str) and param_value.strip():
        TEAM_ID = param_value.strip().lower()
except Exception:
    # Fallback keeps notebooks usable outside cloud parameter context
    pass

VALID_TEAM_IDS = {"production", "team_1", "team_2", "team_3", "team_4", "team_5", "team_6", "team_7"}
if TEAM_ID not in VALID_TEAM_IDS:
    raise ValueError(f"Invalid TEAM_ID '{TEAM_ID}'. Expected one of {sorted(VALID_TEAM_IDS)}")

OBJECTSTORE_PREFIX = f"wolfpack/{TEAM_ID}"

def os_key(file_name: str) -> str:
    return f"{OBJECTSTORE_PREFIX}/{file_name}"

print(f"Notebook team context -> {TEAM_ID}")
print(f"ObjectStore prefix -> {OBJECTSTORE_PREFIX}")
```

### Replacement rule in notebook code

Replace every hardcoded key string like:

```python
"wolfpack/daily_snapshots.csv"
```

with:

```python
os_key("daily_snapshots.csv")
```

Do this for all seven files.

### Minimum read examples

```python
df_snapshots = read_csv_from_store(os_key("daily_snapshots.csv"))
df_positions = read_csv_from_store(os_key("positions.csv"))
df_signals = read_csv_from_store(os_key("signals.csv"))
df_slippage = read_csv_from_store(os_key("slippage.csv"))
df_trades = read_csv_from_store(os_key("trades.csv"))
df_targets = read_csv_from_store(os_key("targets.csv"))
df_events = read_csv_from_store(os_key("order_events.csv"))
```

## 8. Project Setup in QuantConnect Cloud

Create 8 projects with identical code.

Parameter mapping:

| Project role | `team_id` parameter |
|---|---|
| Production master | `production` |
| Team 1 | `team_1` |
| Team 2 | `team_2` |
| Team 3 | `team_3` |
| Team 4 | `team_4` |
| Team 5 | `team_5` |
| Team 6 | `team_6` |
| Team 7 | `team_7` |

Cloud UI reminder:

1. Open each project.
2. Add algorithm parameter `team_id`.
3. Set its default value to the row above.
4. Save.

This keeps code identical while data routes per project.

## 9. Verification Checklist

### Local compile sanity

```bash
python -m py_compile main.py models/*.py core/*.py signals/*.py risk/*.py execution/*.py loggers/*.py
```

### Cloud functional check (one project at a time)

For each project/team:

1. Run a short backtest.
2. Confirm logs show resolved team context.
3. In research notebook, print `OBJECTSTORE_PREFIX`.
4. Confirm CSV loads from `wolfpack/<team_id>/...`.

### Isolation check

- Team 1 project must not overwrite Production keys.
- Production project must not clear Team keys on startup.

## 10. Rollout Plan for Class

1. Implement key-routing changes once in master code.
2. Validate in one staging project (for example `team_1`).
3. Push same code to all 8 projects.
4. Set `team_id` parameter per project.
5. Run one smoke backtest in each project.
6. Give each team only its assigned project.

## 11. Common Pitfalls and Fixes

- Pitfall: missing `team_id` parameter.
  Fix: default to `production` in code and log the final value.

- Pitfall: one notebook still hardcodes `wolfpack/...`.
  Fix: run `rg -n "wolfpack/" research` and replace with `os_key(...)` reads.

- Pitfall: cleanup code deletes global keys.
  Fix: cleanup loop must use `build_key(self.objectstore_prefix, file_name)`.

- Pitfall: typo in team IDs (`Team1`, `team-1`, etc.).
  Fix: strict validation against `production` + `team_1..team_7`.

## 12. Optional Hardening (Recommended)

If you want extra safety:

- Add a debug warning when defaulting to `production` because `team_id` was blank.
- Add a run tag that includes `team_id` for easier backtest filtering.
- Add a notebook assertion cell that confirms key existence before analysis.

Example assertion cell:

```python
required_files = [
    "daily_snapshots.csv",
    "positions.csv",
    "signals.csv",
    "slippage.csv",
    "trades.csv",
    "targets.csv",
    "order_events.csv",
]
for f in required_files:
    key = os_key(f)
    print(key, qb.ObjectStore.ContainsKey(key))
```

## 13. Final Acceptance Criteria

Implementation is complete when all are true:

1. All 8 projects run the exact same code revision.
2. Each project has its own `team_id` parameter.
3. Algorithm writes and deletes only `wolfpack/<team_id>/...` keys.
4. All research notebooks resolve keys from one top-level shared variable and helper.
5. Production uses `wolfpack/production/...`.
6. Team projects use `wolfpack/team_1/...` through `wolfpack/team_7/...`.

