# CC_Atomic.md — Atomic Refactor Playbook

## Purpose

Step-by-step instructions for Claude Code to incrementally refactor the WolfpackTrend codebase from a flat `models/` structure into a domain-grouped atomic architecture. Each phase is followed by a cloud backtest to verify no regressions.

---

## Design Decisions (From User Answers)

| Question | Decision |
|----------|----------|
| Multi-strategy vs single | Single strategy — isolate logic changes to one file |
| Cross-module coupling | Decouple where practical (pass data through pipeline) |
| QCAlgorithm access | "receives algorithm as a parameter" acceptable at all levels |
| LEAN inheritance | Keep LEAN base classes (AlphaModel, PCM, ExecutionModel) as-is |
| Logger | Break into smaller pieces (snapshot, position, slippage, etc.) |
| Math/utilities | Extract pure functions into shared utility layer |
| Data structures | Introduce typed dataclasses (Signal, TargetState, OrderRecord, etc.) |
| Local testability | Not a goal — cloud backtesting is primary validation |
| Directory structure | Domain-grouped folders (signals/, risk/, execution/, loggers/) |
| Migration strategy | Incremental — one phase at a time with backtest verification |

---

## Target Directory Structure

```
WolfpackTrend 1/
├── main.py                          # QCAlgorithm entrypoint (Page)
├── config.json                      # QC cloud config (not tracked)
├── claude.md                        # Project documentation
├── CC_Atomic.md                     # This file
│
├── core/                            # Atoms: pure utilities, data structures, constants
│   ├── __init__.py
│   ├── universe.py                  # DOW30 ticker list (moved from models/)
│   ├── types.py                     # Dataclasses: Signal, TargetState, OrderRecord, etc.
│   ├── math_utils.py                # Pure math: vol estimation, constraint functions, scaling schedules
│   └── formatting.py                # CSV builder, order tag builder, week_id parser
│
├── signals/                         # Signal domain (Alpha)
│   ├── __init__.py
│   ├── trend.py                     # Molecules: signal computation (ATR-normalized SMA distances, composite score, tanh)
│   └── alpha.py                     # Organism: CompositeTrendAlphaModel (LEAN AlphaModel wrapper)
│
├── risk/                            # Risk/Portfolio domain
│   ├── __init__.py
│   ├── constraints.py               # Molecules: per-name cap, gross cap, net cap
│   ├── vol_estimator.py             # Molecules: rolling returns tracker, diagonal vol estimation
│   ├── scaling.py                   # Molecules: scaling schedule logic, week plan initialization
│   └── portfolio.py                 # Organism: TargetVolPortfolioConstructionModel (LEAN PCM wrapper)
│
├── execution/                       # Execution domain
│   ├── __init__.py
│   ├── pricing.py                   # Molecules: limit price computation, signal-strength tier logic
│   ├── cancellation.py              # Molecules: stale order cancellation (signal-aware + legacy)
│   └── execution.py                 # Organism: SignalStrengthExecutionModel (LEAN ExecutionModel wrapper)
│
└── loggers/                         # Logging domain (named loggers/ to avoid shadowing Python's built-in logging module)
    ├── __init__.py
    ├── snapshot_logger.py           # Molecule: daily portfolio snapshot logging
    ├── position_logger.py           # Molecule: position tracking, close detection, daily deltas
    ├── signal_logger.py             # Molecule: signal event logging
    ├── slippage_logger.py           # Molecule: slippage tracking and accumulation
    ├── order_event_logger.py        # Molecule: order lifecycle event logging
    ├── target_logger.py             # Molecule: daily target-state logging
    ├── csv_writer.py                # Atom: CSV building and ObjectStore persistence
    └── portfolio_logger.py          # Organism: PortfolioLogger facade (composes all sub-loggers)
```

---

## Atomic Layer Definitions (For This Project)

### Atoms (`core/`)
- **Zero dependencies** on other project modules
- **Zero QC runtime calls** (no `algorithm.*`)
- Pure functions, constants, dataclasses
- Examples: `DOW30` list, `Signal` dataclass, `compute_limit_price()`, `build_csv()`

### Molecules (domain `*.py` files that are NOT the organism)
- **May import from `core/`** only (never from other domains or organisms)
- **May receive `algorithm` as a parameter** for data access, but should not orchestrate
- Implement a single rule or computation
- Examples: `compute_trend_signal()`, `apply_gross_cap()`, `cancel_stale_orders()`

### Organisms (domain organism files: `alpha.py`, `portfolio.py`, `execution.py`, `portfolio_logger.py`)
- **May import from `core/` and from molecules within their own domain**
- **Inherit from LEAN base classes** (AlphaModel, PortfolioConstructionModel, ExecutionModel)
- Orchestrate molecules, manage state, implement LEAN interface methods
- These are what `main.py` instantiates and wires together

### Page (`main.py`)
- **Imports only from organisms** (via domain `__init__.py` barrel exports)
- Wires everything together in `Initialize()`
- Handles `OnData`, `OnOrderEvent`, `OnEndOfAlgorithm` callbacks
- The only place that calls `self.SetAlpha()`, `self.SetExecution()`, etc.

### Import Rule (ENFORCED)
```
core/ ← signals/, risk/, execution/, loggers/     (anyone can import core)
molecules ← organisms (within same domain only)
organisms ← main.py (via __init__.py)

NEVER: core imports from any domain
NEVER: molecule imports from another domain's molecules
NEVER: molecule imports from any organism
NEVER: organism imports from another domain's organism
```

Cross-domain data sharing happens via:
1. **Dataclasses from `core/types.py`** passed through method arguments
2. **Algorithm attributes** (e.g., `algorithm.pcm.signal_strengths`) — acceptable per user decision
3. **Return values** flowing through the LEAN pipeline (Insight → PortfolioTarget)

---

## Phase 0: Baseline Backtest (MUST DO FIRST)

### What
Run the current unmodified code and save the results so every subsequent phase can be compared against it.

### Steps

1. **Activate the virtual environment and push current code:**
```bash
cd ~/Documents/QuantConnect
source venv/bin/activate
cd MyProjects
lean cloud push --project "WolfpackTrend 1" --force
```

2. **Run the baseline backtest and save results:**
```bash
# Create a directory to store backtest comparisons
mkdir -p "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1/backtest_results"

# Run backtest and capture output in one pass
lean cloud backtest "WolfpackTrend 1" --name "Atomic Phase 0 - Baseline (pre-refactor)" 2>&1 | tee "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1/backtest_results/phase0_baseline.txt"
```

3. **Record the key metrics** from the output into a comparison file:
```bash
# Create a tracking file for phase-by-phase comparison
cat > "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1/backtest_results/comparison.md" << 'EOF'
# Backtest Comparison — Atomic Refactor

| Phase | Description | Total Return | Sharpe | Drawdown | Trades | Status |
|-------|-------------|-------------|--------|----------|--------|--------|
| 0     | Baseline (pre-refactor) | ??? | ??? | ??? | ??? | ??? |
EOF
```

4. **After the backtest finishes**, read the output and fill in the actual numbers in `comparison.md`. The key metrics to track are:
   - **Total Return %**
   - **Sharpe Ratio**
   - **Max Drawdown %**
   - **Total Trades** (number of orders)
   - **Final NAV**

### Success Criteria
- Backtest completes without errors
- Metrics are recorded in `backtest_results/comparison.md`

### Commit
```bash
git add backtest_results/
git commit -m "Phase 0: Save baseline backtest results for atomic refactor comparison"
```

---

## Phase 1: Create Directory Skeleton and `core/` Atoms

### What
Create the new directory structure. Move `universe.py` into `core/`. Create `core/types.py` with initial dataclasses. Create `core/math_utils.py` and `core/formatting.py` as empty stubs. **Do NOT modify any existing model files yet** — just create the new structure alongside.

### Steps

1. **Create all directories:**
```
core/
signals/
risk/
execution/  (note: will coexist with models/execution.py temporarily)
loggers/    (NOT logging/ — avoids shadowing Python's built-in logging module)
```

2. **Create `core/__init__.py`:**
```python
from .universe import DOW30
from .types import (
    Signal, TargetState, OrderRecord, TradeRecord,
    PositionSnapshot, SlippageRecord, OrderEventRecord,
)
```

3. **Create `core/universe.py`** — copy from `models/universe.py` (identical content):
```python
# Dow 30 tickers (static basket)
DOW30 = [
    "AAPL", "AMGN", "AXP", "BA", "CAT", "CRM",
    "CSCO", "CVX", "DIS", "DOW", "GS", "HD",
    "HON", "IBM", "INTC", "JNJ", "JPM", "KO",
    "MCD", "MMM", "MRK", "MSFT", "NKE", "PG",
    "TRV", "UNH", "V", "VZ", "WBA", "WMT"
]
```

4. **Create `core/types.py`** with dataclasses. These will be used in later phases to replace plain dicts:
```python
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Signal:
    """A trend signal emitted by the alpha model."""
    symbol: object          # LEAN Symbol
    direction: int          # InsightDirection.Up (1) or InsightDirection.Down (-1)
    magnitude: float        # Signal strength in (-1, +1) from tanh
    price: float            # Price at signal generation
    sma_short: float        # Short SMA value
    sma_medium: float       # Medium SMA value
    sma_long: float         # Long SMA value
    atr: float              # ATR value


@dataclass
class TargetState:
    """Per-symbol target state for a single day within a scaling cycle."""
    week_id: str            # Rebalance date (YYYY-MM-DD)
    symbol: str             # Ticker string
    start_w: float          # Portfolio weight at start of cycle
    weekly_target_w: float  # Final target weight for the cycle
    scheduled_fraction: float  # Cumulative scaling fraction for today
    scheduled_w: float      # Scheduled weight for today
    actual_w: float         # Actual portfolio weight
    scale_day: int          # Current scaling day (0-indexed)


@dataclass
class OrderRecord:
    """Metadata for a submitted order."""
    order_id: int
    symbol: object          # LEAN Symbol
    tier: str               # "strong", "moderate", "weak", "exit"
    signal_strength: float
    week_id: str            # Rebalance cycle identifier
    market_price_at_submit: float
    limit_price: Optional[float] = None


@dataclass
class TradeRecord:
    """A closed position record."""
    date: str               # YYYY-MM-DD
    symbol: str             # Ticker string
    action: str             # "CLOSE"
    quantity: float
    avg_price: float
    exit_price: float
    realized_pnl: float


@dataclass
class PositionSnapshot:
    """Daily position snapshot for a single symbol."""
    date: str
    symbol: str
    invested: bool
    quantity: float
    price: float
    market_value: float
    weight: float
    unrealized_pnl: float
    daily_pnl: float
    daily_unrealized_pnl: float
    daily_realized_pnl: float
    daily_fees: float
    daily_dividends: float
    daily_total_net_pnl: float
    avg_price: float


@dataclass
class SlippageRecord:
    """Slippage data for a single fill."""
    date: str
    symbol: str
    direction: str
    quantity: float
    expected_price: float
    fill_price: float
    slippage_dollars: float


@dataclass
class OrderEventRecord:
    """A single order lifecycle event."""
    date: str
    order_id: int
    symbol: str
    status: str
    direction: str
    quantity: float
    fill_quantity: float
    fill_price: float
    order_type: str
    limit_price: Optional[float] = None
    market_price_at_submit: Optional[float] = None
    tag: str = ""
```

5. **Create `core/math_utils.py`** — empty stub for now:
```python
"""Pure math utilities. Populated in Phase 3."""
```

6. **Create `core/formatting.py`** — empty stub for now:
```python
"""Formatting utilities (CSV, tags, parsing). Populated in Phase 4."""
```

7. **Create empty `__init__.py` in each domain directory:**
```python
# signals/__init__.py, risk/__init__.py, execution/__init__.py, loggers/__init__.py
```

8. **Verify `main.py` still imports from `models/` and runs unchanged.** Do NOT change any import in `main.py` yet.

### Backtest
```bash
cd ~/Documents/QuantConnect && source venv/bin/activate && cd MyProjects
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Atomic Phase 1 - Directory skeleton + core types"
```

### Success Criteria
- Backtest results are **identical** to Phase 0 (no existing code was modified)
- All new directories and files exist
- Record results in `backtest_results/comparison.md`

### Commit
```bash
git add core/ signals/ risk/ execution/ loggers/ backtest_results/
git commit -m "Phase 1: Create directory skeleton and core atom types"
```

---

## Phase 2: Extract Pure Math into `core/math_utils.py`

### What
Extract pure mathematical functions from `portfolio.py` and `execution.py` into `core/math_utils.py`. The original models still use their own copies — this phase just creates the canonical versions in `core/`. In the next phases, the models will be updated to import from `core/`.

### Functions to Extract

From `portfolio.py`:
- `build_scaling_schedule(scaling_days, front_load_factor)` → extracted from `_build_schedule()`
- `estimate_portfolio_vol(weights, rolling_returns, min_obs)` → extracted from `_estimate_portfolio_vol()`
- `apply_per_name_cap(weights, max_weight)` → extracted from `_apply_per_name_cap()`
- `apply_gross_cap(weights, max_gross)` → extracted from `_apply_gross_cap()`
- `apply_net_cap(weights, max_net)` → extracted from `_apply_net_cap()`

From `execution.py`:
- `compute_limit_price(price, quantity, offset_pct, tick_size)` → extracted from `_compute_limit_price()`
- `extract_week_id_from_tag(tag)` → extracted from `_extract_week_id_from_tag()`

From `alpha.py`:
- `compute_composite_signal(price, sma_short, sma_medium, sma_long, atr, weights, temperature, min_magnitude)` → extracted from inline logic in `_compute_signals()`

### Implementation Rules

- Functions in `core/math_utils.py` must be **pure** — no `self`, no `algorithm`, no QC imports
- They receive plain Python values (floats, dicts, lists) and return plain Python values
- For `estimate_portfolio_vol`, accept a dict of `{symbol: [returns_list]}` instead of `RollingWindow` objects
- Each function must have a docstring explaining inputs, outputs, and the math

### Example Signature for `compute_composite_signal`:
```python
def compute_composite_signal(price, sma_short, sma_medium, sma_long, atr_value,
                              weights=(0.2, 0.5, 0.3), temperature=3.0,
                              min_magnitude=0.05):
    """
    Compute trend signal from ATR-normalized SMA distances.

    Args:
        price: Current close price
        sma_short: Short-period SMA value
        sma_medium: Medium-period SMA value
        sma_long: Long-period SMA value
        atr_value: ATR value (clamped to >= 1e-8 internally)
        weights: Tuple of (short_weight, medium_weight, long_weight)
        temperature: Divisor before tanh (controls sensitivity)
        min_magnitude: Skip signals below this absolute value

    Returns:
        float or None: Signal magnitude in (-1, +1) via tanh, or None if:
            - signals don't all agree in direction
            - magnitude below min_magnitude
    """
```

### Backtest
```bash
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Atomic Phase 2 - Extract pure math to core"
```

### Success Criteria
- Backtest results **identical** to Phase 0 (existing models unchanged)
- `core/math_utils.py` contains all listed functions with docstrings
- No QC imports anywhere in `core/`

### Commit
```bash
git add core/math_utils.py
git commit -m "Phase 2: Extract pure math functions into core/math_utils.py"
```

---

## Phase 3: Extract Formatting Utilities into `core/formatting.py`

### What
Extract formatting/parsing functions that currently live inside model classes.

### Functions to Extract

From `logger.py`:
- `build_csv(data, columns)` → extracted from `_build_csv()`

From `execution.py`:
- `build_order_tag(tier, signal_strength, week_id, scale_day)` → extracted from `_build_order_tag()`
- `extract_week_id_from_tag(tag)` → already in `core/math_utils.py` from Phase 2, **move it here** since it's formatting not math

### Implementation Rules

- Pure functions, no `self`, no `algorithm`, no QC imports
- `build_order_tag` takes plain values instead of reaching into `algorithm.pcm`
- `build_csv` takes `List[Dict]` and `List[str]` columns, returns `str`

### Backtest
```bash
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Atomic Phase 3 - Extract formatting to core"
```

### Success Criteria
- Backtest results **identical** to Phase 0
- `core/formatting.py` contains all listed functions
- `extract_week_id_from_tag` moved from `math_utils.py` to `formatting.py`

### Commit
```bash
git add core/formatting.py core/math_utils.py
git commit -m "Phase 3: Extract formatting utilities into core/formatting.py"
```

---

## Phase 4: Wire Alpha Model to Use `core/` Atoms

### What
Modify `models/alpha.py` to import and call functions from `core/math_utils.py` instead of having inline signal computation. This is the first phase that **modifies existing code**.

### Changes to `models/alpha.py`

1. Add import at top:
```python
from core.math_utils import compute_composite_signal
```

2. Replace the inline signal computation in `_compute_signals()` with a call to `compute_composite_signal()`. The method should:
   - Still iterate over symbols
   - Still check indicator readiness and bar existence
   - Call `compute_composite_signal(price, sma_s, sma_m, sma_l, atr_value, ...)` for the actual math
   - Handle the return value (None means skip, float means valid signal)
   - Still update `self.cached_signals` and call `self.logger.log_signal()`

3. **Do NOT change** the class signature, `Update()`, `OnSecuritiesChanged()`, or any other public interface.

### Exact Code to Replace

In `_compute_signals`, replace lines 151-178 (the computation block after getting indicator values) with:
```python
            # Compute composite signal using core math
            mag = compute_composite_signal(
                price, sma_s, sma_m, sma_l, atr_value,
                weights=(self.weight_short, self.weight_medium, self.weight_long),
                temperature=self.signal_temperature,
                min_magnitude=self.min_magnitude
            )

            if mag is None:
                continue

            # Determine direction
            direction = InsightDirection.Up if mag > 0 else InsightDirection.Down

            # Cache signal
            self.cached_signals[symbol] = (direction, mag)
```

### Backtest
```bash
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Atomic Phase 4 - Wire alpha to core math"
```

### Success Criteria
- Backtest results **identical** to Phase 0
- `alpha.py` imports from `core.math_utils`
- Signal computation logic lives in `core/math_utils.py`
- The signal values produced are bit-for-bit identical (same tanh, same thresholds)

### Commit
```bash
git add models/alpha.py core/
git commit -m "Phase 4: Wire alpha model to use core/math_utils for signal computation"
```

---

## Phase 5: Wire Portfolio Model to Use `core/` Atoms

### What
Modify `models/portfolio.py` to import and call functions from `core/math_utils.py` for vol estimation, constraint application, and scaling schedule building.

### Changes to `models/portfolio.py`

1. Add imports:
```python
from core.math_utils import (
    build_scaling_schedule,
    estimate_portfolio_vol,
    apply_per_name_cap,
    apply_gross_cap,
    apply_net_cap,
)
```

2. In `__init__`, replace `self._build_schedule(...)` calls with `build_scaling_schedule(self.scaling_days, ...)`:
```python
self.strong_schedule = build_scaling_schedule(self.scaling_days, front_load_factor=2.0)
self.moderate_schedule = build_scaling_schedule(self.scaling_days, front_load_factor=1.3)
self.weak_schedule = build_scaling_schedule(self.scaling_days, front_load_factor=1.0)
```

3. Replace `self._estimate_portfolio_vol(weights)` calls with:
```python
# Convert RollingWindow objects to plain lists for the pure function
returns_dict = {}
for symbol in weights.keys():
    if symbol in self.rolling_returns:
        window = self.rolling_returns[symbol]
        if window.Count >= self.min_obs:
            returns_dict[symbol] = [window[i] for i in range(window.Count)]
vol_annual = estimate_portfolio_vol(weights, returns_dict)
```

**IMPORTANT**: The logger also calls `pcm._estimate_portfolio_vol()`. After this change, either:
- Keep the old `_estimate_portfolio_vol` as a thin wrapper that calls the core function, OR
- Update the logger to call the core function directly (preferred, will happen in Phase 7 when the logger is split)

**For now, keep `_estimate_portfolio_vol` as a wrapper** so the logger still works:
```python
def _estimate_portfolio_vol(self, weights):
    """Wrapper for backward compatibility with logger."""
    returns_dict = {}
    for symbol in weights.keys():
        if symbol in self.rolling_returns:
            window = self.rolling_returns[symbol]
            if window.Count >= self.min_obs:
                returns_dict[symbol] = [window[i] for i in range(window.Count)]
    return estimate_portfolio_vol(weights, returns_dict)
```

4. Replace `self._apply_per_name_cap(weights)` with `apply_per_name_cap(weights, self.max_weight)`, etc.

5. **Delete** the original private methods (`_build_schedule`, `_apply_per_name_cap`, `_apply_gross_cap`, `_apply_net_cap`) since they're now in core. Keep `_estimate_portfolio_vol` as a wrapper (see above).

### Backtest
```bash
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Atomic Phase 5 - Wire portfolio to core math"
```

### Success Criteria
- Backtest results **identical** to Phase 0
- `portfolio.py` imports from `core.math_utils`
- No duplicated math logic (except the `_estimate_portfolio_vol` wrapper)

### Commit
```bash
git add models/portfolio.py core/
git commit -m "Phase 5: Wire portfolio model to use core/math_utils for vol and constraints"
```

---

## Phase 6: Wire Execution Model to Use `core/` Atoms

### What
Modify `models/execution.py` to import and use functions from `core/math_utils.py` and `core/formatting.py`.

### Changes to `models/execution.py`

1. Add imports:
```python
from core.math_utils import compute_limit_price
from core.formatting import build_order_tag, extract_week_id_from_tag
```

2. Replace `self._compute_limit_price(security, price, quantity, offset)` calls with:
```python
tick = security.SymbolProperties.MinimumPriceVariation
limit_price = compute_limit_price(price, unordered_quantity, offset_pct, tick)
```

3. Replace `self._build_order_tag(algorithm, tier, signal_strength)` calls with:
```python
pcm = getattr(algorithm, 'pcm', None)
week_id = getattr(pcm, 'current_week_id', '') if pcm is not None else ''
scale_day = getattr(pcm, 'current_scale_day', '') if pcm is not None else ''
tag = build_order_tag(tier, signal_strength, week_id, scale_day)
```

**Note:** The tag-building now requires extracting `week_id` and `scale_day` at the call site instead of inside the helper. This is a small coupling tradeoff, but it keeps the atom pure. Alternatively, extract the PCM lookup into a small local helper at the top of `Execute()`.

4. Replace `self._extract_week_id_from_tag(tag)` with `extract_week_id_from_tag(tag)`.

5. **Delete** the original private methods: `_compute_limit_price`, `_build_order_tag`, `_extract_week_id_from_tag`.

6. Also clean up: the `import re` inside `_extract_week_id_from_tag` should be a top-level import in `core/formatting.py`.

### Backtest
```bash
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Atomic Phase 6 - Wire execution to core atoms"
```

### Success Criteria
- Backtest results **identical** to Phase 0
- `execution.py` imports from `core.math_utils` and `core.formatting`
- No duplicated utility logic

### Commit
```bash
git add models/execution.py core/
git commit -m "Phase 6: Wire execution model to use core atoms for pricing and formatting"
```

---

## Phase 7: Break Logger into Sub-Loggers (Loggers Domain)

### What
Split `models/logger.py` (411 lines, 7 data lists) into focused sub-loggers in the `loggers/` directory. Create a `PortfolioLogger` facade that composes them. **Keep `models/logger.py` as a thin re-export** so existing imports don't break yet.

### New Files

**`loggers/csv_writer.py`** (Atom):
```python
from core.formatting import build_csv

def save_to_objectstore(algorithm, key, data, columns):
    """Save a list of dicts as CSV to ObjectStore."""
    if not data:
        return 0
    csv_content = build_csv(data, columns)
    algorithm.ObjectStore.Save(key, csv_content)
    return len(data)
```

**`loggers/snapshot_logger.py`** (Molecule):
- Class `SnapshotLogger` with:
  - `__init__()` — holds `self.snapshots`, `self.prev_nav`, `self.starting_cash`
  - `log(algorithm, pcm, data)` — the snapshot portion of current `log_daily()`
  - Does NOT handle positions, trades, targets — those are separate loggers

**`loggers/position_logger.py`** (Molecule):
- Class `PositionLogger` with:
  - `__init__()` — holds `self.positions`, `self.trades`, `self.prev_positions`, `self.prev_symbol_totals`
  - `log(algorithm, current_date, nav)` — current `_log_positions()` logic
  - The close-detection logic stays here (trades list)

**`loggers/signal_logger.py`** (Molecule):
- Class `SignalLogger` with:
  - `__init__()` — holds `self.signals`
  - `log(date, symbol, direction, magnitude, price, sma_short, sma_medium, sma_long, atr)` — current `log_signal()` logic

**`loggers/slippage_logger.py`** (Molecule):
- Class `SlippageLogger` with:
  - `__init__()` — holds `self.slippage`, `self.daily_slippage`, `self.last_slippage_date`
  - `log(date, symbol, direction, quantity, expected_price, fill_price)` — current `log_slippage()` logic
  - Property `daily_slippage_amount` for snapshot logger to read

**`loggers/order_event_logger.py`** (Molecule):
- Class `OrderEventLogger` with:
  - `__init__()` — holds `self.order_events`
  - `log(date, order_id, symbol, status, direction, quantity, fill_quantity, fill_price, order_type, limit_price, market_price_at_submit, tag)` — current `log_order_event()` logic

**`loggers/target_logger.py`** (Molecule):
- Class `TargetLogger` with:
  - `__init__()` — holds `self.targets`
  - `log(algorithm, pcm, current_date)` — current `_log_targets()` logic

**`loggers/portfolio_logger.py`** (Organism / Facade):
```python
from loggers.snapshot_logger import SnapshotLogger
from loggers.position_logger import PositionLogger
from loggers.signal_logger import SignalLogger
from loggers.slippage_logger import SlippageLogger
from loggers.order_event_logger import OrderEventLogger
from loggers.target_logger import TargetLogger
from loggers.csv_writer import save_to_objectstore


class PortfolioLogger:
    """Facade that composes all sub-loggers. Drop-in replacement for the original."""

    def __init__(self):
        self.snapshot_logger = SnapshotLogger()
        self.position_logger = PositionLogger()
        self.signal_logger = SignalLogger()
        self.slippage_logger = SlippageLogger()
        self.order_event_logger = OrderEventLogger()
        self.target_logger = TargetLogger()

    # --- Public API (identical signatures to original) ---

    @property
    def starting_cash(self):
        return self.snapshot_logger.starting_cash

    @property
    def slippage(self):
        """For len(self.logger.slippage) in main.py OnEndOfAlgorithm."""
        return self.slippage_logger.slippage

    @property
    def daily_slippage(self):
        return self.slippage_logger.daily_slippage_amount

    def log_daily(self, algorithm, pcm, data=None):
        self.snapshot_logger.log(algorithm, pcm, data, self.slippage_logger, self.position_logger)
        nav = algorithm.Portfolio.TotalPortfolioValue
        current_date = algorithm.Time.date()
        self.position_logger.log(algorithm, current_date, nav)
        self.target_logger.log(algorithm, pcm, current_date)

    def log_signal(self, **kwargs):
        self.signal_logger.log(**kwargs)

    def log_slippage(self, **kwargs):
        self.slippage_logger.log(**kwargs)

    def log_order_event(self, **kwargs):
        self.order_event_logger.log(**kwargs)

    def save_to_objectstore(self, algorithm):
        """Save all sub-logger data to ObjectStore as CSV files."""
        counts = {}
        counts['snapshots'] = save_to_objectstore(algorithm, "wolfpack/daily_snapshots.csv",
            self.snapshot_logger.snapshots,
            ['date', 'nav', 'cash', 'gross_exposure', 'net_exposure',
             'long_exposure', 'short_exposure', 'daily_pnl', 'cumulative_pnl',
             'daily_slippage', 'num_positions', 'estimated_vol'])
        counts['positions'] = save_to_objectstore(algorithm, "wolfpack/positions.csv",
            self.position_logger.positions,
            ['date', 'symbol', 'invested', 'quantity', 'price', 'market_value', 'weight',
             'unrealized_pnl', 'daily_pnl', 'daily_unrealized_pnl', 'daily_realized_pnl',
             'daily_fees', 'daily_dividends', 'daily_total_net_pnl', 'avg_price'])
        counts['trades'] = save_to_objectstore(algorithm, "wolfpack/trades.csv",
            self.position_logger.trades,
            ['date', 'symbol', 'action', 'quantity', 'avg_price', 'exit_price', 'realized_pnl'])
        counts['signals'] = save_to_objectstore(algorithm, "wolfpack/signals.csv",
            self.signal_logger.signals,
            ['date', 'symbol', 'direction', 'magnitude', 'price',
             'sma_short', 'sma_medium', 'sma_long', 'atr'])
        counts['slippage'] = save_to_objectstore(algorithm, "wolfpack/slippage.csv",
            self.slippage_logger.slippage,
            ['date', 'symbol', 'direction', 'quantity',
             'expected_price', 'fill_price', 'slippage_dollars'])
        counts['targets'] = save_to_objectstore(algorithm, "wolfpack/targets.csv",
            self.target_logger.targets,
            ['date', 'week_id', 'symbol', 'start_w', 'weekly_target_w',
             'scheduled_fraction', 'scheduled_w', 'actual_w', 'scale_day'])
        counts['order_events'] = save_to_objectstore(algorithm, "wolfpack/order_events.csv",
            self.order_event_logger.order_events,
            ['date', 'order_id', 'symbol', 'status', 'direction',
             'quantity', 'fill_quantity', 'fill_price',
             'order_type', 'limit_price', 'market_price_at_submit', 'tag'])

        algorithm.Debug(
            f"ObjectStore: Saved {counts['snapshots']} snapshots, "
            f"{counts['positions']} position records, "
            f"{counts['trades']} trades, "
            f"{counts['signals']} signals, "
            f"{counts['slippage']} slippage records, "
            f"{counts['targets']} target-state rows, "
            f"{counts['order_events']} order events")
```

### Transition Strategy
- Create all files in `loggers/`
- Update `loggers/__init__.py` to export `PortfolioLogger`
- Keep `models/logger.py` temporarily as:
```python
# Backward compatibility — will be removed in Phase 11
from loggers.portfolio_logger import PortfolioLogger
```
- Do NOT change imports in `main.py`, `alpha.py`, etc. yet

### Backtest
```bash
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Atomic Phase 7 - Break logger into sub-loggers"
```

### Success Criteria
- Backtest results **identical** to Phase 0
- `models/logger.py` now re-exports from `loggers/portfolio_logger.py`
- All sub-logger files exist and are imported by the facade
- The facade's public API matches the original `PortfolioLogger` exactly

### Commit
```bash
git add loggers/ models/logger.py
git commit -m "Phase 7: Break logger into sub-loggers with PortfolioLogger facade"
```

---

## Phase 8: Create Signal Domain (`signals/`)

### What
Create `signals/trend.py` (molecule) containing signal computation logic, and `signals/alpha.py` (organism) as the LEAN AlphaModel wrapper. Wire them to use `core/` atoms.

### New Files

**`signals/trend.py`** (Molecule):
- Contains `TrendSignalComputer` class (or just functions) that:
  - Manages indicator creation and readiness checks
  - Calls `compute_composite_signal()` from `core/math_utils`
  - Returns a dict of `{symbol: Signal}` dataclasses
  - Does NOT emit Insights (that's the organism's job)

**`signals/alpha.py`** (Organism):
- `CompositeTrendAlphaModel(AlphaModel)` — same class name, same interface
  - Uses `TrendSignalComputer` from `signals/trend.py` internally
  - Manages rebalance counter, cached signals, daily emission logic
  - Emits LEAN Insight objects
  - Sets `pcm.is_rebalance_day` flag (unchanged coupling)
  - Calls `logger.log_signal()` (unchanged coupling)

### Transition Strategy
- Create files in `signals/`
- Update `signals/__init__.py`:
```python
from .alpha import CompositeTrendAlphaModel
```
- Keep `models/alpha.py` as a re-export:
```python
# Backward compatibility — will be removed in Phase 11
from signals.alpha import CompositeTrendAlphaModel
```
- Do NOT change `main.py` imports yet

### Backtest
```bash
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Atomic Phase 8 - Create signals domain"
```

### Success Criteria
- Backtest results **identical** to Phase 0
- Signal computation extracted to `signals/trend.py`
- LEAN wrapper in `signals/alpha.py`
- `models/alpha.py` is a thin re-export

### Commit
```bash
git add signals/ models/alpha.py
git commit -m "Phase 8: Create signals domain with trend molecule and alpha organism"
```

---

## Phase 9: Create Risk Domain (`risk/`)

### What
Create the risk domain with molecules for constraints, vol estimation, and scaling, plus the portfolio organism.

### New Files

**`risk/constraints.py`** (Molecule):
- Thin wrappers or re-exports from `core/math_utils`:
```python
from core.math_utils import apply_per_name_cap, apply_gross_cap, apply_net_cap
```
- This exists so the portfolio organism imports from its own domain, not directly from core

**`risk/vol_estimator.py`** (Molecule):
- Class `VolEstimator` that:
  - Manages `rolling_returns` and `prev_close` state
  - Has `update_returns(data, symbols)` method
  - Has `estimate_vol(weights)` method that calls `core.math_utils.estimate_portfolio_vol`
  - Encapsulates the RollingWindow → list conversion

**`risk/scaling.py`** (Molecule):
- Contains scaling schedule logic:
  - `ScalingScheduler` class with pre-built schedules
  - `get_schedule(signal_strength)` method
  - `get_current_fraction(symbol, scale_day, signal_strengths)` method
  - `initialize_week_plan(algorithm, weekly_targets)` method
  - `get_daily_target_state(algorithm, weekly_targets, ...)` method

**`risk/portfolio.py`** (Organism):
- `TargetVolPortfolioConstructionModel(PortfolioConstructionModel)` — same class, same interface
  - Uses `VolEstimator`, `ScalingScheduler`, and constraint functions internally
  - `CreateTargets()`, `UpdateReturns()`, `OnSecuritiesChanged()` unchanged public API
  - Still exposes `signal_strengths`, `current_week_id`, `expected_prices` as attributes (other models read these)

### Transition Strategy
- Create files in `risk/`
- Update `risk/__init__.py`:
```python
from .portfolio import TargetVolPortfolioConstructionModel
```
- Keep `models/portfolio.py` as re-export
- Do NOT change `main.py` yet

### Backtest
```bash
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Atomic Phase 9 - Create risk domain"
```

### Success Criteria
- Backtest results **identical** to Phase 0
- Vol estimation, constraints, and scaling extracted to molecules
- Portfolio organism composes molecules
- `models/portfolio.py` is a thin re-export

### Commit
```bash
git add risk/ models/portfolio.py
git commit -m "Phase 9: Create risk domain with vol, constraints, scaling, and portfolio organism"
```

---

## Phase 10: Create Execution Domain (`execution/`)

### What
Create the execution domain with molecules for pricing and cancellation, plus the execution organism.

### New Files

**`execution/pricing.py`** (Molecule):
- Contains signal-strength tier classification:
```python
def classify_signal_tier(signal_strength, strong_threshold, moderate_threshold):
    """Classify signal strength into execution tier."""
    if signal_strength >= strong_threshold:
        return "strong"
    elif signal_strength >= moderate_threshold:
        return "moderate"
    else:
        return "weak"

def get_offset_for_tier(tier, strong_offset, moderate_offset, weak_offset):
    """Get limit price offset percentage for a given tier."""
    ...
```
- Re-exports `compute_limit_price` from core

**`execution/cancellation.py`** (Molecule):
- Contains cancellation logic extracted from the execution model:
  - `cancel_stale_orders_signal_aware(open_tickets, order_week_ids, current_week_id, ...)` — returns list of tickets to cancel
  - `cancel_stale_orders_legacy(open_tickets, limit_open_checks, max_checks)` — returns list of tickets to cancel
  - These are **pure decision functions** — they return what to cancel, the organism does the actual `ticket.Cancel()`

**`execution/execution.py`** (Organism):
- `SignalStrengthExecutionModel(ExecutionModel)` — same class, same interface
  - Uses `pricing.py` and `cancellation.py` molecules internally
  - Manages state: `open_limit_tickets`, `limit_open_checks`, `order_week_ids`, `market_price_at_submit`
  - Still exposes `market_price_at_submit` dict and `cancel_stale_orders()` method

### Naming Note
The `execution/` directory will shadow the old `models/execution.py` import path. Since `main.py` still imports from `models/`, and `models/execution.py` will re-export from `execution/execution.py`, this works. But be careful with circular imports.

### Transition Strategy
- Create files in `execution/`
- Update `execution/__init__.py`:
```python
from .execution import SignalStrengthExecutionModel
```
- Keep `models/execution.py` as re-export
- Do NOT change `main.py` yet

### Backtest
```bash
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Atomic Phase 10 - Create execution domain"
```

### Success Criteria
- Backtest results **identical** to Phase 0
- Pricing and cancellation logic extracted to molecules
- Execution organism composes molecules
- `models/execution.py` is a thin re-export

### Commit
```bash
git add execution/ models/execution.py
git commit -m "Phase 10: Create execution domain with pricing, cancellation, and execution organism"
```

---

## Phase 11: Rewire `main.py` and Remove `models/`

### What
Update `main.py` to import from the new domain packages instead of `models/`. Then delete the `models/` directory entirely.

### Changes to `main.py`

Replace the imports:
```python
# OLD
from models import DOW30, CompositeTrendAlphaModel, TargetVolPortfolioConstructionModel, SignalStrengthExecutionModel, PortfolioLogger

# NEW
from core import DOW30
from signals import CompositeTrendAlphaModel
from risk import TargetVolPortfolioConstructionModel
from execution import SignalStrengthExecutionModel
from loggers import PortfolioLogger
```

### Delete `models/`
After verifying `main.py` works with new imports, delete:
- `models/__init__.py`
- `models/universe.py`
- `models/alpha.py`
- `models/portfolio.py`
- `models/execution.py`
- `models/logger.py`

### Update `claude.md`
Update the "Project Structure" section to reflect the new directory layout.

### Backtest
```bash
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Atomic Phase 11 - Rewire main.py, remove models/"
```

### Success Criteria
- Backtest results **identical** to Phase 0
- `models/` directory completely removed
- `main.py` imports from `core/`, `signals/`, `risk/`, `execution/`, `loggers/`
- `claude.md` updated with new structure
- No broken imports, no circular dependencies

### Commit
```bash
git add -A
git commit -m "Phase 11: Rewire main.py to new domain structure, remove legacy models/"
```

---

## Phase 12: Adopt Typed Dataclasses

### What
Replace plain `dict` usage in logging and data passing with the dataclasses from `core/types.py`. This is the final structural improvement.

### Changes

1. **Signal flow**: `_compute_signals()` in `signals/trend.py` returns `Signal` dataclasses instead of `(direction, magnitude)` tuples. The alpha organism converts to `Insight` objects.

2. **Logger inputs**: Each sub-logger's `log()` method accepts the corresponding dataclass:
   - `signal_logger.log(signal: Signal)` instead of keyword args
   - `slippage_logger.log(record: SlippageRecord)` instead of keyword args
   - `order_event_logger.log(event: OrderEventRecord)` instead of keyword args
   - `position_logger` and `snapshot_logger` may continue using algorithm data directly (they read from `algorithm.Portfolio`)

3. **Target state**: `get_daily_target_state()` returns `List[TargetState]` instead of `List[Dict]`.

4. **CSV output**: Update `build_csv()` in `core/formatting.py` to accept either dicts or dataclasses:
```python
from dataclasses import asdict

def build_csv(data, columns):
    """Build CSV from list of dicts or dataclasses."""
    lines = [','.join(columns)]
    for row in data:
        if hasattr(row, '__dataclass_fields__'):
            row = asdict(row)
        values = [str(row.get(col, '')) for col in columns]
        lines.append(','.join(values))
    return '\n'.join(lines)
```

5. **Execution order records**: The execution model can use `OrderRecord` internally to track open orders instead of separate dicts (`limit_open_checks`, `order_week_ids`, `market_price_at_submit`). This consolidates 3 tracking dicts into one `{order_id: OrderRecord}` dict.

### Backtest
```bash
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Atomic Phase 12 - Typed dataclasses"
```

### Success Criteria
- Backtest results **identical** to Phase 0
- Dataclasses used for signal flow, logging inputs, and target state
- Execution model uses `OrderRecord` for tracking
- CSV output unchanged (same columns, same values)

### Commit
```bash
git add -A
git commit -m "Phase 12: Adopt typed dataclasses from core/types.py throughout codebase"
```

---

## Phase 13: Final Cleanup and Documentation

### What
Final polish: remove any unused code, verify import hygiene, update all documentation.

### Steps

1. **Verify import rule compliance:**
   - `core/` has zero imports from any domain directory
   - Molecules only import from `core/`
   - Organisms import from `core/` and molecules within their own domain
   - `main.py` imports only from domain `__init__.py` files

2. **Remove unused imports and dead code** across all files.

3. **Update `claude.md`** with:
   - New project structure
   - Updated module descriptions
   - New import patterns
   - Any changed parameter locations

4. **Update `CC_Atomic.md`** (this file) to mark all phases as complete.

5. **Verify `.gitignore`** still correctly excludes `config.json`, `__pycache__/`, etc.

6. **Run final verification backtest:**

### Backtest
```bash
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Atomic Phase 13 - Final cleanup"
```

### Success Criteria
- Backtest results **identical** to Phase 0
- Clean import graph with no violations
- Updated documentation
- No unused code

### Commit
```bash
git add -A
git commit -m "Phase 13: Final cleanup, documentation, and import verification"
```

---

## Final Comparison

After all phases, the `backtest_results/comparison.md` should show **identical metrics across all 14 rows** (Phase 0 through Phase 13). Any deviation indicates a regression that must be investigated before proceeding.

### Expected Final Structure

```
WolfpackTrend 1/
├── main.py
├── claude.md
├── CC_Atomic.md
├── backtest_results/
│   ├── comparison.md
│   ├── phase0_baseline.txt
│   └── ... (one file per phase)
│
├── core/
│   ├── __init__.py
│   ├── universe.py
│   ├── types.py
│   ├── math_utils.py
│   └── formatting.py
│
├── signals/
│   ├── __init__.py
│   ├── trend.py
│   └── alpha.py
│
├── risk/
│   ├── __init__.py
│   ├── constraints.py
│   ├── vol_estimator.py
│   ├── scaling.py
│   └── portfolio.py
│
├── execution/
│   ├── __init__.py
│   ├── pricing.py
│   ├── cancellation.py
│   └── execution.py
│
└── loggers/
    ├── __init__.py
    ├── csv_writer.py
    ├── snapshot_logger.py
    ├── position_logger.py
    ├── signal_logger.py
    ├── slippage_logger.py
    ├── order_event_logger.py
    ├── target_logger.py
    └── portfolio_logger.py
```

### Running the Backtest Between Phases (Quick Reference)

Every phase uses the same commands:
```bash
cd ~/Documents/QuantConnect
source venv/bin/activate
cd MyProjects
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Atomic Phase N - Description" 2>&1 | tee "/Users/graham/Documents/QuantConnect/MyProjects/WolfpackTrend 1/backtest_results/phaseN.txt"
```

Then update `backtest_results/comparison.md` with the results.

---

## Rollback Strategy

If any phase produces different backtest results:

1. **Do NOT proceed to the next phase**
2. Compare the phase's backtest output with Phase 0 baseline
3. Use `git diff` to see exactly what changed
4. The most likely culprits:
   - Float precision differences (rounding in extracted functions)
   - Missing state initialization
   - Import order affecting QC's module resolution
   - `RollingWindow` → list conversion losing data
5. Fix the issue and re-run the backtest
6. If stuck, revert the phase commit with `git revert HEAD` (safe — preserves history and won't wipe unrelated local work)

---

## Notes for Claude Code Executor

- **Always read a file before editing it.** Do not guess at file contents.
- **One phase at a time.** Complete the phase, run the backtest, verify results, commit, then move on.
- **Preserve exact behavior.** The extracted functions must produce bit-for-bit identical results. Pay special attention to:
  - `max(atr_value, 1e-8)` clamping
  - `round(..., 4)` calls
  - `schedule[-1] = 1.0` forced last element
  - The order of constraint application (per-name → gross → net)
- **QC cloud imports:** Files on QC cloud are flat (no directories). `lean cloud push` handles directory structure, but verify that QC resolves imports correctly. If it doesn't, you may need to add the project root to `sys.path` or use relative imports within each domain.
- **The directory is `loggers/` not `logging/`** to avoid shadowing Python's built-in `logging` module. This is enforced from Phase 1 onward.
- **`backtest_results/`** is tracked in git on the `Atomic_Refactor` branch to document the verification process. Add `backtest_results/` to `.gitignore` in Phase 13 after the refactor is merged to main.
