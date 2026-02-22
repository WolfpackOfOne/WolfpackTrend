# Strategy Documentation

WolfpackTrend is a systematic long/short trend-following strategy trading a static equity universe. It uses a composite momentum signal, targets a fixed portfolio volatility, and executes with signal-strength-based limit orders.

## Universe

Static list of equities defined in `models/universe.py` (`EQUITY_UNIVERSE`). The universe does not rotate dynamically.

## Signal Generation (Alpha Model)

### Composite Trend Signal

The strategy computes a composite trend score for each stock using three simple moving averages:

| Horizon | Period | Weight |
|---------|--------|--------|
| Short   | 20 days  | 0.2  |
| Medium  | 63 days  | 0.5  |
| Long    | 252 days | 0.3  |

For each horizon, the distance from price to SMA is normalized by ATR(14):

```
distance_i = (price - SMA_i) / ATR
```

### Direction Agreement Rule

A signal is only generated when **all three horizons agree in direction**:
- All distances positive (bullish) → long signal
- All distances negative (bearish) → short signal
- Mixed directions → no signal (symbol skipped)

### Signal Magnitude

The weighted composite score is passed through `tanh` with a temperature divisor:

```
score = 0.2 * dist_short + 0.5 * dist_medium + 0.3 * dist_long
magnitude = tanh(score / 3.0)
```

- Temperature of 3.0 produces smooth, bounded output in (-1, +1)
- Signals with `|magnitude| < 0.05` are discarded

### Rebalance Cadence

- Signals are **recalculated every 5 trading days** (not calendar days)
- On non-rebalance days, cached signals are **re-emitted daily** to drive the scaling pipeline
- Trading-day counter ensures holidays don't compress or extend the cycle

## Portfolio Construction

### Volatility Targeting

The portfolio targets **10% annualized volatility** using a diagonal approximation (ignores cross-asset correlations):

```
port_vol = sqrt(sum(w_i^2 * var_i)) * sqrt(252)
```

- Uses 63-day rolling returns for variance estimation
- Minimum 20 observations required per asset
- Rolling returns are maintained incrementally (no History calls)

### Position Scaling

New targets are not applied immediately. Positions scale from their current weight to the target over **5 trading days**:

| Signal Strength | Scaling Curve | Day 1 Fraction |
|-----------------|---------------|----------------|
| Strong (>= 0.7)  | Front-loaded (sqrt) | ~45% |
| Moderate (0.3-0.7) | Mild front-load | ~30% |
| Weak (< 0.3) | Linear | 20% |

### Exposure Constraints

Applied in strict order (order matters for deterministic results):

1. **Per-name cap**: Each weight clipped to [-10%, +10%]
2. **Gross exposure cap**: If `sum(|w_i|) > 150%`, scale all weights proportionally
3. **Net exposure cap**: If `|sum(w_i)| > 50%`, scale all weights proportionally

## Execution

### Signal-Strength Tiered Limits

| Tier | Signal Threshold | Order Type | Offset |
|------|-----------------|------------|--------|
| Strong | >= 0.70 | Limit at market price | 0.0% |
| Moderate | >= 0.30 | Limit with offset | 0.5% |
| Weak | < 0.30 | Limit with offset | 1.5% |
| Exit | (any) | Market order | n/a |

- Buy orders: limit price = market * (1 - offset)
- Sell orders: limit price = market * (1 + offset)
- Prices rounded to tick size

### Stale Order Cancellation

Orders carry a `week_id` tag (the rebalance date in YYYY-MM-DD format). At market open each day:

1. All open limit orders are inspected
2. Orders with a `week_id` older than the current rebalance cycle are cancelled
3. Current-cycle orders are preserved (allowing the full 5-day scaling window)
4. Legacy fallback: if `week_id` is unavailable, orders are cancelled after 2 market-open checks

The PCM also runs a backup cancellation pass inside the pipeline to prevent duplicate orders.

## Backtest Configuration

| Parameter | Value |
|-----------|-------|
| Start Date | 2022-01-01 |
| End Date | 2024-01-01 |
| Starting Cash | $100,000 |
| Warmup | 252 days |
| Benchmark | SPY |

## Parameters Reference

All default values are documented in `templates/strategy_config.py`.
