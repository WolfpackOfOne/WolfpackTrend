# WolfpackTrend — Signal-Strength Execution & Daily Position Scaling

## Implementation Plan

**Branch:** `feature/trading-logic`
**Created:** 2026-02-05
**Status:** Planning (Rev 2 — incorporates review feedback)

---

## Table of Contents

1. [Objective](#objective)
2. [Current Architecture](#current-architecture)
3. [Design Overview](#design-overview)
4. [Detailed Component Changes](#detailed-component-changes)
   - [Alpha Model](#41-alpha-model-changes)
   - [Portfolio Construction Model](#42-portfolio-construction-model-changes)
   - [Custom Execution Model](#43-custom-execution-model-new-file)
   - [Module Init](#44-module-init-changes)
   - [Main Algorithm](#45-main-algorithm-changes)
5. [Signal-Strength Order Type Logic](#signal-strength-order-type-logic)
6. [Daily Scaling Into Weekly Targets](#daily-scaling-into-weekly-targets)
7. [Unfilled Limit Order Handling](#unfilled-limit-order-handling)
8. [Parameter Reference](#parameter-reference)
9. [Data Flow Walkthrough](#data-flow-walkthrough)
10. [Edge Cases and Mitigations](#edge-cases-and-mitigations)
11. [Implementation Order](#implementation-order)
12. [Verification and Testing](#verification-and-testing)

---

## Review Findings Addressed (Rev 2)

| # | Finding | Fix |
|---|---------|-----|
| 1 | Hardcoded 5-element schedules break if `scaling_days != 5` | Generate schedules dynamically from a formula based on `scaling_days` |
| 2 | `signal_strengths[symbol]` KeyError for symbols not in the map | Use `.get(symbol, default)` with a configurable fallback (defaults to moderate) |
| 3 | Overloading `Insight.SourceModel` breaks LEAN semantics | Replace with a shared `is_rebalance_day` boolean flag on the PCM, set by the alpha model |
| 4 | Cancelling orders inside `Execute()` then calling `GetUnorderedQuantity()` may still count cancel-pending orders | Move cancellation to a `Schedule.On()` event at market open in `main.py`, before `Execute()` is called |
| 5 | `weekly_targets` / `signal_strengths` persist for removed symbols | Clean up both maps in PCM's `OnSecuritiesChanged` when securities are removed |
| 6 | `round(price, 2)` assumes 2-decimal tick size | Use `security.SymbolProperties.MinimumPriceVariation` for tick-aware rounding |
| 7 | Calendar-day rebalance vs trading-day scaling causes under-exposure on holiday weeks | Switch rebalance interval to trading-day counter (increment only when `Update()` runs) |

---

## Objective

Enhance the WolfpackTrend strategy with two new capabilities:

1. **Signal-strength-based order types**: Instead of using market orders for everything, the execution model will choose between market orders and limit orders based on how strong the alpha signal is. Strong signals trade aggressively at market price. Weak signals place patient limit orders that only fill if the price moves favorably.

2. **Daily scaling into weekly targets**: Instead of executing the full portfolio rebalance in a single day, positions will scale into their target weights gradually over the trading week. The pace of scaling depends on signal strength — strong signals scale in faster, weak signals spread evenly.

---

## Current Architecture

The strategy currently uses QuantConnect LEAN's framework architecture:

```
Alpha Model ──→ Portfolio Construction Model ──→ Execution Model
(signals)        (target weights)                 (orders)
```

### Current Alpha Model (`models/alpha.py`)
- Emits insights once per `rebalance_interval_days` (currently 7 = weekly)
- Each insight carries a signal magnitude = `tanh(composite_score)` bounded in (-1, +1)
- Signal magnitude is stored as both `insight.Weight` and `insight.Confidence`
- Signals below `min_magnitude=0.05` are filtered out
- The composite score is a weighted combination of 3 SMA-normalized distances:
  - Short (20-day): weight 0.5
  - Medium (63-day): weight 0.3
  - Long (252-day): weight 0.2
- Each distance is normalized by ATR(14) for cross-stock comparability

### Current Portfolio Construction Model (`models/portfolio.py`)
- Receives insights, extracts `Weight` and `Direction`
- Normalizes weights to unit gross exposure (proportional to signal magnitude)
- Estimates portfolio volatility using 63-day diagonal approximation (ignores correlations)
- Scales all weights to target 10% annualized volatility
- Applies constraints in order: per-name cap (10%) → gross cap (150%) → net cap (50%)
- Returns `PortfolioTarget.Percent()` for each position
- Exits positions that no longer have signals

### Current Execution Model (`main.py` line 81)
- Uses `ImmediateExecutionModel()` — submits market orders for all targets immediately
- No consideration of signal strength or order type differentiation

### Current Pipeline Trigger
- `RebalancePortfolioOnInsightChanges = True` (line 84)
- Pipeline triggers whenever the alpha model emits new insights
- Currently: insights emitted weekly → execution happens weekly in a single batch

---

## Design Overview

### Core Design Decision: Alpha Emits Daily, Recalculates Weekly

The key challenge is that LEAN's pipeline (Alpha → PCM → Execution) only triggers the execution model when the alpha model emits new insights. Currently, insights are emitted weekly, so execution only happens weekly.

To achieve daily execution with weekly signal recalculation, we modify the alpha model to **emit insights every trading day**, but only **recalculate signals weekly**. On non-rebalance days, the alpha model re-emits its cached signals from the last rebalance.

This approach works entirely within LEAN's framework — no scheduled events or workarounds needed. The daily emission triggers the full pipeline daily:

```
Every Trading Day:
  Alpha emits insights (fresh or cached)
    → PCM receives insights, computes today's scaling target
      → Execution model submits orders (market or limit based on signal strength)
```

### How Components Know Rebalance vs Scaling Day

**[Rev 2 fix — Finding #3]:** Instead of overloading `Insight.SourceModel` (which LEAN intends to identify the generating alpha model), we use a **shared boolean flag on the PCM**:

```python
# Alpha sets this each day before emitting insights:
algorithm.pcm.is_rebalance_day = True  # or False

# PCM reads it in CreateTargets():
if self.is_rebalance_day:
    # Full weight computation
else:
    # Scaling day — increment and emit partial targets
```

This avoids breaking LEAN semantics, keeps `SourceModel` available for its intended purpose (identifying alpha models), and works cleanly for our single-alpha setup.

### Rebalance and Scaling Both Use Trading-Day Counters

**[Rev 2 fix — Finding #7]:** Both the rebalance interval and the scaling window now count **trading days** (days when `Update()` actually runs), not calendar days. This guarantees the scaling window always reaches 100% before the next rebalance, even during holiday weeks.

```python
# Alpha model:
self.trading_days_since_rebalance = 0  # incremented each day Update() runs

# Rebalance when:
if self.trading_days_since_rebalance >= self.rebalance_interval_trading_days:
    # time to rebalance
```

With `rebalance_interval_trading_days=5` and `scaling_days=5`, the scaling window and rebalance interval are guaranteed to align regardless of holidays.

---

## Detailed Component Changes

### 4.1 Alpha Model Changes

**File:** `models/alpha.py`

**What changes:**

The alpha model currently has a single `last_emit_date` field and skips all days within the rebalance interval. We split this into two concerns:

1. **Rebalance tracking** (`trading_days_since_rebalance`): Controls when signals are recalculated
2. **Daily emission** (`last_emit_date`): Ensures we emit exactly once per trading day

**New/changed constructor parameters:**
```python
rebalance_interval_trading_days=5  # Renamed from rebalance_interval_days; now counts trading days
```

**New state variables added to `__init__`:**
```python
self.cached_signals = {}                    # symbol -> (direction, magnitude)
self.trading_days_since_rebalance = None    # None = first day; int = trading days since last rebalance
```

**Modified `Update()` logic:**

```
1. Check if we already emitted today (prevent duplicate emission on intraday calls)
   - If last_emit_date == current_date → return empty
   - Set last_emit_date = current_date

2. Determine if this is a rebalance day (TRADING-DAY counter):
   - If trading_days_since_rebalance is None → rebalance (first time)
   - If trading_days_since_rebalance >= rebalance_interval_trading_days → rebalance
   - Otherwise → scaling day; increment trading_days_since_rebalance

3. If rebalance day:
   - Set trading_days_since_rebalance = 0
   - Clear cached_signals
   - Run full signal computation (existing lines 55-124)
   - Store results in cached_signals
   - Set algorithm.pcm.is_rebalance_day = True

4. If scaling day:
   - Increment trading_days_since_rebalance
   - Set algorithm.pcm.is_rebalance_day = False

5. Emit insights for all cached signals:
   - For each symbol in cached_signals:
     - Check data bar exists for this symbol today
     - Create Insight.Price() with:
       - period = timedelta(days=1)  ← changed from rebalance_interval_days
       - SourceModel = None  ← leave as-is, not overloaded
       - confidence = abs(magnitude)
       - weight = abs(magnitude)
   - Append to insights list

6. Log summary (existing debug logging, enhanced with day type)
   - "[2022-01-03] Alpha (rebalance): 22 signals (15 long, 7 short)"
   - "[2022-01-04] Alpha (scaling, day 1/5): 22 signals (cached)"
```

**Key differences from current code:**
- `last_emit_date` now prevents duplicate same-day emission (was preventing emission within the interval)
- `trading_days_since_rebalance` replaces calendar-day interval — counts only days when `Update()` runs
- `cached_signals` stores signals between rebalances
- Insights are emitted every day (not just on rebalance days)
- `is_rebalance_day` flag set on the PCM (not on `Insight.SourceModel`)
- Insight period changes from `rebalance_interval_days` to 1 day

---

### 4.2 Portfolio Construction Model Changes

**File:** `models/portfolio.py`

**What changes:**

The PCM gains the ability to differentiate rebalance days from scaling days and emit incremental targets.

**New constructor parameters:**
```python
scaling_days=5  # Number of trading days to scale into full position
```

**New state variables added to `__init__`:**
```python
self.scaling_days = scaling_days
self.weekly_targets = {}       # symbol -> final target weight from last rebalance
self.signal_strengths = {}     # symbol -> abs(magnitude) from last rebalance
self.current_scale_day = 0     # Which day of the scaling period (0-indexed)
self.is_rebalance_day = False  # Set by alpha model each day before CreateTargets runs
```

**Dynamically generated scaling schedules:**

**[Rev 2 fix — Finding #1]:** Instead of hardcoded 5-element lists, schedules are generated dynamically from `scaling_days` using a formula. This ensures correctness for any value of `scaling_days`.

```python
def _build_schedule(self, front_load_factor):
    """
    Generate a cumulative scaling schedule of length self.scaling_days.

    front_load_factor controls how front-loaded the schedule is:
      - 1.0 = even spread (linear: 1/N, 2/N, ..., 1.0)
      - >1.0 = front-loaded (power curve, reaches target faster early on)

    The last element is always 1.0 (reach 100% on final day).
    """
    n = self.scaling_days
    if n <= 1:
        return [1.0]

    # Generate schedule using power curve: (i/n)^(1/front_load_factor)
    # front_load_factor=1.0 → linear
    # front_load_factor=2.0 → sqrt curve (front-loaded)
    # front_load_factor=0.5 → square curve (back-loaded, not used)
    schedule = []
    exponent = 1.0 / front_load_factor
    for i in range(1, n + 1):
        fraction = (i / n) ** exponent
        schedule.append(round(fraction, 4))
    schedule[-1] = 1.0  # Guarantee final day = 100%
    return schedule
```

**Schedule generation in `__init__`:**
```python
# Strong: front_load_factor=2.0 → sqrt curve (50%, 71%, 87%, 94%, 100% for 5 days)
self.strong_schedule = self._build_schedule(front_load_factor=2.0)

# Moderate: front_load_factor=1.3 → mild front-load (30%, 50%, 69%, 85%, 100% for 5 days)
self.moderate_schedule = self._build_schedule(front_load_factor=1.3)

# Weak: front_load_factor=1.0 → linear (20%, 40%, 60%, 80%, 100% for 5 days)
self.weak_schedule = self._build_schedule(front_load_factor=1.0)
```

**Why this is better than hardcoded lists:**
- Works for any `scaling_days` value (3, 5, 7, 10, etc.)
- Always ends at 1.0 — guaranteed to reach 100% on the final day
- The shape is controlled by `front_load_factor`, which can be made configurable
- For `scaling_days=5`, produces nearly identical values to the original hardcoded schedules

**Example schedules for `scaling_days=5`:**
```
Day:               0      1      2      3      4
────────────────────────────────────────────────────
Strong (√curve):  45%    63%    77%    89%   100%
Moderate (1.3):   30%    50%    69%    85%   100%
Weak (linear):    20%    40%    60%    80%   100%
```

**Example schedules for `scaling_days=3` (holiday week or different config):**
```
Day:               0      1      2
──────────────────────────────────
Strong (√curve):  58%    82%   100%
Moderate (1.3):   42%    68%   100%
Weak (linear):    33%    67%   100%
```

**Schedule selection method:**
```python
def _get_scaling_schedule(self, signal_strength):
    if signal_strength >= 0.7:
        return self.strong_schedule
    elif signal_strength >= 0.3:
        return self.moderate_schedule
    else:
        return self.weak_schedule
```

**Modified `CreateTargets()` logic:**

```
1. Filter to active insights (existing)

2. Determine if rebalance or scaling day:
   - Read self.is_rebalance_day (set by alpha model)

3. If REBALANCE DAY:
   a. Reset current_scale_day = 0
   b. Run existing weight computation:
      - Convert insights to signed raw weights
      - Normalize to unit gross
      - Estimate portfolio volatility
      - Scale to target vol
      - Apply constraints (per-name → gross → net)
   c. Store result as weekly_targets
   d. Store signal strengths: signal_strengths[symbol] = insight.Weight

4. If SCALING DAY:
   a. Increment current_scale_day (capped at scaling_days - 1)

5. For each symbol in weekly_targets:
   a. Look up signal strength for this symbol
   b. Get the appropriate scaling schedule
   c. Look up cumulative fraction for current_scale_day
   d. Compute today's target = weekly_target * cumulative_fraction
   e. Create PortfolioTarget.Percent(algorithm, symbol, today_weight)

6. Exit positions not in weekly_targets (existing logic)
   - Always emit zero-weight targets for these

7. Store expected prices for slippage tracking (existing)

8. Log summary (existing debug logging, enhanced with scale day info)
```

**Universe removal cleanup:**

**[Rev 2 fix — Finding #5]:** When securities are removed, clean up the weekly_targets and signal_strengths maps so stale entries don't generate phantom targets:

```python
def OnSecuritiesChanged(self, algorithm, changes):
    for security in changes.AddedSecurities:
        symbol = security.Symbol
        self.symbols.add(symbol)
        if symbol not in self.rolling_returns:
            self.rolling_returns[symbol] = RollingWindow[float](self.vol_lookback)

    for security in changes.RemovedSecurities:
        symbol = security.Symbol
        self.symbols.discard(symbol)
        if symbol in self.rolling_returns:
            del self.rolling_returns[symbol]
        if symbol in self.prev_close:
            del self.prev_close[symbol]
        # [Rev 2] Clean up scaling state for removed symbols
        if symbol in self.weekly_targets:
            del self.weekly_targets[symbol]
        if symbol in self.signal_strengths:
            del self.signal_strengths[symbol]
```

**Why `PortfolioTarget.Percent` handles incremental scaling correctly:**

`PortfolioTarget.Percent(algorithm, symbol, weight)` sets an absolute target. LEAN's execution framework computes the delta between current holdings and the target. So:

- Day 0: target = 50% of final → execution model orders to get to 50%
- Day 1: target = 75% of final → current holdings are ~50%, execution orders the additional 25%
- Day 2: target = 88% of final → current is ~75%, execution orders the additional 13%

We don't need to compute deltas ourselves — LEAN handles this.

**Signal strength passing to execution model:**

The `signal_strengths` dictionary is stored as a property on the PCM. The execution model accesses it via `algorithm.pcm.signal_strengths.get(symbol, default)`.

---

### 4.3 Custom Execution Model (NEW FILE)

**File:** `models/execution.py`

**Purpose:** Replace `ImmediateExecutionModel` with a signal-strength-aware execution model that selects between market orders and limit orders.

**Constraint:** This strategy targets DOW30 US equities at daily resolution only.

**Class:** `SignalStrengthExecutionModel(ExecutionModel)`

**Constructor parameters:**
```python
strong_threshold=0.70           # Signal strength above this → market order
moderate_threshold=0.30         # Signal strength above this → limit at moderate offset
moderate_offset_pct=0.005       # 0.5% offset for moderate signals
weak_offset_pct=0.015           # 1.5% offset for weak signals
default_signal_strength=0.50    # Fallback when signal_strengths lookup misses
```

**State variables:**
```python
self.targets_collection = PortfolioTargetCollection()  # LEAN's built-in target tracker
self.open_limit_tickets = []  # Track open limit order tickets for cancellation
```

**Safe signal strength lookup:**

**[Rev 2 fix — Finding #2]:** The execution model never assumes a symbol exists in `signal_strengths`. It always uses `.get()` with a configurable default:

```python
def _get_signal_strength(self, algorithm, symbol):
    """
    Safely look up signal strength for a symbol.
    Returns default_signal_strength if not found (e.g., universe changes,
    constraints zeroing a symbol, missing data on rebalance day).
    """
    pcm = getattr(algorithm, 'pcm', None)
    if pcm is None:
        return self.default_signal_strength
    strengths = getattr(pcm, 'signal_strengths', {})
    return strengths.get(symbol, self.default_signal_strength)
```

This handles:
- Symbols created by constraint exits that were never in the signal set
- Universe changes between rebalance and execution
- Missing data on rebalance day preventing a symbol from getting a signal
- Any other edge case where signal_strengths doesn't have an entry

**`Execute(algorithm, targets)` method logic:**

```
1. Add new targets to targets_collection

2. For each target (ordered by margin impact):
   a. Compute unordered quantity using OrderSizing.GetUnorderedQuantity()
      - This gives the delta between current holdings and target
      - If delta is 0, skip (already at target)

   b. Get current market price for the symbol; skip if price <= 0

   c. Determine if this is an EXIT (unordered quantity reduces position to zero):
      - If exiting → always use market order (regardless of signal)

   d. Look up signal strength safely via _get_signal_strength()

   e. Select order type based on signal strength:
      - signal >= strong_threshold → MarketOrder(symbol, quantity)
      - signal >= moderate_threshold → LimitOrder at moderate_offset_pct
      - signal < moderate_threshold → LimitOrder at weak_offset_pct

   f. Track limit order tickets in open_limit_tickets list

3. Clear fulfilled targets from the collection
```

**Tick-size-aware limit price computation:**

**[Rev 2 fix — Finding #6]:** Instead of hardcoding `round(price, 2)`, use the security's minimum price variation for proper tick-size rounding:

```python
def _compute_limit_price(self, security, price, quantity, offset_pct):
    """
    Compute limit price with offset, rounded to the security's tick size.
    """
    if quantity > 0:
        # BUYING: set limit BELOW market
        raw_price = price * (1 - offset_pct)
    else:
        # SELLING/SHORTING: set limit ABOVE market
        raw_price = price * (1 + offset_pct)

    # Round to tick size
    tick = security.SymbolProperties.MinimumPriceVariation
    if tick > 0:
        return round(raw_price / tick) * tick
    return round(raw_price, 2)  # Fallback for DOW30 equities
```

**Examples:**
- Stock at $100, tick=$0.01, buying with moderate signal: limit = $99.50
- Stock at $100, tick=$0.01, selling with weak signal: limit = $101.50
- Stock at $100, buying with strong signal: market order (fills at ~$100)

**Stale order cancellation — done externally, not inside Execute():**

**[Rev 2 fix — Finding #4]:** Cancelling orders inside `Execute()` and then immediately calling `GetUnorderedQuantity()` risks the cancellation being "pending" but not yet reflected in LEAN's order accounting. Instead:

- **Cancellation happens in `main.py`** via a `Schedule.On()` event at market open, *before* the Alpha → PCM → Execute pipeline runs
- The execution model provides a `cancel_stale_orders()` method that `main.py` calls
- By the time `Execute()` runs later in the same time step, the cancellations have been processed

```python
def cancel_stale_orders(self, algorithm):
    """
    Cancel all tracked open limit orders. Called from main.py's
    scheduled event at market open, before the pipeline runs.
    """
    still_open = []
    for ticket in self.open_limit_tickets:
        if ticket.Status in (OrderStatus.Submitted, OrderStatus.PartiallyFilled):
            ticket.Cancel()
            algorithm.Debug(
                f"  Cancelled stale limit: {ticket.Symbol.Value} "
                f"qty={ticket.Quantity}"
            )
        if ticket.Status not in (OrderStatus.Filled, OrderStatus.Canceled, OrderStatus.Invalid):
            still_open.append(ticket)
    self.open_limit_tickets = still_open
```

**Order event cleanup:**

```python
def OnOrderEvent(self, algorithm, order_event):
    """Clean up filled/cancelled orders from tracking list."""
    if order_event.Status in (OrderStatus.Filled, OrderStatus.Canceled, OrderStatus.Invalid):
        self.open_limit_tickets = [
            t for t in self.open_limit_tickets
            if t.OrderId != order_event.OrderId
        ]
```

**Security removal handling:**

```python
def OnSecuritiesChanged(self, algorithm, changes):
    """Cancel open orders for removed securities."""
    for removed in changes.RemovedSecurities:
        symbol = removed.Symbol
        for ticket in self.open_limit_tickets:
            if ticket.Symbol == symbol and ticket.Status in (OrderStatus.Submitted, OrderStatus.PartiallyFilled):
                ticket.Cancel()
        self.open_limit_tickets = [
            t for t in self.open_limit_tickets if t.Symbol != symbol
        ]
```

---

### 4.4 Module Init Changes

**File:** `models/__init__.py`

Add the new execution model export:

```python
from .universe import DOW30
from .alpha import CompositeTrendAlphaModel
from .portfolio import TargetVolPortfolioConstructionModel
from .execution import SignalStrengthExecutionModel
from .logger import PortfolioLogger
```

---

### 4.5 Main Algorithm Changes

**File:** `main.py`

**Import changes:**
```python
from models import (DOW30, CompositeTrendAlphaModel,
                     TargetVolPortfolioConstructionModel,
                     SignalStrengthExecutionModel, PortfolioLogger)
```

**Alpha model** (parameter renamed from `rebalance_interval_days` to `rebalance_interval_trading_days`):
```python
self.SetAlpha(CompositeTrendAlphaModel(
    short_period=20,
    medium_period=63,
    long_period=252,
    atr_period=14,
    rebalance_interval_trading_days=5,  # Trading days, not calendar days
    logger=self.logger,
    algorithm=self
))
```

**PCM** (new `scaling_days` parameter):
```python
self.pcm = TargetVolPortfolioConstructionModel(
    target_vol_annual=0.10,
    max_gross=1.50,
    max_net=0.50,
    max_weight=0.10,
    vol_lookback=63,
    scaling_days=5,
    algorithm=self
)
```

**Execution model** (replaces `ImmediateExecutionModel`):
```python
self.execution_model = SignalStrengthExecutionModel(
    strong_threshold=0.70,
    moderate_threshold=0.30,
    moderate_offset_pct=0.005,
    weak_offset_pct=0.015,
    default_signal_strength=0.50
)
self.SetExecution(self.execution_model)
```

**Scheduled stale order cancellation:**

**[Rev 2 fix — Finding #4]:** Cancel stale limit orders at market open, before the pipeline runs:

```python
# In Initialize():
self.Schedule.On(
    self.DateRules.EveryDay(),
    self.TimeRules.AfterMarketOpen("SPY", 0),  # At market open
    self._cancel_stale_orders
)

# New method:
def _cancel_stale_orders(self):
    """Cancel unfilled limit orders from previous days before today's pipeline runs."""
    self.execution_model.cancel_stale_orders(self)
```

**Framework settings** (unchanged — `RebalancePortfolioOnInsightChanges = True` is what triggers the daily pipeline since the alpha now emits daily).

**Debug logging updates:**
```python
self.Debug("Alpha: Composite Trend (SMA 20/63/252, ATR 14, weekly rebalance, daily emission)")
self.Debug(f"Execution: Signal-strength based (strong>=0.70→market, moderate>=0.30→limit 0.5%, weak→limit 1.5%)")
self.Debug(f"Scaling: 5 trading days (strong front-loaded, weak even)")
```

---

## Signal-Strength Order Type Logic

### How Signal Strength Maps to Order Types

The alpha model produces a signal magnitude via `tanh(composite_score)`. The absolute value of this magnitude (ranging from 0.05 to ~1.0) determines the order type:

```
Signal Strength    Order Type       Limit Offset    Reasoning
─────────────────────────────────────────────────────────────
≥ 0.70 (strong)    Market order     N/A             High conviction → fill immediately
0.30–0.70 (mod)    Limit order      0.5% away       Moderate conviction → small patience
0.05–0.30 (weak)   Limit order      1.5% away       Low conviction → price must come to us
Exit (weight=0)    Market order     N/A             Always exit immediately
Unknown/missing    Limit order      0.5% away       Safe default (moderate tier)
```

### Why This Makes Sense

- **Strong signals** represent stocks where price is far above/below all three SMAs. The trend is clear and we want to be in the position immediately.
- **Moderate signals** represent moderate trends. We're willing to wait for a slightly better entry.
- **Weak signals** represent marginal trends close to the threshold. We only want to enter if the market gives us a discount, reducing the cost of being wrong.
- **Unknown/missing** signals (from constraints, universe changes, etc.) default to moderate behavior — patient but not excessively cautious.

### Limit Order Fill Probability

With daily resolution data in QuantConnect:
- LEAN checks if the limit price falls within the bar's [Low, High] range
- A 0.5% offset from yesterday's close will frequently be touched (high fill rate)
- A 1.5% offset will sometimes miss (lower fill rate — this is intentional)
- Unfilled orders are cancelled at market open and re-evaluated when the pipeline runs

---

## Daily Scaling Into Weekly Targets

### How Scaling Works

On each rebalance day, the PCM computes full target weights for the week. Instead of executing all at once, positions scale into their targets over `scaling_days` trading days.

### Dynamically Generated Scaling Schedules

**[Rev 2 fix — Finding #1]:** Schedules are generated from a formula, not hardcoded. The `front_load_factor` parameter controls the curve shape:

```
front_load_factor=1.0 → linear (even spread)
front_load_factor=1.3 → mild front-load (moderate signals)
front_load_factor=2.0 → sqrt curve (strong signals — aggressive early)
```

**Formula:** `fraction[i] = ((i+1) / scaling_days) ^ (1/front_load_factor)`

### Example Schedules for `scaling_days=5`

Each schedule shows the cumulative fraction of the weekly target that should be in place by that day:

```
Day:               0      1      2      3      4
────────────────────────────────────────────────────
Strong (√curve):  45%    63%    77%    89%   100%
Moderate (1.3):   30%    50%    69%    85%   100%
Weak (linear):    20%    40%    60%    80%   100%
```

### Example Schedules for `scaling_days=3` (or a holiday week if adapted)

```
Day:               0      1      2
──────────────────────────────────
Strong (√curve):  58%    82%   100%
Moderate (1.3):   42%    68%   100%
Weak (linear):    33%    67%   100%
```

### Concrete Example

Suppose on rebalance day the PCM calculates that AAPL should have a final weight of +6% (long):

**If AAPL's signal strength is 0.85 (strong):**
- Day 0: Target = 6% × 0.45 = 2.7% → Market order to get to 2.7%
- Day 1: Target = 6% × 0.63 = 3.78% → Market order for additional ~1.1%
- Day 2: Target = 6% × 0.77 = 4.62% → Market order for additional ~0.84%
- Day 3: Target = 6% × 0.89 = 5.34% → Market order for additional ~0.72%
- Day 4: Target = 6% × 1.00 = 6.0% → Market order for final ~0.66%

**If AAPL's signal strength is 0.15 (weak):**
- Day 0: Target = 6% × 0.20 = 1.2% → Limit order at 1.5% below market
- Day 1: Target = 6% × 0.40 = 2.4% → Limit order at 1.5% below market
- Day 2: Target = 6% × 0.60 = 3.6% → Limit order at 1.5% below market
- Day 3: Target = 6% × 0.80 = 4.8% → Limit order at 1.5% below market
- Day 4: Target = 6% × 1.00 = 6.0% → Limit order at 1.5% below market

Note: Weak signal limit orders may not fill every day (1.5% offset). If an order doesn't fill on Day 1, the Day 2 target is 3.6% but we might only have 1.2% in place. LEAN computes the gap and submits a larger order on Day 2 to catch up. This creates a natural "if the price doesn't come to us, we accumulate more slowly" behavior.

---

## Unfilled Limit Order Handling

### The Problem

If a limit order doesn't fill today, it's still pending in LEAN's order system. The next day, the PCM emits a new (larger) target. LEAN's `OrderSizing.GetUnorderedQuantity()` accounts for pending orders, which could cause it to undercount what we need to order.

### The Solution: Cancel at Market Open via Scheduled Event

**[Rev 2 fix — Finding #4]:** Cancellation is done in a `Schedule.On()` event at market open in `main.py`, NOT inside `Execute()`. This ensures cancellations are processed before the Alpha → PCM → Execute pipeline runs:

```
Market Open (scheduled event):
  1. main.py._cancel_stale_orders() calls execution_model.cancel_stale_orders()
  2. All pending limit orders from previous days are cancelled
  3. LEAN processes the cancellations

Later in the same time step (pipeline triggered by daily bar):
  4. Alpha emits insights → PCM creates targets → Execute() runs
  5. GetUnorderedQuantity() sees no pending orders (they were already cancelled)
  6. Fresh orders submitted at today's prices
```

### Why This Is Better Than Cancelling Inside Execute()

Cancelling inside `Execute()` and immediately calling `GetUnorderedQuantity()` in the same method creates a race condition. The cancellation may be "submitted" but not yet "processed" by LEAN's order management system. By separating cancellation into an earlier scheduled event, we give LEAN time to process the cancellations before the execution model computes order quantities.

### What Happens to Partial Fills?

If a limit order was partially filled (e.g., 60 of 100 shares):
- The 60 shares are in the portfolio
- The remaining 40-share order is cancelled at market open
- When the pipeline runs, the new target might be for 150 shares total
- `GetUnorderedQuantity` sees 60 shares in holdings, no pending orders → orders 90 shares
- The partial fill is not lost — it's reflected in current holdings

---

## Parameter Reference

### All Configurable Parameters

| Parameter | Default | Location | Description |
|-----------|---------|----------|-------------|
| `rebalance_interval_trading_days` | 5 | Alpha Model | Trading days between full signal recalculation |
| `short_period` | 20 | Alpha Model | Short-term SMA period |
| `medium_period` | 63 | Alpha Model | Medium-term SMA period |
| `long_period` | 252 | Alpha Model | Long-term SMA period |
| `atr_period` | 14 | Alpha Model | ATR period for normalization |
| `min_magnitude` | 0.05 | Alpha Model | Minimum signal to emit |
| `target_vol_annual` | 0.10 | PCM | Target annualized portfolio volatility |
| `max_gross` | 1.50 | PCM | Maximum gross exposure |
| `max_net` | 0.50 | PCM | Maximum absolute net exposure |
| `max_weight` | 0.10 | PCM | Maximum per-name weight |
| `vol_lookback` | 63 | PCM | Days for volatility estimation |
| `scaling_days` | 5 | PCM | Trading days to scale into positions |
| `strong_threshold` | 0.70 | Execution | Signal strength for market orders |
| `moderate_threshold` | 0.30 | Execution | Signal strength for moderate limit orders |
| `moderate_offset_pct` | 0.005 | Execution | 0.5% limit offset for moderate signals |
| `weak_offset_pct` | 0.015 | Execution | 1.5% limit offset for weak signals |
| `default_signal_strength` | 0.50 | Execution | Fallback when signal_strengths lookup misses |

### Scaling Schedule Parameters (In PCM)

| Tier | `front_load_factor` | Behavior |
|------|---------------------|----------|
| Strong (≥0.7) | 2.0 | Sqrt curve — aggressive early scaling |
| Moderate (0.3–0.7) | 1.3 | Mild front-load |
| Weak (<0.3) | 1.0 | Linear — even spread |

---

## Data Flow Walkthrough

### Week 1, Day 0 (Monday — Rebalance Day)

```
1. Market opens → Schedule.On fires → cancel_stale_orders() (nothing to cancel on day 1)

2. Daily bar arrives, pipeline triggers:

3. Alpha Model Update():
   - trading_days_since_rebalance is None → this is a rebalance day
   - Sets trading_days_since_rebalance = 0
   - Computes signals for all 30 DOW stocks
   - 22 stocks pass min_magnitude filter
   - Caches: {AAPL: (Up, 0.82), MSFT: (Up, 0.45), BA: (Down, -0.18), ...}
   - Sets algorithm.pcm.is_rebalance_day = True
   - Emits 22 insights (SourceModel=None, not overloaded)

4. PCM CreateTargets():
   - Reads self.is_rebalance_day = True → full rebalance
   - Converts insights to raw weights: {AAPL: +0.82, MSFT: +0.45, BA: -0.18, ...}
   - Normalizes to unit gross
   - Scales to 10% target vol → {AAPL: +0.062, MSFT: +0.034, BA: -0.014, ...}
   - Applies constraints
   - Stores as weekly_targets
   - Stores signal_strengths: {AAPL: 0.82, MSFT: 0.45, BA: 0.18, ...}
   - current_scale_day = 0
   - AAPL schedule (strong): fraction = 0.45
   - MSFT schedule (moderate): fraction = 0.30
   - BA schedule (weak): fraction = 0.20
   - Emits targets: {AAPL: +2.79%, MSFT: +1.02%, BA: -0.28%, ...}

5. Execution Model Execute():
   - AAPL: _get_signal_strength → 0.82 ≥ 0.70 → MarketOrder
   - MSFT: _get_signal_strength → 0.45, 0.30≤0.45<0.70 → LimitOrder at 0.5% offset
   - BA: _get_signal_strength → 0.18, <0.30 → LimitOrder at 1.5% offset (short, limit above)
```

### Week 1, Day 1 (Tuesday — Scaling Day)

```
1. Market opens → Schedule.On fires → cancel_stale_orders()
   - Cancels MSFT limit order (if unfilled)
   - Cancels BA limit order (if unfilled)

2. Daily bar arrives, pipeline triggers:

3. Alpha Model Update():
   - trading_days_since_rebalance = 0, increment to 1. 1 < 5 → scaling day
   - Sets algorithm.pcm.is_rebalance_day = False
   - Re-emits cached signals (same 22 insights, same magnitudes)

4. PCM CreateTargets():
   - Reads self.is_rebalance_day = False → scaling day
   - current_scale_day increments to 1
   - AAPL schedule (strong): fraction = 0.63
   - MSFT schedule (moderate): fraction = 0.50
   - BA schedule (weak): fraction = 0.40
   - Emits targets: {AAPL: +3.91%, MSFT: +1.7%, BA: -0.56%, ...}

5. Execution Model Execute():
   - AAPL: already holds ~2.79%, target is 3.91% → orders delta of ~1.12%
     signal=0.82 → MarketOrder
   - MSFT: may hold 0% (limit didn't fill) or ~1.02% (limit filled)
     target is 1.7% → orders appropriate delta
     signal=0.45 → LimitOrder at 0.5% offset from today's price
   - BA: similar logic
```

### Week 1, Days 2-4 (Wed-Fri)

Same pattern. Cumulative fractions increase until Day 4 reaches 100%.

### Week 2, Day 0 (Next Monday — New Rebalance)

- `trading_days_since_rebalance` hits 5 (== `rebalance_interval_trading_days`)
- Cycle repeats with freshly computed signals
- Some stocks may have changed direction or dropped below the threshold

---

## Edge Cases and Mitigations

### 1. Signal Flips Mid-Week

**Scenario:** AAPL has a strong long signal on Monday. By Wednesday, the market crashes and AAPL's signal would be short — but we don't recalculate until next Monday.

**Behavior:** The strategy continues scaling into the stale long position until the next rebalance. This is by design — the weekly rebalance cadence means we accept up to one week of signal lag.

**Mitigation:** The scaling mechanism naturally limits exposure. By Wednesday (Day 2), a strong signal would be at 77% of target. A weak signal would only be at 60%. The slower scaling for weak signals provides natural protection against whipsaw.

### 2. Stock Removed From Universe

**[Rev 2 fix — Finding #5]:**

**Scenario:** A stock is removed from the DOW30 mid-backtest.

**Behavior — multi-layer cleanup:**
1. **Execution model** `OnSecuritiesChanged()`: Cancels any open limit orders for the removed security
2. **PCM** `OnSecuritiesChanged()`: Removes symbol from `weekly_targets`, `signal_strengths`, `symbols`, `rolling_returns`, and `prev_close`
3. **Alpha model** `OnSecuritiesChanged()`: Removes indicators and stops tracking the symbol

No phantom targets will be generated because the symbol is removed from `weekly_targets` before the next `CreateTargets()` call.

### 3. Missing Signal Strength for a Symbol

**[Rev 2 fix — Finding #2]:**

**Scenario:** A target is generated for a symbol that isn't in `signal_strengths` (constraints, universe timing, missing data bar on rebalance day).

**Behavior:** The execution model's `_get_signal_strength()` returns `default_signal_strength` (0.50 = moderate tier). This means:
- The symbol gets a limit order at 0.5% offset (not a market order)
- It's a safe, conservative default — if we don't know the signal strength, we don't trade aggressively

### 4. Insufficient Data for Volatility Estimation

**Scenario:** Early in the backtest, not enough return history to estimate volatility.

**Behavior:** Same as current — `_estimate_portfolio_vol` returns `None`, and no scaling is applied (scale=1.0). The constraints (per-name, gross, net) still protect against excessive exposure.

### 5. All Signals Are Weak

**Scenario:** Market is in a range-bound period. All signals are between 0.05 and 0.30.

**Behavior:** All orders are limit orders at 1.5% offset. Many may not fill. Positions scale in very slowly. This is the desired behavior — the strategy naturally reduces activity when conviction is low.

### 6. Holiday Weeks (Fewer Than 5 Trading Days)

**[Rev 2 fix — Finding #7]:**

**Scenario:** A holiday week has only 4 trading days.

**Behavior:** Both rebalance and scaling use trading-day counters. With `rebalance_interval_trading_days=5` and `scaling_days=5`:
- Day 0 (Mon): Rebalance, scale day 0
- Day 1 (Tue): Scale day 1
- Day 2 (Wed): Scale day 2
- (Thu: Holiday — no `Update()` call, no increment)
- Day 3 (Fri): Scale day 3
- Day 4 (next Mon): Scale day 4 → 100% reached. Also: trading_days_since_rebalance hits 5, triggering next rebalance.

The system always reaches 100% and always rebalances after exactly `rebalance_interval_trading_days` trading days, regardless of holidays.

### 7. Very Large Target Change on Rebalance

**Scenario:** On rebalance day, the new weekly target for a stock is much larger than the current position.

**Behavior:** The scaling mechanism handles this naturally. If the stock had a position from last week at 100% of old target, and the new target is 2x larger, the Day 0 fraction applies to the NEW target. So for a strong signal, we'd go to 45% of the new (larger) target immediately, which might be close to or even larger than the old position.

### 8. Tick Size Mismatch

**[Rev 2 fix — Finding #6]:**

**Scenario:** A future expansion to non-DOW30 securities (FX, futures) with different tick sizes.

**Behavior:** Limit prices are rounded using `security.SymbolProperties.MinimumPriceVariation` instead of hardcoded 2-decimal rounding. For DOW30 equities, this produces the same result ($0.01 ticks), but it's future-proof.

---

## Implementation Order

The implementation should proceed in this order to allow incremental testing:

### Step 1: Create `models/execution.py`
- Self-contained new file
- No dependencies on other changes
- Can be tested independently by swapping in for `ImmediateExecutionModel`

### Step 2: Modify `models/alpha.py`
- Add signal caching and daily emission
- Switch to trading-day counter
- Set `is_rebalance_day` flag on PCM
- Backward compatible — if PCM doesn't have the flag, it just gets daily targets

### Step 3: Modify `models/portfolio.py`
- Add `is_rebalance_day` flag, scaling logic, and signal strength storage
- Dynamic schedule generation via `_build_schedule()`
- Clean up `weekly_targets` / `signal_strengths` in `OnSecuritiesChanged`
- This is the most complex change — depends on alpha changes from Step 2

### Step 4: Modify `models/__init__.py`
- One-line addition to export `SignalStrengthExecutionModel`

### Step 5: Modify `main.py`
- Wire new execution model (store reference for scheduled event)
- Add `scaling_days` parameter to PCM
- Add `Schedule.On` for stale order cancellation
- Update debug logging

### Step 6: Update `claude.md`
- Document new parameters, order types, and scaling behavior

---

## Verification and Testing

### Test 1: Regression Check

Set parameters to replicate current behavior:
```python
# In execution model: treat everything as strong → market orders
strong_threshold=0.0

# In PCM: instant scaling → no gradual ramp
# Set front_load_factor to very high value so day 0 fraction ≈ 100%
# Or set scaling_days=1 (single-element schedule = [1.0])
```

Expected: Results should be nearly identical to current strategy (small differences from daily vs weekly insight emission are acceptable).

### Test 2: Push to Cloud and Backtest

```bash
cd ~/Documents/QuantConnect
source venv/bin/activate
cd MyProjects
lean cloud push --project "WolfpackTrend 1" --force
lean cloud backtest "WolfpackTrend 1" --name "Signal-strength execution + daily scaling"
```

### Test 3: Check Debug Logs

Look for these log patterns:
- Alpha: `[2022-01-03] Alpha (rebalance): 22 signals (15 long, 7 short)`
- Alpha: `[2022-01-04] Alpha (scaling, day 1/5): 22 signals (cached)`
- PCM: `[2022-01-03] PCM: Scale day 0/5, Vol=12.3%, Gross=45%, Net=+12%`
- Execution: `Market order: Buy 56 AAPL (signal=0.82)`
- Execution: `Limit order: Buy 30 MSFT @ $298.50 (signal=0.45, offset=0.5%)`
- Stale cancel: `Cancelled stale limit: MSFT qty=30`

### Test 4: ObjectStore Analysis

After backtest, in a research notebook:
```python
# Check positions.csv for gradual weight ramp
df_pos = pd.read_csv(StringIO(qb.ObjectStore.Read("wolfpack/positions.csv")), parse_dates=['date'])

# For a specific stock, plot weight over a week
aapl = df_pos[df_pos['symbol'] == 'AAPL']
aapl_week = aapl[(aapl['date'] >= '2022-03-07') & (aapl['date'] <= '2022-03-11')]
print(aapl_week[['date', 'weight']])
# Should show gradual increase, not a jump
```

### Test 5: Limit Order Fill Rate

Check slippage.csv to verify limit orders are working:
- Moderate signals should fill most of the time (0.5% offset)
- Weak signals should have a lower fill rate (1.5% offset)
- Compare average fill prices between market and limit orders

### Test 6: Edge Case Coverage

**[Rev 2 — addresses test gaps identified in review]:**

| Test | What it verifies |
|------|------------------|
| Set `scaling_days=3` and run backtest | Schedule generation works for non-5 values; no index errors |
| Remove a stock from DOW30 list mid-backtest (or use a shorter universe) | `weekly_targets` / `signal_strengths` are properly cleaned up in `OnSecuritiesChanged` |
| Run with `default_signal_strength=0.50` and check that unknown symbols get moderate treatment | Safe fallback for missing signal_strengths entries |
| Check that orders cancelled at market open don't appear in `GetUnorderedQuantity` during `Execute()` | Scheduled cancellation timing is correct |
| Verify limit prices are multiples of tick size in slippage.csv | Tick-size rounding works correctly |
| Run backtest spanning a holiday week (e.g., Thanksgiving) and verify 100% scaling is reached | Trading-day counters align correctly |
