# GPT_Notebook.md

Instructions for Claude Code to create research notebooks for the WolfpackTrend 1 project.

## Scope and Safety
- Work only inside `WolfpackTrend 1/`.
- Do not edit `Lean/`, `MyProjects/lean.json`, or any `config.json` files.
- Prefer small, incremental changes.
- Read `WolfpackTrend 1/claude.md` for ObjectStore schema and usage.

## Reference Notebooks (Wheel)
Use these as style and structure references:
- `Wheel/research/column_inspector.ipynb`
- `Wheel/research/timeseries_plotter.ipynb`
- `Wheel/research/position_monitor.ipynb`
- `Wheel/research/pl_attribution.ipynb`

## Data Sources (ObjectStore)
Load from QuantConnect ObjectStore using QuantBook:
- `wolfpack/daily_snapshots.csv`
- `wolfpack/positions.csv`
- `wolfpack/signals.csv`
- `wolfpack/slippage.csv`

Expected columns are documented in `WolfpackTrend 1/claude.md`.

## Notebook Set to Create
Create a `WolfpackTrend 1/research/` directory and add the notebooks below.

### 1) column_inspector.ipynb
Purpose: schema validation and quick sanity checks.
Required:
- Load each CSV from ObjectStore.
- Display shape, dtypes, and top 20 rows per column (similar to Wheel column inspector).

### 2) timeseries_plotter.ipynb
Purpose: quick time series exploration.
Required:
- Load `wolfpack/daily_snapshots.csv`.
- Auto-plot all numeric columns as time series.
- Include a date filter or `start_date`/`end_date` variables.

### 3) position_monitor.ipynb
Purpose: exposure dashboard.
Required:
- Load `wolfpack/positions.csv` and `wolfpack/daily_snapshots.csv`.
- Plot top weights on a given date, net/gross/long/short exposure over time.
- Include a `target_date` variable.

### 4) slippage_analysis.ipynb
Purpose: slippage diagnostics.
Required:
- Load `wolfpack/slippage.csv`.
- Compute slippage in $ and bps (use expected_price or fill_price as denominator).
- Show distributions by symbol and direction, and daily aggregates.
- Plot daily slippage vs gross exposure or estimated volatility (from daily snapshots).

### 5) risk_metrics.ipynb
Purpose: VaR / CVaR.
Required:
- Derive daily returns from `nav` in `wolfpack/daily_snapshots.csv`.
- Compute historical VaR and CVaR at 95% and 99%.
- Provide rolling windows (20/60/252 days).
- Plot drawdowns and rolling risk metrics.

### 6) performance_metrics.ipynb
Purpose: Sharpe and summary stats.
Required:
- Daily return series from `nav`.
- Compute Sharpe (daily, annualized), Sortino, Calmar.
- Allow configurable risk-free rate (default 0.0).

### 7) pnl_attribution.ipynb
Purpose: P&L attribution.
Required:
- Use positions (weights) and daily price returns to compute per-symbol contribution.
- If trade-level data is not available, do weights-based attribution.
- Overlay daily slippage cost from `wolfpack/slippage.csv`.

## Notebook Standards
- Each notebook starts with a markdown title and a brief description.
- First code cell: imports and helper functions.
- Second cell: ObjectStore load with error handling for missing files.
- Keep plotting style consistent with Wheel notebooks (matplotlib or plotly).
- Avoid heavy refactors; keep computations straightforward and transparent.

## Validation
- Note in the notebook if it requires a backtest to populate ObjectStore.
- If a file is missing, show a clear message and stop further cells.
