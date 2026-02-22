# Architecture

WolfpackTrend uses a layered architecture built on QuantConnect's LEAN framework. The codebase was refactored into an atomic design: pure functions at the bottom, domain modules in the middle, and LEAN framework wrappers at the top.

## Layer Overview

```
┌─────────────────────────────────────────────────┐
│  main.py  (Composition Root)                    │
│  - Wires models together                        │
│  - Schedules stale-order cancellation            │
│  - Routes events (OnData, OnOrderEvent)          │
├─────────────────────────────────────────────────┤
│  models/  (Compatibility Adapters)              │
│  - Thin re-exports from domain modules          │
│  - Preserves import paths for main.py           │
├──────────┬──────────┬───────────┬───────────────┤
│ signals/ │  risk/   │execution/ │   loggers/    │
│ (Alpha)  │  (PCM)   │  (Exec)   │  (Logging)    │
│          │          │           │               │
│ Organisms: LEAN-aware classes that              │
│ implement AlphaModel, PCM, ExecutionModel       │
├─────────────────────────────────────────────────┤
│  core/  (Atoms)                                 │
│  - Pure functions (no self, no QC imports)       │
│  - math_utils.py: signal computation, vol est,  │
│    constraints, limit pricing, scaling           │
│  - formatting.py: CSV builder, tag parsing       │
│  - data_types.py: typed dataclass stubs          │
│  - universe.py: re-exports DOW30 ticker list     │
└─────────────────────────────────────────────────┘
```

## Directory Map

```
WolfpackTrend 1/
├── main.py                     # Algorithm entrypoint (QCAlgorithm subclass)
├── models/                     # Compatibility adapters (thin re-exports)
│   ├── __init__.py             # Exports: DOW30, all model classes
│   ├── universe.py             # DOW30 ticker list (source of truth)
│   ├── alpha.py                # → signals.alpha.CompositeTrendAlphaModel
│   ├── portfolio.py            # → risk.portfolio.TargetVolPortfolioConstructionModel
│   ├── execution.py            # → execution.execution.SignalStrengthExecutionModel
│   └── logger.py               # → loggers.portfolio_logger.PortfolioLogger
├── core/                       # Pure functions (no QC dependencies)
│   ├── __init__.py             # Exports DOW30
│   ├── universe.py             # Re-exports DOW30 from models.universe
│   ├── math_utils.py           # Signal computation, vol estimation, constraints
│   ├── formatting.py           # CSV building, order tag parsing
│   └── data_types.py           # Typed dataclass stubs (Signal, TargetState, etc.)
├── signals/                    # Signal generation domain
│   ├── __init__.py
│   ├── trend.py                # compute_trend_signals() molecule
│   └── alpha.py                # CompositeTrendAlphaModel (LEAN AlphaModel)
├── risk/                       # Portfolio construction domain
│   ├── __init__.py
│   ├── constraints.py          # Re-exports constraint functions from core
│   ├── vol_estimator.py        # Re-exports estimate_portfolio_vol from core
│   ├── scaling.py              # Re-exports build_scaling_schedule from core
│   └── portfolio.py            # TargetVolPortfolioConstructionModel (LEAN PCM)
├── execution/                  # Order execution domain
│   ├── __init__.py
│   ├── pricing.py              # Limit price computation molecule
│   ├── cancellation.py         # Stale order cancellation logic
│   └── execution.py            # SignalStrengthExecutionModel (LEAN ExecutionModel)
├── loggers/                    # Logging domain
│   ├── __init__.py
│   ├── csv_writer.py           # Re-exports build_csv from core
│   ├── snapshot_logger.py      # Daily portfolio snapshots
│   ├── position_logger.py      # Position tracking + trade close detection
│   ├── signal_logger.py        # Alpha signal logging
│   ├── slippage_logger.py      # Fill slippage tracking
│   ├── order_event_logger.py   # Order lifecycle events
│   ├── target_logger.py        # Daily scaling target state
│   └── portfolio_logger.py     # Facade composing all sub-loggers
├── templates/                  # Reference configurations
│   ├── __init__.py
│   └── strategy_config.py      # Default parameter values
├── tools/                      # Development utilities
│   └── parity/                 # Backtest parity verification
│       ├── fetch_backtest_stats.py
│       ├── compare_metrics.py
│       └── run_phase_gate.sh
├── backtests/                  # Backtest artifacts (gitignored)
│   └── atomic_refactor/        # Refactor phase tracking
│       └── progress.md
└── docs/                       # This documentation
```

## Design Principles

### Atoms (`core/`)
- Pure functions only - no `self`, no `algorithm` references, no QC imports
- Accept plain Python types (floats, dicts, lists), return plain Python types
- Deterministic: same inputs always produce same outputs
- Unit-testable without any LEAN infrastructure

### Organisms (domain modules)
- LEAN-aware classes that implement framework interfaces (AlphaModel, PCM, ExecutionModel)
- Call into `core/` atoms for all computation
- Handle framework concerns: indicators, RollingWindows, Insight creation, order submission

### Adapters (`models/`)
- One-line re-exports that preserve the original import paths
- `main.py` imports from `models/` and never needs to change when internals refactor
- Can be removed once `main.py` imports directly from domain modules (Phase 14, optional)

## Data Flow

```
Market Data
    │
    ▼
Alpha Model (signals/)
    │ Emits Insight[] daily
    │ (fresh on rebalance days, cached on scaling days)
    ▼
Portfolio Construction Model (risk/)
    │ Converts insights → PortfolioTarget[]
    │ Applies: vol targeting → per-name cap → gross cap → net cap
    │ Scales targets over 5 trading days
    ▼
Execution Model (execution/)
    │ Converts targets → orders
    │ Signal strength determines limit offset
    │ Stale orders cancelled by week_id cycle
    ▼
Order Events → Logger (loggers/)
    │ Tracks fills, slippage, positions, snapshots
    │ Saves to ObjectStore at end of backtest
    ▼
ObjectStore (7 CSV files)
```
