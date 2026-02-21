# Signal-Aware Order Cancellation

**Date**: 2026-02-13
**Status**: Proposed
**Impact**: High - affects order execution and position scaling

---

## Executive Summary

The current order cancellation mechanism is too aggressive for the 5-day position scaling strategy, resulting in 32.7% of moderate tier orders being cancelled prematurely. This proposal implements **signal-aware cancellation** that only cancels orders from previous rebalance cycles, allowing the full 5-day scaling window to complete.

**Expected Improvements:**
- Moderate tier cancellation rate: **32.7% → <5%**
- Moderate tier fill ratio: **62.9% → >90%**
- Complete position scaling before new signals arrive

---

## Problem Statement

### Current Behavior

The `SignalStrengthExecutionModel` cancels unfilled limit orders after **2 market-open checks** (~2 days):

```python
# models/execution.py (lines 120-139)
def cancel_stale_orders(self, algorithm):
    for ticket in self.open_limit_tickets:
        if ticket.Status in (OrderStatus.Submitted, OrderStatus.PartiallyFilled):
            checks = self.limit_open_checks.get(ticket.OrderId, 0) + 1
            self.limit_open_checks[ticket.OrderId] = checks
            if checks >= self.limit_cancel_after_open_checks:  # Default: 2
                ticket.Cancel()
```

**Timeline:**
- Day 0: Order submitted (end-of-day or intraday)
- Day 1: Market open → first check (`checks = 1`)
- Day 2: Market open → second check (`checks = 2`) → **Order cancelled**

### The Conflict with Scaling Strategy

The portfolio construction model scales positions over **5 trading days**:

```python
# models/portfolio.py (lines 130-141)
# Position buildup: 0% → 20% → 40% → 60% → 80% → 100% over 5 days
```

**Problem**: Orders submitted on Day 1 are cancelled on Day 3, **before the 5-day scaling completes**.

**Rebalance schedule**:
- Signals generated every **5 trading days**
- Fresh targets emitted daily (cached or new)
- Each day's orders get cancelled before accumulating

**Result**: Position scaling is disrupted mid-cycle, leading to:
- Incomplete position buildup
- Lower-than-expected exposure
- Degraded strategy performance

---

## Evidence from Analysis

### 1. Cancellation Rate by Tier
**Source**: `research/trading/order_lifecycle.ipynb`

```
tier        orders    cancel_rate    avg_fill_ratio
moderate    11,946       32.7%            62.9%
strong       N/A         <5%              >95%
exit         630         0.0%            100.0%
```

**Interpretation**:
- **Moderate tier** (0.5% limit offset): 32.7% cancelled, 62.9% average fill
- **Strong tier** (0.0% offset): Near-immediate fills, minimal cancellation
- **Exit tier** (market orders): 100% fill, no cancellation

### 2. Fill Progression Cliff at Day 2
**Source**: `research/trading/order_lifecycle.ipynb` - Fill Progression Analysis

- **Day 0**: 0% fill (just submitted)
- **Day 1**: ~100% fill for surviving orders
- **Day 2**: **~100% cancellation rate** (cliff)
- **Days 3+**: Remaining orders fill or cancelled

**Interpretation**: Orders are systematically cancelled at exactly day 2, confirming the 2-check threshold.

### 3. Price Movement Analysis
**Source**: `research/trading/order_lifecycle.ipynb` - Price Movement at Cancellation

- **~80% of cancelled orders**: Minimal price movement (-0.5% to +0.5%)
- **~20% of cancelled orders**: Significant favorable movement (>5%)

**Interpretation**:
- Most cancellations are justified (price didn't move enough to fill 0.5% offset)
- However, **~20% had favorable moves** and could have filled given more time

### 4. Root Cause: Misaligned Timeframes

| Component | Timeframe | Outcome |
|-----------|-----------|---------|
| Signal generation | Every 5 trading days | Fresh targets |
| Position scaling | 5 trading days (0% → 100%) | Gradual buildup |
| Order cancellation | **2 trading days** | **Premature termination** |

**The mismatch**: Orders are cancelled on Day 3 while scaling runs through Day 5.

---

## Proposed Solution: Signal-Aware Cancellation

### Core Principle

**Only cancel orders from PREVIOUS rebalance cycles, not the current one.**

This allows:
- ✅ Full 5-day scaling window to complete
- ✅ Stale orders from old signals still cancelled
- ✅ No risk of executing outdated prices

### Implementation Approach

Track which **rebalance cycle** (week_id) each order belongs to:
- **Current cycle orders**: Allowed to persist through full 5-day scaling
- **Previous cycle orders**: Cancelled immediately (stale)

### Week ID Tracking (Actual Code)

The `week_id` used in order tags is already tracked by the **Portfolio Construction Model (PCM)** and is injected into tags by the execution model:

```python
# models/portfolio.py (around _initialize_week_plan)
self.current_week_id = algorithm.Time.strftime('%Y-%m-%d')
```

```python
# models/execution.py (_build_order_tag)
week_id = getattr(pcm, 'current_week_id', '') if pcm is not None else ''
...
f"week_id={week_id};"
```

**Format**: `YYYY-MM-DD` (no symbol prefix).

**Important**: Before the first rebalance (or if PCM hasn't set the value yet), `current_week_id` is `None`, so tags will include `week_id=` (empty value). Any signal-aware logic must treat empty `week_id` as missing and fall back safely.

**Example timeline**:
- **Week 0** (2024-01-02): Signals generated, `week_id = "AAPL_20240102"`
  - Days 1-5: Orders submitted with `week_id = "AAPL_20240102"`
- **Week 1** (2024-01-09): New signals, `week_id = "AAPL_20240109"`
  - Old orders (Week 0) cancelled immediately
  - New orders (Week 1) allowed full 5-day window

---

## Code Changes Required

### File 1: `models/execution.py`

#### Change 1.1: Add Week ID Tracking (Class-level)

**Location**: After line 37 (after `self.market_price_at_submit = {}`)

```python
# Add to __init__:
self.market_price_at_submit = {}
self.order_week_ids = {}  # NEW: Track which rebalance cycle each order belongs to
```

**Purpose**: Store the week_id for each order when submitted.

#### Change 1.2: Capture Week ID at Order Submission

**Location**: Lines 71, 83, 94, 105 (where orders are submitted)

**Current code** (line 71):
```python
ticket = algorithm.LimitOrder(symbol, quantity, limit_price, tag)
```

**New code**:
```python
ticket = algorithm.LimitOrder(symbol, quantity, limit_price, tag)
# Extract and store week_id from tag
week_id = self._extract_week_id_from_tag(tag)
if week_id:
    self.order_week_ids[ticket.OrderId] = week_id
else:
    # week_id can be empty early in the run; treat as missing
    pass
```

**Apply to**:
- Line 71 (strong signals)
- Line 83 (moderate signals)
- Line 94 (weak signals)
- Line 105 (exit signals - though exits use market orders and aren't cancelled)

#### Change 1.3: Add Helper Method to Extract Week ID

**Location**: After `cancel_stale_orders()` method (after line 139)

```python
def _extract_week_id_from_tag(self, tag):
    """Extract week_id from order tag string.

    Args:
        tag (str): Order tag in format 'tier=moderate;week_id=AAPL_20240102'

    Returns:
        str: Week ID or None if not found
    """
    if not tag:
        return None

    import re
    match = re.search(r'week_id=([^;]+)', tag)
    return match.group(1) if match else None
```

**Purpose**: Parse the week_id from the order tag string.

#### Change 1.4: Replace Cancellation Logic

**Location**: Lines 120-139 (entire `cancel_stale_orders` method)

**Current code**:
```python
def cancel_stale_orders(self, algorithm):
    """Cancel limit orders that have been open too long"""
    for ticket in self.open_limit_tickets:
        if ticket.Status in (OrderStatus.Submitted, OrderStatus.PartiallyFilled):
            checks = self.limit_open_checks.get(ticket.OrderId, 0) + 1
            self.limit_open_checks[ticket.OrderId] = checks

            if checks >= self.limit_cancel_after_open_checks:
                algorithm.Log(f"Cancelling stale order {ticket.OrderId} after {checks} open checks")
                ticket.Cancel()

                # Cleanup tracking
                if ticket.OrderId in self.limit_open_checks:
                    del self.limit_open_checks[ticket.OrderId]
                if ticket.OrderId in self.market_price_at_submit:
                    del self.market_price_at_submit[ticket.OrderId]

                self.open_limit_tickets.remove(ticket)
```

**New code**:
```python
def cancel_stale_orders(self, algorithm):
    """Cancel limit orders from PREVIOUS rebalance cycles only.

    This allows the full 5-day scaling window to complete for current-cycle orders
    while still preventing stale orders from old signals.
    """
    # Get current week_id from PCM (set on rebalance day in portfolio model)
    pcm = getattr(algorithm, 'pcm', None)
    current_week_id = getattr(pcm, 'current_week_id', None) if pcm is not None else None

    if not current_week_id:
        # Fallback: if no current_week_id set, use old 2-check behavior
        algorithm.Log("Warning: current_week_id not set, using legacy 2-check cancellation")
        self._cancel_stale_orders_legacy(algorithm)
        return

    # Cancel orders from previous rebalance cycles
    orders_to_cancel = []
    for ticket in self.open_limit_tickets:
        if ticket.Status in (OrderStatus.Submitted, OrderStatus.PartiallyFilled):
            order_week_id = self.order_week_ids.get(ticket.OrderId)

            if not order_week_id:
                # Order has no week_id (possible early in run); fall back to legacy logic
                algorithm.Log(f"Warning: Order {ticket.OrderId} has no week_id; applying legacy check")
                # Legacy behavior for this ticket only
                checks = self.limit_open_checks.get(ticket.OrderId, 0) + 1
                self.limit_open_checks[ticket.OrderId] = checks
                if checks >= self.limit_cancel_after_open_checks:
                    algorithm.Log(
                        f"[LEGACY] Cancelling stale order {ticket.OrderId} after {checks} checks"
                    )
                    orders_to_cancel.append(ticket)
                continue

            # Parse dates from week_ids to compare cycles
            # Format: SYMBOL_YYYYMMDD
            try:
                order_date_str = order_week_id.split('_')[-1]
                current_date_str = current_week_id.split('_')[-1]

                # Only cancel if order is from PREVIOUS cycle (older date)
                if order_date_str < current_date_str:
                    algorithm.Log(f"Cancelling stale order {ticket.OrderId} from week {order_week_id} (current: {current_week_id})")
                    orders_to_cancel.append(ticket)
            except Exception as e:
                algorithm.Log(f"Error comparing week_ids for order {ticket.OrderId}: {e}")
                continue

    # Execute cancellations and cleanup
    for ticket in orders_to_cancel:
        ticket.Cancel()

        # Cleanup tracking dictionaries
        if ticket.OrderId in self.limit_open_checks:
            del self.limit_open_checks[ticket.OrderId]
        if ticket.OrderId in self.market_price_at_submit:
            del self.market_price_at_submit[ticket.OrderId]
        if ticket.OrderId in self.order_week_ids:
            del self.order_week_ids[ticket.OrderId]

        self.open_limit_tickets.remove(ticket)


def _cancel_stale_orders_legacy(self, algorithm):
    """Legacy 2-check cancellation logic (fallback only)"""
    for ticket in self.open_limit_tickets:
        if ticket.Status in (OrderStatus.Submitted, OrderStatus.PartiallyFilled):
            checks = self.limit_open_checks.get(ticket.OrderId, 0) + 1
            self.limit_open_checks[ticket.OrderId] = checks

            if checks >= self.limit_cancel_after_open_checks:
                algorithm.Log(f"[LEGACY] Cancelling stale order {ticket.OrderId} after {checks} checks")
                ticket.Cancel()

                # Cleanup
                if ticket.OrderId in self.limit_open_checks:
                    del self.limit_open_checks[ticket.OrderId]
                if ticket.OrderId in self.market_price_at_submit:
                    del self.market_price_at_submit[ticket.OrderId]
                if ticket.OrderId in self.order_week_ids:
                    del self.order_week_ids[ticket.OrderId]

                self.open_limit_tickets.remove(ticket)
```

**Key changes**:
- Compare `order_week_id` vs `current_week_id` by date
- Only cancel orders from older cycles
- Graceful fallback if week_id tracking fails
- Added cleanup for `order_week_ids` dictionary

---

### File 2: `models/portfolio.py`

#### Change 2.1: Use PCM’s Current Week ID (Already Present)

**Location**: `_initialize_week_plan()` (around line 255)

**Current code**:
```python
self.current_week_id = algorithm.Time.strftime('%Y-%m-%d')
```

**Purpose**: This is the authoritative `week_id` for the current rebalance cycle and is already used in order tags via the execution model.

#### Change 2.2: Ensure Signal-Aware Cancellation Sees the New Cycle

**Important sequencing note**: `cancel_stale_orders()` is scheduled at **market open**, before the pipeline runs. PCM’s `current_week_id` is only set later when targets are created. This means a “current vs previous cycle” comparison will still see the *old* week_id on rebalance days.

**Options**:
- Move cancellation to after the pipeline (e.g., end of day), or
- Trigger cancellation right after PCM updates targets on rebalance days.

The exact scheduling change is required to make week-aware cancellation reliable.

---

### File 3: `main.py`

#### Change 3.1: Adjust Cancellation Scheduling (Recommended)

**Location**: `Initialize()` scheduling of `_cancel_stale_orders`

**Current code**:
```python
self.Schedule.On(
    self.DateRules.EveryDay(),
    self.TimeRules.AfterMarketOpen("SPY", 0),
    self._cancel_stale_orders
)
```

**Issue**: This runs before PCM sets `current_week_id` on rebalance days, so cycle-aware cancellation can’t see the new cycle.

**Recommendation**: Move this to after the pipeline runs (e.g., end of day), or invoke cancellation immediately after PCM target creation on rebalance days.

---

## Implementation Checklist

- [ ] **Backup current code** (commit to git before changes)
- [ ] **File 1**: Update `models/execution.py`
  - [ ] Add `self.order_week_ids = {}` to `__init__`
  - [ ] Capture week_id at order submission (lines 71, 83, 94, 105)
  - [ ] Add `_extract_week_id_from_tag()` helper method
  - [ ] Replace `cancel_stale_orders()` with signal-aware logic
  - [ ] Add `_cancel_stale_orders_legacy()` fallback method
- [ ] **File 2**: Update `models/alpha.py`
  - [ ] Set `algorithm.current_week_id` after week_id calculation
  - [ ] Reset `algorithm.current_week_id = None` at rebalance start
- [ ] **File 3**: Update `main.py`
  - [ ] Initialize `self.current_week_id = None` in `Initialize()`
- [ ] **Test**: Run backtest with logging to verify week_id tracking
- [ ] **Validate**: Check order_events.csv for reduced cancellation rate
- [ ] **Compare**: Run before/after backtests to measure impact

---

## Testing Strategy

### 1. Logging Verification

Add temporary debug logging to verify week_id tracking:

```python
# In execution.py, cancel_stale_orders():
algorithm.Log(f"Current week_id: {current_week_id}")
for ticket in self.open_limit_tickets:
    order_week_id = self.order_week_ids.get(ticket.OrderId)
    algorithm.Log(f"Order {ticket.OrderId}: week_id={order_week_id}, status={ticket.Status}")
```

**Expected output**:
- Current week_id updates every 5 trading days
- Orders tagged with their submission week_id
- Cancellations only for orders where `order_week_id < current_week_id`

### 2. Backtest Comparison

Run two backtests (same date range):

| Metric | Before (2-check) | After (Signal-Aware) | Target |
|--------|------------------|----------------------|--------|
| Moderate tier cancel rate | 32.7% | ? | <5% |
| Moderate tier fill ratio | 62.9% | ? | >90% |
| Average position buildup | ~63% of target | ? | ~100% of target |
| Sharpe ratio | Baseline | ? | ≥ Baseline |
| Max drawdown | Baseline | ? | ≤ Baseline |

### 3. Order Lifecycle Analysis

Re-run `research/trading/order_lifecycle.ipynb` with new backtest data:

**Expected changes**:
- Days-to-cancellation: Peak shifts from day 2 to day 5+
- Cancellation rate by order age: Cliff at day 2 disappears
- Fill ratio: Increases as orders have more time to fill

### 4. Edge Cases to Test

- **Week boundary**: Orders submitted on Friday of Week 0, should persist through Week 0 (until Tuesday of Week 1)
- **Holiday weeks**: Scaling may take >5 calendar days but should complete in 5 trading days
- **Partial fills**: Partially filled orders from previous cycles should still be cancelled
- **Missing week_id**: Orders without week_id should fall back to legacy behavior (logged warning)

---

## Expected Outcomes

### Quantitative Improvements

| Metric | Current | Expected | Improvement |
|--------|---------|----------|-------------|
| Moderate tier cancellation rate | 32.7% | <5% | **-27.7 pp** |
| Moderate tier avg fill ratio | 62.9% | >90% | **+27.1 pp** |
| Orders completing scaling | ~67% | >95% | **+28 pp** |
| Position target achievement | ~63% | ~95% | **+32%** |

### Qualitative Improvements

1. **Aligned execution with strategy intent**
   - 5-day scaling completes as designed
   - Positions build to full targets before rebalance

2. **Reduced transaction costs**
   - Fewer cancelled orders = less wasted commission
   - Better limit fill rates = reduced slippage

3. **Improved risk management**
   - Actual exposure closer to targeted exposure
   - Volatility targeting more accurate

4. **No stale order risk**
   - Previous cycle orders still cancelled
   - Fresh signals always get priority

---

## Risks and Mitigations

### Risk 1: Missing or Empty Week ID

**Scenario**: `week_id` is empty early in the run or missing from a tag, causing orders to skip cancellation.

**Mitigation**:
- Treat missing/empty `week_id` as legacy 2-check behavior for that order
- Log warnings to surface unexpected tag formats
- Unit tests for `_extract_week_id_from_tag()` and empty-tag behavior

### Risk 2: Increased Capital Usage

**Scenario**: More orders persist longer → higher margin requirements

**Mitigation**:
- Monitor margin usage in backtests
- Portfolio construction already has gross exposure cap (150%)
- Orders still capped by position limits (10% per name)

### Risk 3: Execution on Stale Prices

**Scenario**: Order from Day 1 fills on Day 5 at outdated limit price

**Mitigation**:
- Limit orders protect against adverse price movement
- 5-day timeframe is still short relative to trend horizon (20/63/252 days)
- Moderate tier offset (0.5%) provides price improvement buffer

### Risk 4: Rebalance Interval = Scaling Window

**Scenario**: Both are 5 days, so orders may overlap rebalances

**Mitigation**:
- Signal-aware cancellation handles this explicitly
- Old cycle orders cancelled on Day 1 of new cycle
- No accumulation across cycles

---

## Rollback Plan

If the new logic causes issues:

1. **Immediate rollback** (single line change):
   ```python
   # In main.py, Initialize():
   self.current_week_id = None  # Force fallback to legacy behavior
   ```

2. **Full rollback** (git):
   ```bash
   git checkout models/execution.py models/alpha.py main.py
   ```

3. **Partial rollback** (disable signal-aware only):
   ```python
   # In execution.py, cancel_stale_orders():
   current_week_id = None  # Force legacy path
   ```

---

## Success Criteria

### Minimum Viable Success
- [ ] Backtest runs without errors
- [ ] Moderate tier cancellation rate < 15% (down from 32.7%)
- [ ] Moderate tier fill ratio > 80% (up from 62.9%)
- [ ] No regression in Sharpe ratio

### Full Success
- [ ] Moderate tier cancellation rate < 5%
- [ ] Moderate tier fill ratio > 90%
- [ ] Sharpe ratio improves by ≥5%
- [ ] Position targets achieved >95% of the time

### Exceptional Success
- [ ] All above metrics achieved
- [ ] Max drawdown reduced
- [ ] Strategy capacity increased (better fills allow larger positions)

---

## Next Steps

1. **Review this document** with stakeholders
2. **Create feature branch**: `git checkout -b feature/signal-aware-cancellation`
3. **Implement changes** following the code change sections
4. **Run backtest** with debug logging enabled
5. **Analyze results** using order_lifecycle.ipynb
6. **Iterate** if needed based on results
7. **Merge to main** once validated
8. **Deploy to live** (if applicable)

---

## References

- **Investigation**: `research/trading/order_lifecycle.ipynb`
- **Plan**: `/Users/graham/.claude/plans/spicy-floating-wolf.md`
- **Current implementation**:
  - `models/execution.py` (lines 120-139)
  - `models/alpha.py` (lines 178-179)
  - `models/portfolio.py` (lines 130-141)

---

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2026-02-13 | Claude (Investigation) | Initial proposal based on order lifecycle analysis |

---

## Appendix: Alternative Approaches Considered

### Option 1: Increase Check Threshold (Rejected)

**Change**: Set `limit_cancel_after_open_checks = 5`

**Pros**: One-line change, simple to implement

**Cons**:
- Orders persist 4-5 days regardless of rebalance schedule
- If rebalance is every 5 days, orders overlap cycles
- No explicit alignment with strategy logic
- Harder to reason about behavior

**Decision**: Rejected in favor of signal-aware approach for better alignment with strategy intent.

### Option 3: Dynamic Cancellation by Fill Progress (Considered)

**Change**: Only cancel 0% filled orders after 2 checks; allow partial fills more time

**Pros**: Balances staleness vs opportunity

**Cons**:
- Doesn't address root cause (misaligned timeframes)
- Complex state tracking
- Unpredictable order lifetime

**Decision**: Deferred - can be added later if signal-aware approach needs refinement.

### Option 4: Reduce Moderate Offset (Rejected)

**Change**: Reduce moderate offset from 0.5% to 0.25%

**Pros**: More aggressive pricing → higher fills

**Cons**:
- Reduces price improvement opportunity
- Doesn't solve the timeframe mismatch
- Changes strategy execution quality

**Decision**: Rejected - preserves intended execution strategy.
