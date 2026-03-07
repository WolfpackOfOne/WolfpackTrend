# GPT Rebalance Counter Analysis

## Scope
This document explains two related strategy issues:

1. Rebalance cadence is off by one trading day in both alpha and portfolio counters.
2. `week_id` can remain unchanged across extra days when no active insights are passed into portfolio construction.

It also explains why these issues produce analysis artifacts such as `day_in_week` values above expected scaling windows, and gives concrete fix options.

All file and line references below are based on the current repository state at time of writing.

## Relevant Files
- `signals/alpha.py`
- `risk/portfolio.py`
- `loggers/portfolio_logger.py`
- `loggers/target_logger.py`
- `research/trading/stale_signal_risk.ipynb`
- `core/math_utils.py`

## Intended Invariants (from project guidance)
- Rebalance interval is 5 trading days.
- Scaling is 5 trading days.
- Cycle logic should be trading-day-based, not calendar-based.
- `week_id` should represent rebalance cycle boundaries.

## Current Behavior Summary

### Issue A: Off-by-one rebalance cycle
Both alpha and portfolio models use this pattern:

- Rebalance if `counter >= interval`
- On rebalance day, set `counter = 0`
- On non-rebalance day, increment `counter += 1`

With interval = 5, this produces rebalance every 6th trading day, not every 5th.

Code references:
- Alpha check: `signals/alpha.py:84`
- Alpha increment: `signals/alpha.py:95`
- Portfolio check: `risk/portfolio.py:109`
- Portfolio increment: `risk/portfolio.py:120`

### Issue B: `week_id` may not roll when no active insights
Portfolio construction returns early before cycle state is processed:

- Empty insights return: `risk/portfolio.py:100`
- Empty active insights return: `risk/portfolio.py:105`

`week_id` is only refreshed in `_initialize_week_plan()`:
- Method definition: `risk/portfolio.py:227`
- Assignment: `risk/portfolio.py:235`

If `CreateTargets()` returns early, `_initialize_week_plan()` is skipped and `week_id` remains the previous value.

### Why this shows up in the notebook chart
In `stale_signal_risk.ipynb`, x-axis is computed as:

- `merged['day_in_week'] = ... groupby(['week_id', 'symbol']).cumcount()`
- Reference: `research/trading/stale_signal_risk.ipynb:130`

If a single `week_id` spans extra dates, `cumcount()` can exceed expected 0..4 range and reach values like 10.

## Deep Dive: Off-by-One Counter Logic

### Current alpha flow
From `signals/alpha.py`:

- Rebalance check (`>= interval`) at line 84
- If rebalance: counter reset to 0 at line 88
- Else increment at line 95

Assume interval = 5 and `R` means rebalance day:

1. Day 0: counter None -> R, reset to 0
2. Day 1: 0 >= 5 is false -> increment to 1
3. Day 2: 1 >= 5 is false -> increment to 2
4. Day 3: 2 >= 5 is false -> increment to 3
5. Day 4: 3 >= 5 is false -> increment to 4
6. Day 5: 4 >= 5 is false -> increment to 5
7. Day 6: 5 >= 5 is true -> R

Result: rebalance gap is 6 trading days (Day 0 to Day 6), not 5.

### Current portfolio flow
`risk/portfolio.py` repeats the same shape:

- Counter check at lines 107-110
- Rebalance branch resets to 0 at line 116
- Non-rebalance increments at line 120

So portfolio-side fallback counter has the same 6-day spacing behavior.

### Why this matters
- Alpha signal refresh happens less frequently than configured.
- `current_week_id` rollover and week plan initialization happen less frequently than expected.
- Stale order week-cycle behavior can be delayed by one trading day.
- Research notebooks keyed by `week_id` and within-week day index are skewed.

## Deep Dive: No Active Insights and Stale `week_id`

### How active insights are determined
Portfolio construction filters:

```python
active_insights = [i for i in insights if i.IsActive(algorithm.UtcTime)]
if not active_insights:
    return targets
```

Reference: `risk/portfolio.py:103` and `risk/portfolio.py:105`.

### When no active insights can happen
This is expected in several normal market conditions:

1. No symbol passes trend agreement gate
- `compute_composite_signal()` requires all three trend distances to have same sign.
- References: `core/math_utils.py:140` to `core/math_utils.py:143`

2. Magnitude below threshold
- Signals below `min_magnitude` are dropped.
- Reference: `core/math_utils.py:150`

3. Data gaps or symbol readiness gaps
- Alpha skips symbols without ready indicators or bar in current slice.
- References: `signals/alpha.py:130` to `signals/alpha.py:139`

4. Insight expiration behavior
- Insight lifetime is 1 day.
- Reference: `signals/alpha.py:107`
- If alpha emits none on a day, prior insights may no longer be active by the time PCM filters them.

### Why stale `week_id` follows
- `week_id` is only assigned in `_initialize_week_plan()`.
- `_initialize_week_plan()` is only called in rebalance branch.
- Rebalance branch is never reached if method returns early for no active insights.

So cycle metadata may stop advancing exactly on days you most need clean bookkeeping.

## Interaction Between Both Issues
The two problems compound:

1. Off-by-one rebalance interval already stretches cycle boundaries.
2. No-insight early returns can stretch `week_id` further.
3. Notebook uses `cumcount()` by `week_id`, making x-axis appear too long.

That is why seeing `day_in_week` values around 10 is plausible with this implementation, even though strategy configuration says 5-day cadence.

## Fix Strategy

## Goals
- Enforce actual 5-trading-day cadence.
- Keep cycle state (`week_id`, `scale_day`, counters) moving deterministically.
- Preserve trading-day semantics.
- Preserve stale-order cancellation behavior tied to cycle IDs.
- Keep logging schema unchanged.

## Fix Part 1: Correct off-by-one in both counters

### Option 1 (minimal change)
Change rebalance condition from:

- `counter >= interval`

to:

- `counter >= (interval - 1)`

while keeping reset-to-zero and increment-on-non-rebalance pattern.

Why this works:
- With interval 5, rebalance days occur at counter values `None`, then `4`, then `4` again after reset cycle.
- That yields Day 0, Day 5, Day 10... spacing.

Apply in:
- `signals/alpha.py` rebalance check
- `risk/portfolio.py` counter fallback check

Edge case:
- interval = 1 should rebalance daily; this still works since `(1 - 1) = 0`.

### Option 2 (clearer semantics)
Use a "days since rebalance completed" counter and evaluate at start of day:

- Increment first
- Rebalance when `days_since >= interval`
- Reset on rebalance

This can be clearer, but is a bigger refactor and easier to misalign across alpha + PCM unless carefully mirrored.

Recommendation: Option 1 for minimal risk and fastest correction.

## Fix Part 2: Prevent `week_id` freeze on no-insight days

### Current anti-pattern
Cycle state update is downstream of:

- `if not insights: return`
- `if not active_insights: return`

### Safer pattern
Move cycle timing update ahead of early returns and separate:

1. Cycle advancement (always)
2. Target computation (depends on active insights)
3. Logging state update (always on cycle boundaries)

Concrete behavior target:
- On rebalance day with no active insights:
  - Advance to new `week_id`
  - Set weekly targets to empty
  - Initialize week plan
  - Emit explicit flatten targets for currently managed/invested symbols (policy decision, recommended)

This ensures:
- Bookkeeping remains coherent
- `week_id` always means "current rebalance cycle"
- Research grouping stays aligned with intended cadence

## Fix Part 3: Notebook axis should use logged `scale_day`
Even after fixing counters, analytics should use intentional strategy state when available.

`targets.csv` already includes `scale_day`:
- Logged from PCM state: `risk/portfolio.py:280`
- Persisted by target logger: `loggers/target_logger.py:7`, `loggers/target_logger.py:34`

For stale-signal risk notebook, prefer:

- x-axis from `scale_day` (0..4 expected with 5-day scaling)

instead of recomputing `cumcount()` from `week_id` and date ordering.

This removes hidden dependence on metadata continuity and gives a direct measurement of planned scaling day.

## Suggested Implementation Plan

1. Patch alpha counter threshold
- File: `signals/alpha.py`
- Change rebalance threshold logic to `>= interval - 1`

2. Patch PCM counter threshold
- File: `risk/portfolio.py`
- Same threshold change in fallback counter logic

3. Refactor PCM early-return ordering
- File: `risk/portfolio.py`
- Ensure cycle progression and rebalance state updates occur even when insights list is empty
- Ensure `week_id` rotates on schedule

4. Decide and encode explicit no-signal policy
- Recommended: flatten toward zero when no signals at rebalance
- This is consistent with trend-gate semantics ("no agreement" means no directional conviction)

5. Update stale-signal notebook
- File: `research/trading/stale_signal_risk.ipynb`
- Use `scale_day` as x-axis when available

6. Validate with local compile check
- `python -m py_compile main.py models/*.py`

7. Validate in cloud backtest
- Confirm rebalance timestamps, week IDs, and scale-day distribution

## Validation Checklist

### Counter correctness
- Rebalance occurs every 5 trading days, not 6.
- Check debug logs in alpha and PCM over at least 30 trading days.

### `week_id` correctness
- `week_id` changes exactly on rebalance boundaries.
- No prolonged same `week_id` streaks unless expected due to trading calendar gaps.

### Scaling day distribution
- `scale_day` should usually be in range 0..4 for 5-day scaling.
- If schedule pins at last day due delayed rebalance, verify this is intentional and bounded.

### Notebook sanity
- Stale signal chart x-axis should align with 0..4 (or documented exception cases).
- Outliers above expected range should be explainable by explicit logic, not silent metadata drift.

## Risk Notes

1. Behavior change risk
- Fixing early returns can change live/backtest behavior in periods with no valid signals.
- If portfolio was previously "sticky" due missing targets, making flatten explicit may reduce residual exposure.

2. Synchronization risk
- Alpha and PCM counters must stay semantically aligned.
- If only one is fixed, cycle signals and target generation can desynchronize.

3. Backward-compat analytics risk
- Historical notebooks expecting `cumcount()` by `week_id` may show shifted patterns after fix.
- This is expected and desirable if prior behavior was inconsistent with strategy design.

## Recommended Final State
- Alpha and PCM rebalance cadence: strict 5 trading days.
- `week_id` advances deterministically on each rebalance cycle.
- No-signal rebalance days still produce coherent cycle metadata and explicit target behavior.
- Research charts use direct strategy state (`scale_day`) where available.

## Practical "Done" Criteria
- Code compiles locally.
- One cloud backtest confirms:
  - Rebalance spacing is 5 trading days.
  - `targets.csv` has stable week segmentation.
  - No `day_in_week` inflation in stale-signal analysis when using `scale_day`.
- No ObjectStore schema changes.

