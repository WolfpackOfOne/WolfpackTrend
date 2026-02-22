# Universe Selection Research Notebooks

This folder is a focused workflow to diagnose why the same names are repeatedly traded.

## Notebook order
1. `01_signal_evolution_by_equity.ipynb`
2. `02_weekly_selection_diagnostics.ipynb`
3. `03_symbol_stickiness_and_why.ipynb`

## Data required
- `{TEAM_ID}/signals.csv`
- `{TEAM_ID}/targets.csv`
- Optional: `{TEAM_ID}/positions.csv`

Run a fresh backtest first so ObjectStore contains current logs.
