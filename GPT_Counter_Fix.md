# GPT Counter Fix: Off-by-One Rebalance Cadence

## Executive Summary

Your strategy intends to rebalance every **5 trading days**, but the current counter implementation causes rebalances every **6 trading days**.  
This happens because the code:

1. Checks rebalance condition before incrementing the counter.
2. Resets the counter to `0` on rebalance day.
3. Uses condition `counter >= interval` with `interval=5`.

That sequence makes the next rebalance trigger when the counter reaches `5`, which occurs on the **6th** trading day after reset.

This same pattern appears in both:

- `signals/alpha.py` (alpha rebalance cadence)
- `risk/portfolio.py` (PCM fallback cadence)

So the cadence drift is duplicated across the two core components that should remain synchronized.

---

## Why This Is a Real Bug (Not Just Interpretation)

### Intended semantic meaning

When configuration says `rebalance_interval_trading_days=5`, the expected cycle is:

- Rebalance on Day 0
- Rebalance on Day 5
- Rebalance on Day 10

That is one rebalance every 5 trading days.

### Actual current behavior

With the current logic, you get:

- Rebalance on Day 0
- Rebalance on Day 6
- Rebalance on Day 12

That is one rebalance every 6 trading days.

### Practical consequence

Your “weekly” cycle stretches by +20% in time:

- Intended: 5-day cycle
- Actual: 6-day cycle

This affects:

- Signal refresh cadence
- `week_id` rollovers
- Scaling plan refresh timing
- Stale order cleanup that depends on cycle transitions
- Research dashboards keyed to cycle boundaries

---

## The Exact Root Cause

## 1) Alpha counter logic (`signals/alpha.py`)

Relevant lines:

- Rebalance check: `signals/alpha.py:84`
- Reset on rebalance: `signals/alpha.py:88`
- Increment on non-rebalance: `signals/alpha.py:95`

Current shape:

```python
if counter is None:
    rebalance = True
elif counter >= interval:
    rebalance = True

if rebalance:
    counter = 0
else:
    counter += 1
```

For `interval = 5`:

1. Rebalance day sets `counter = 0`
2. Next day checks `0 >= 5` (false), then increments to `1`
3. Day after checks `1 >= 5` (false), increments to `2`
4. Continue until check sees `5 >= 5` (true)
5. That true check happens on Day 6 from last rebalance

So cadence is 6 days.

---

## 2) PCM fallback counter logic (`risk/portfolio.py`)

Relevant lines:

- Fallback check: `risk/portfolio.py:107` to `risk/portfolio.py:110`
- Rebalance branch reset: `risk/portfolio.py:116`
- Non-rebalance increment: `risk/portfolio.py:120`

This uses the same “check-before-increment + reset-to-zero + `>= interval`” pattern, so it inherits the same off-by-one cadence.

Even if alpha sets `pcm.is_rebalance_day`, keeping incorrect fallback math in PCM is risky:

- Any day where external signal is absent, delayed, or bypassed can expose fallback behavior.
- Drift can appear in edge cases and debugging becomes harder.

---

## Timeline Proof (Concrete Example)

Assume:

- `interval = 5`
- `counter` reset to `0` on rebalance day
- check happens before increment

Day-by-day:

1. Day 0: rebalance, set `counter=0`
2. Day 1 start: check `0>=5` false, end `counter=1`
3. Day 2 start: check `1>=5` false, end `counter=2`
4. Day 3 start: check `2>=5` false, end `counter=3`
5. Day 4 start: check `3>=5` false, end `counter=4`
6. Day 5 start: check `4>=5` false, end `counter=5`
7. Day 6 start: check `5>=5` true, rebalance

If you intended Day 5 rebalance, this is clearly one day late each cycle.

---

## Recommended Fix (Minimal-Risk)

Change threshold from:

```python
counter >= interval
```

to:

```python
counter >= (interval - 1)
```

Why this works with current flow:

- Counter still resets to `0` on rebalance day
- Non-rebalance days still increment by `+1`
- Rebalance triggers when counter reaches `4` for interval 5
- That gives Day 0, Day 5, Day 10...

This is the smallest change and preserves existing counter style.

---

## Where To Apply It

Update both places to keep alpha/PCM cadence aligned:

1. `signals/alpha.py`
- Current condition around `signals/alpha.py:84`
- Replace threshold with `>= self.rebalance_interval_trading_days - 1`

2. `risk/portfolio.py`
- Current fallback condition around `risk/portfolio.py:109`
- Replace threshold with `>= self.rebalance_interval_trading_days - 1`

Important:

- Keep `max(1, int(...))` guards already in constructors.
- For `interval=1`, `(interval-1)=0`, so rebalance remains daily (correct).

---

## Alternative Fix (Clearer Semantics, Larger Change)

You can also redesign the counter to represent “days elapsed since last rebalance” and increment first, then test threshold.  
That can be cleaner conceptually, but it is easier to accidentally desynchronize alpha and PCM unless both are refactored together and carefully tested.

Given current architecture, the minimal threshold change is safer.

---

## Why This Matters Beyond Cadence

Even a 1-day drift in cycle timing propagates:

1. **Signal staleness**
- Fresh signal recompute occurs later than configured.

2. **Scaling behavior**
- Week/scale metadata rotates later, so execution and logs may reflect elongated cycles.

3. **Stale order lifecycle**
- Cancellation logic tied to `week_id` transitions can also shift.

4. **Research interpretation**
- Any chart grouped by `week_id` or “day in week” can show inflated ranges and confusing diagnostics.

---

## Validation Plan After Fix

## A) Static sanity check

Confirm both files now use identical threshold semantics:

- `signals/alpha.py`
- `risk/portfolio.py`

No mixed logic between the two.

## B) Local compile check

Run:

```bash
python -m py_compile main.py models/*.py
```

## C) Backtest cadence check

Run a cloud backtest and inspect debug logs for rebalance timestamps:

- Gap between rebalance days should be 5 trading days consistently.

## D) Data-output check

Inspect `targets.csv` and order tags:

- `week_id` should rotate at intended cadence.
- `scale_day` progression should align with expected 5-day cycle.

## E) Regression check for edge intervals

Test at least:

- `rebalance_interval_trading_days = 1` (daily)
- `rebalance_interval_trading_days = 5` (weekly trading cadence)

---

## Suggested Acceptance Criteria

The fix is “done” when all are true:

1. Rebalance events are exactly 5 trading days apart for interval 5.
2. Alpha and PCM roll over on the same cycle boundaries.
3. `week_id` and `scale_day` progress coherently with no cycle inflation.
4. No compile/runtime regressions in normal backtest execution.

---

## Notes on Scope

This document addresses only the **counter off-by-one cadence** bug.  
It does not include broader policy changes such as:

- whether to flatten on rebalance days with no active insights,
- whether to alter insight period from 1 day to multi-day,
- whether to add execution deadbands for tiny residual rebalances.

Those can be handled separately once cadence correctness is restored.

