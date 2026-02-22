# ObjectStore Data Schema

The strategy logs daily metrics to QuantConnect's ObjectStore during backtests. All files are saved at the end of the backtest via `OnEndOfAlgorithm`. Previous run data is cleared at initialization.

## Files

| Key | Description | Approx Rows (2yr) |
|-----|-------------|--------------------|
| `wolfpack/daily_snapshots.csv` | Daily portfolio-level metrics | ~500 |
| `wolfpack/positions.csv` | Per-symbol position snapshots | ~15,000 |
| `wolfpack/signals.csv` | Alpha signals with indicator values | ~2,000 |
| `wolfpack/slippage.csv` | Per-fill slippage measurement | ~8,000 |
| `wolfpack/trades.csv` | Realized P&L from closed positions | ~4,000 |
| `wolfpack/targets.csv` | Daily per-symbol scaling target state | ~15,000 |
| `wolfpack/order_events.csv` | Full order lifecycle events | ~20,000 |

## Reading in Research Notebooks

```python
from io import StringIO
import pandas as pd

key = "wolfpack/daily_snapshots.csv"
df = pd.read_csv(StringIO(qb.ObjectStore.Read(key)), parse_dates=['date'])
```

## Column Definitions

### daily_snapshots.csv

| Column | Type | Description |
|--------|------|-------------|
| `date` | datetime | Trading date |
| `nav` | float | Total portfolio value |
| `cash` | float | Available cash |
| `gross_exposure` | float | (long + short) / nav |
| `net_exposure` | float | (long - short) / nav |
| `long_exposure` | float | Long value / nav |
| `short_exposure` | float | Short value / nav |
| `daily_pnl` | float | NAV change from previous day |
| `cumulative_pnl` | float | NAV - starting cash |
| `daily_slippage` | float | Sum of order slippage for the day |
| `num_positions` | int | Count of active positions |
| `estimated_vol` | float | Portfolio volatility estimate |

### positions.csv

| Column | Type | Description |
|--------|------|-------------|
| `date` | datetime | Trading date |
| `symbol` | string | Ticker symbol |
| `invested` | int | 1 if invested, 0 if flat |
| `quantity` | float | Position quantity |
| `price` | float | Last price |
| `market_value` | float | quantity * price |
| `weight` | float | market_value / nav |
| `unrealized_pnl` | float | Current unrealized P&L |
| `daily_pnl` | float | Daily unrealized P&L delta (legacy) |
| `daily_unrealized_pnl` | float | Daily unrealized P&L delta |
| `daily_realized_pnl` | float | Daily realized P&L delta |
| `daily_fees` | float | Daily fees delta |
| `daily_dividends` | float | Daily dividends delta (informational under Adjusted pricing) |
| `daily_total_net_pnl` | float | realized + unrealized - fees |
| `avg_price` | float | Average entry price |

### signals.csv

| Column | Type | Description |
|--------|------|-------------|
| `date` | datetime | Signal generation date |
| `symbol` | string | Ticker symbol |
| `direction` | string | "Up" or "Down" |
| `magnitude` | float | Signal magnitude from tanh (-1 to +1) |
| `price` | float | Close price at signal time |
| `sma_short` | float | SMA(20) value |
| `sma_medium` | float | SMA(63) value |
| `sma_long` | float | SMA(252) value |
| `atr` | float | ATR(14) value |

### slippage.csv

| Column | Type | Description |
|--------|------|-------------|
| `date` | datetime | Fill date |
| `symbol` | string | Ticker symbol |
| `direction` | string | "Buy" or "Sell" |
| `quantity` | float | Fill quantity |
| `expected_price` | float | Price at signal generation |
| `fill_price` | float | Actual fill price |
| `slippage_dollars` | float | Dollar slippage (positive = adverse) |

### trades.csv

| Column | Type | Description |
|--------|------|-------------|
| `date` | datetime | Trade close date |
| `symbol` | string | Ticker symbol |
| `action` | string | Always "CLOSE" |
| `quantity` | float | Position quantity at close |
| `avg_price` | float | Average entry price |
| `exit_price` | float | Price at close |
| `realized_pnl` | float | Approximate realized P&L |

### targets.csv

| Column | Type | Description |
|--------|------|-------------|
| `date` | datetime | Trading date |
| `week_id` | string | Rebalance date (YYYY-MM-DD) identifying the cycle |
| `symbol` | string | Ticker symbol |
| `start_w` | float | Portfolio weight at start of rebalance cycle |
| `weekly_target_w` | float | Final target weight for the cycle |
| `scheduled_fraction` | float | Cumulative scaling fraction for today (0.0-1.0) |
| `scheduled_w` | float | Scheduled weight for today |
| `actual_w` | float | Actual portfolio weight |
| `scale_day` | int | Current scaling day (0-indexed) |

### order_events.csv

| Column | Type | Description |
|--------|------|-------------|
| `date` | datetime | Event date |
| `order_id` | int | LEAN order ID |
| `symbol` | string | Ticker symbol |
| `status` | string | Submitted, Filled, Canceled, Invalid |
| `direction` | string | Buy or Sell |
| `quantity` | float | Ordered quantity |
| `fill_quantity` | float | Filled quantity (for this event) |
| `fill_price` | float | Fill price (if filled) |
| `order_type` | string | Market or Limit |
| `limit_price` | float | Limit price (if limit order) |
| `market_price_at_submit` | float | Market price when order was submitted |
| `tag` | string | Execution metadata (tier, signal, week_id, scale_day) |

## Tag Format

Order tags encode execution metadata:

```
tier=strong;signal=0.8234;week_id=2023-06-05;scale_day=2
```

Parse with `core.formatting.extract_week_id_from_tag()`.

## Notes

- ObjectStore CSV export via API requires an Institutional account
- For parity verification, use the backtest statistics API instead (see [parity.md](parity.md))
- Dividends are informational under Adjusted pricing mode; do not subtract from NAV reconciliation
