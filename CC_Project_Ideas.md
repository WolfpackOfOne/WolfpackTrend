# WolfpackTrend Project Ideas

30 project ideas for modifying the WolfpackTrend algorithm. Each project starts from the existing codebase and requires a single focused change. Present your backtest results (Sharpe, Sortino, Calmar, drawdown, total return) versus the baseline and explain **why** the change helped or hurt.

---

## Easy (Parameter & Universe Changes)

These projects modify existing parameters or swap data inputs. No new classes or logic required.

---

### E1. Change the Stock Universe

**Description:** The strategy currently trades a static list of 30 DOW stocks. Replace this universe with a different set of equities to test whether trend-following works better on different asset types. For example, try a tech-heavy NASDAQ subset, a defensive sector (utilities, staples), or a set of international ETFs. The hypothesis is that stocks with stronger momentum characteristics (e.g., tech) may produce better trend signals.

**Files to modify:**
- `shared/universe.py` — Replace the `EQUITY_UNIVERSE` list with your chosen tickers

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Compare overall performance metrics (Sharpe, Sortino, Calmar, drawdown)
- `research/signal/signal_distribution_dashboard.ipynb` — See how signal magnitude distributions differ across your new universe
- `research/universe_selection/01_signal_evolution_by_equity.ipynb` — Visualize per-stock signal behavior over time

---

### E2. Tune the SMA Signal Weights

**Description:** The alpha model blends three SMA horizons (20-day, 63-day, 252-day) using weights `(0.2, 0.5, 0.3)`. The medium-term trend currently dominates. By shifting weight toward the short-term SMA, the strategy becomes more reactive (more trades, faster entries/exits). By shifting toward the long-term SMA, the strategy becomes smoother (fewer trades, longer holding periods). This tests which time horizon carries the most predictive power for this universe.

**Files to modify:**
- `config.py` — Change `ALPHA_SIGNAL_WEIGHTS` tuple (recommended to sum to 1.0 for comparability; current code enforces length=3, not sum)

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/signal/signal_profitability_stats.ipynb` — Does the hit rate change with different weight profiles?
- `research/trading/rebalance_week_health.ipynb` — How does turnover change?

---

### E3. Adjust Signal Temperature

**Description:** After computing the raw composite trend score, it is divided by a "temperature" parameter and passed through `tanh()` to produce a signal in (-1, +1). Low temperature (e.g., 1.0) makes signals more binary (close to +1 or -1), meaning the strategy takes full-conviction positions. High temperature (e.g., 10.0) compresses signals toward zero, meaning positions are smaller and more nuanced. This directly controls how aggressively the strategy responds to trend signals.

**Files to modify:**
- `config.py` — Change `ALPHA_SIGNAL_TEMPERATURE` (try 1.0, 2.0, 5.0, 10.0)

**Where the logic lives:** `core/math_utils.py` — `compute_composite_signal()` function applies `tanh(score / temperature)`

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/signal/signal_distribution_dashboard.ipynb` — Visualize how signal distributions compress or expand
- `research/exposure/02_portfolio_vol_vs_target.ipynb` — Does realized vol track the target differently?

---

### E4. Modify Target Volatility

**Description:** The portfolio construction model scales all positions so the portfolio targets 10% annualized volatility. Lowering this (e.g., 5%) creates a more conservative strategy with smaller positions and lower drawdowns. Raising it (e.g., 15-20%) amplifies returns but increases drawdown and leverage. This is the primary risk dial for the strategy. Key question: do risk-adjusted metrics (Sharpe, Sortino) stay constant as you scale, or does the strategy have a "sweet spot"?

**Files to modify:**
- `main.py` — Change `target_vol_annual` parameter in the `TargetVolPortfolioConstructionModel` constructor

**Where the logic lives:** `risk/portfolio.py` — `CreateTargets()` scales weights by `target_vol / estimated_vol`

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison across vol targets
- `research/exposure/02_portfolio_vol_vs_target.ipynb` — Does realized vol actually hit the target?
- `research/exposure/04_exposure_split_plots.ipynb` — How does gross/net exposure change?
- `research/risk/portfolio_volatility.ipynb` — Rolling realized vol vs. target

---

### E5. Change the Rebalance Frequency

**Description:** The strategy recalculates signals every 5 trading days (weekly). Between rebalances, it re-emits cached signals to drive position scaling. Changing this interval affects how quickly the strategy responds to new information versus how much it trades. Daily rebalancing (1) captures trends faster but generates more orders. Monthly rebalancing (21) reduces turnover but may miss reversals. This tests the optimal tradeoff between signal freshness and transaction costs.

**Files to modify:**
- `main.py` — Change `rebalance_interval_trading_days` parameter passed to both the alpha model and portfolio construction model

**Where the logic lives:**
- `signals/alpha.py` — `Update()` method uses `self.rebalance_interval_trading_days` to decide fresh-signal vs. cached-signal days
- `risk/portfolio.py` — `CreateTargets()` uses `self.rebalance_interval_trading_days` for its own rebalance counter

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/trading/rebalance_week_health.ipynb` — Fill rates per rebalance cycle
- `research/trading/scaling_adherence.ipynb` — Does scaling still work with longer/shorter cycles?
- `research/slippage_analysis.ipynb` — Does slippage change with frequency?

---

### E6. Adjust Exposure Caps

**Description:** The strategy enforces three portfolio constraints: max gross exposure (150%), max net exposure (50%), and max per-name weight (10%). These are applied in sequence in `core/math_utils.py`. Tightening gross exposure (e.g., 100%) forces more conservative sizing. Loosening net exposure (e.g., 100%) allows larger directional bets. Changing per-name weight (e.g., 5% or 20%) affects concentration. This tests how constraint design affects risk-adjusted performance.

**Files to modify:**
- `main.py` — Change `max_gross`, `max_net`, and/or `max_weight` in the `TargetVolPortfolioConstructionModel(...)` constructor

**Where the logic lives:** `core/math_utils.py` — `apply_per_name_cap()`, `apply_gross_cap()`, `apply_net_cap()` functions

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/exposure/01_concentration_risk.ipynb` — Herfindahl index and top-N concentration
- `research/exposure/03_exposure_regime_dashboard.ipynb` — Gross/net exposure over time
- `research/exposure/04_exposure_split_plots.ipynb` — Long vs. short exposure breakdown

---

### E7. Modify the Dead-Band Tolerance

**Description:** When the portfolio rebalances, it classifies each position as HOLD if the current weight is within a "dead-band" of the target weight (currently 1.5%). Positions classified as HOLD generate no orders, reducing turnover. A smaller dead-band (e.g., 0.5%) makes the strategy more precise but generates more orders. A larger dead-band (e.g., 3-5%) allows significant drift before rebalancing. This directly tests the tradeoff between tracking precision and transaction costs.

**Files to modify:**
- `main.py` — Change `rebalance_dead_band` parameter

**Where the logic lives:** `risk/portfolio.py` — `_classify_symbols()` uses `dead_band` (`self.rebalance_dead_band`) to determine HOLD vs. RESIZE

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/trading/rebalance_week_health.ipynb` — How many symbols trade per rebalance?
- `research/position_monitor.ipynb` — Position weight drift over time
- `research/slippage_analysis.ipynb` — Total slippage cost vs. dead-band setting

---

### E8. Change the Backtest Window

**Description:** The baseline backtest runs from 2022-01-01 to 2024-01-01, covering a rising-rate, mixed-trend environment. Running the same strategy over different market regimes tests robustness. Try the COVID crash (2019-2021), the post-COVID rally (2020-2022), a low-volatility period (2016-2018), or a full decade (2015-2025). The hypothesis is that trend-following performs best in trending markets and worst in choppy, range-bound periods.

**Files to modify:**
- `main.py` — Change `self.SetStartDate()` and `self.SetEndDate()` in `Initialize()`

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison across regimes
- `research/risk/risk_metrics.ipynb` — Drawdown behavior in different regimes
- `research/signal/signal_direction_persistence.ipynb` — Do signals persist longer in trending vs. choppy markets?
- `research/exposure/03_exposure_regime_dashboard.ipynb` — How does exposure adapt to different regimes?

---

### E9. Switch the SMA Periods

**Description:** The alpha model uses 20/63/252-day SMAs corresponding roughly to 1-month, 3-month, and 1-year trends. Faster periods (e.g., 10/30/120) detect trend changes sooner but produce more false signals. Slower periods (e.g., 50/100/300) are more reliable but enter/exit later. This tests which combination of lookback windows best captures tradeable trends in the DOW 30.

**Files to modify:**
- `main.py` — Change `short_period`, `medium_period`, `long_period` arguments passed to `CompositeTrendAlphaModel(...)`. Also adjust warmup (`self.SetWarmUp(...)`) to be at least as long as your longest SMA.

**Where the logic lives:** `signals/alpha.py` — `_track_symbol()` registers the three horizon indicators via `algorithm.SMA(...)`

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/signal/signal_profitability_stats.ipynb` — Hit rate with different SMA speeds
- `research/signal/signal_what_and_why.ipynb` — Inspect individual signal decisions
- `research/trading/stale_signal_risk.ipynb` — Do slower SMAs produce staler signals?

---

### E10. Raise the Minimum Signal Threshold

**Description:** Signals with magnitude below `ALPHA_MIN_MAGNITUDE` (currently 0.05) are discarded. Raising this threshold (e.g., 0.15, 0.25, or 0.40) filters out weak, low-conviction signals, meaning the strategy only trades when the trend is strong. This reduces the number of active positions and concentrates capital in high-conviction names. The tradeoff is missing genuine early-stage trends that start weak and strengthen.

**Files to modify:**
- `config.py` — Change `ALPHA_MIN_MAGNITUDE`

**Where the logic lives:** `core/math_utils.py` — `compute_composite_signal()` returns `None` when `abs(magnitude) < min_magnitude`

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/signal/signal_distribution_dashboard.ipynb` — How many signals get filtered at different thresholds?
- `research/signal/signal_profitability_stats.ipynb` — Are weak signals unprofitable? Does filtering them help?
- `research/position_monitor.ipynb` — How many positions are held at any time?

---

## Medium (Logic & Model Changes)

These projects require modifying or extending existing model logic. Typically involves editing one model file plus `main.py`.

---

### M1. Add a Volume Filter to the Alpha Model

**Description:** The current alpha model generates signals purely from price (SMA distances). Volume is a classic confirmation indicator: a trend accompanied by above-average volume is more likely to persist. Add a condition that suppresses signal emission when a stock's recent average volume is below its longer-term volume average. This tests the "volume confirms trend" hypothesis. You'll need to add a volume indicator (e.g., 20-day vs. 50-day volume SMA) to the alpha model's indicator dictionary.

**Files to modify:**
- `signals/alpha.py` — Add volume indicators in `_track_symbol()`, add volume check in `_compute_signals()` before emitting

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/signal/signal_profitability_stats.ipynb` — Do volume-confirmed signals have higher hit rates?
- `research/signal/signal_distribution_dashboard.ipynb` — How many signals does the volume filter remove?
- `research/trading/volume_decomposition_by_signal_and_trade_type.ipynb` — Volume patterns around signal generation

---

### M2. Implement ATR-Based Position Sizing

**Description:** Currently, all positions are sized by target-volatility scaling using portfolio-level diagonal variance. An alternative is to size each position inversely by its own ATR: stocks with larger ATR (more volatile) get smaller positions. This is a simpler, per-stock risk budgeting approach. Implement this by modifying the weight normalization step in the portfolio construction model to divide raw weights by each stock's ATR before normalizing.

**Files to modify:**
- `risk/portfolio.py` — Modify `CreateTargets()` to incorporate per-symbol ATR into weight calculation. You'll need to access ATR values from the alpha model (they're already computed in `signals/alpha.py`)
- `main.py` — May need to pass ATR data from the alpha model to the PCM

**Where the existing ATR lives:** `signals/alpha.py` — `self.atr[symbol]` stores the `AverageTrueRange(atr_period)` indicator

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/risk/portfolio_volatility.ipynb` — Does ATR-based sizing produce more stable realized vol?
- `research/exposure/01_concentration_risk.ipynb` — Does ATR sizing change concentration?
- `research/position_monitor.ipynb` — Compare position size distributions

---

### M3. Add a Momentum Ranking Filter

**Description:** Instead of trading all 30 stocks that pass the signal threshold, rank them by signal magnitude and only emit insights for the top N (e.g., top 10 or top 15). This concentrates capital in the strongest trends rather than spreading it across all signals. The hypothesis is that higher-conviction signals are more profitable, and diluting capital into weak signals hurts returns. Implement by sorting signals in the alpha model and truncating before emission.

**Files to modify:**
- `signals/alpha.py` — In `Update()`, after computing all signals, sort by magnitude and only emit the top N. Add a `max_positions` parameter to `__init__()`
- `main.py` — Pass `max_positions` parameter to the alpha model

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/signal/signal_profitability_stats.ipynb` — Are top-ranked signals more profitable?
- `research/exposure/01_concentration_risk.ipynb` — How concentrated does the portfolio become?
- `research/position_monitor.ipynb` — Number of active positions over time

---

### M4. Implement Asymmetric Scaling Schedules

**Description:** Currently, both entries and exits scale over 5 days using the same schedule. In practice, you may want to enter slowly (to get better prices) but exit quickly (to cut losses). Or vice versa: enter quickly on strong signals but exit gradually to avoid market impact. Modify the portfolio construction model to use different scaling behavior for entries vs. exits. For example, exits could execute at 100% on day 1 (immediate) while entries still scale over 5 days.

**Files to modify:**
- `risk/portfolio.py` — In `CreateTargets()`, check the classification (NEW_ENTRY/FLIP vs. EXIT) and apply different scaling logic. Currently EXIT symbols already get immediate 0% targets. The change would be to also apply this to RESIZE when the new target is smaller than current.
- `core/math_utils.py` — Optionally add a separate `build_scaling_schedule()` call for exit schedules

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/trading/scaling_adherence.ipynb` — Verify asymmetric scaling is working
- `research/risk/risk_metrics.ipynb` — Does faster exit reduce drawdown?
- `research/slippage_analysis.ipynb` — Does entry/exit asymmetry affect fill quality?

---

### M5. Add a Drawdown Circuit Breaker

**Description:** When the portfolio draws down beyond a threshold (e.g., -10% from peak), reduce all position sizes or go flat entirely. This is a common institutional risk management feature. The circuit breaker activates during severe drawdowns and deactivates when NAV recovers above a re-entry threshold (e.g., -5% from peak). During activation, multiply all target weights by a reduction factor (e.g., 0.0 for full flat, 0.5 for half-size).

**Files to modify:**
- `main.py` — Track peak NAV and current drawdown in `OnData()`. Pass a `drawdown_multiplier` to the PCM
- `risk/portfolio.py` — In `CreateTargets()`, multiply all weights by the drawdown multiplier before applying constraints

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison (especially max drawdown and Calmar ratio)
- `research/risk/risk_metrics.ipynb` — Drawdown depth and duration with vs. without circuit breaker
- `research/timeseries_plotter.ipynb` — Overlay NAV curves with circuit breaker activation periods
- `research/exposure/03_exposure_regime_dashboard.ipynb` — Gross exposure drops during circuit breaker activation

---

### M6. Replace SMA with EMA Indicators

**Description:** Simple Moving Averages (SMA) weight all observations equally. Exponential Moving Averages (EMA) weight recent observations more heavily, making them more responsive to recent price changes. This tests whether faster-reacting indicators improve signal timing and catch trend reversals sooner, or whether they generate more whipsaw (false signals). QuantConnect provides `ExponentialMovingAverage` as a drop-in replacement.

**Files to modify:**
- `signals/alpha.py` — In `_track_symbol()`, replace `algorithm.SMA(...)` with `algorithm.EMA(...)` for each horizon (or wire `ExponentialMovingAverage` indicators manually). The rest of the signal computation logic stays the same.

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/signal/signal_direction_persistence.ipynb` — Do EMA signals flip direction more often?
- `research/signal/signal_profitability_stats.ipynb` — Hit rate comparison
- `research/signal/signal_what_and_why.ipynb` — Inspect specific signal timing differences

---

### M7. Add a Regime Filter Using a Market Index

**Description:** Add SPY (or another broad index) as a regime indicator. When SPY is above its 200-day SMA, only allow long positions. When SPY is below its 200-day SMA, only allow short positions (or go flat). This tests whether filtering individual stock signals by the broad market trend improves performance by avoiding counter-trend trades in bear/bull markets. The filter requires adding SPY as a separate security and tracking its own SMA indicator.

**Files to modify:**
- `signals/alpha.py` — Add SPY as a special symbol with its own SMA. In `_compute_signals()`, check SPY regime before emitting each symbol's insight. Suppress long signals in bear regime and short signals in bull regime.
- `main.py` — Add SPY to the universe (if not already present) and ensure it's passed to the alpha model

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/signal/signal_distribution_dashboard.ipynb` — How many signals does the regime filter suppress?
- `research/exposure/03_exposure_regime_dashboard.ipynb` — Gross/net exposure should shift with regime
- `research/risk/beta_vs_spy.ipynb` — Does regime filtering reduce market beta?

---

### M8. Implement Dynamic Rebalance Frequency

**Description:** Instead of rebalancing on a fixed 5-day cycle, trigger a rebalance whenever the aggregate change in signals exceeds a threshold. Compute the sum of absolute signal changes since the last rebalance; if it exceeds (e.g., 0.5), rebalance immediately. This makes the strategy event-driven: it rebalances quickly during volatile markets but holds steady in calm periods. This is more efficient than fixed-frequency rebalancing.

**Files to modify:**
- `signals/alpha.py` — In `Update()`, compute signals every day (not just on rebalance days). Compare current signals to `cached_signals`. If the sum of absolute changes exceeds a threshold, treat today as a rebalance day. Otherwise, re-emit cached signals.
- `main.py` — Add a `signal_change_threshold` parameter

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/trading/rebalance_week_health.ipynb` — How often does the strategy actually rebalance?
- `research/signal/signal_direction_persistence.ipynb` — Does dynamic rebalancing catch direction changes faster?
- `research/slippage_analysis.ipynb` — Does event-driven rebalancing reduce or increase total trading costs?

---

### M9. Improve Volatility Scaling Accuracy (Correlation-Aware Position Sizing)

**Description:** The current portfolio volatility estimate uses a diagonal approximation (ignores cross-correlations between stocks). This underestimates true portfolio risk when stocks are positively correlated and overestimates when they're negatively correlated. Implement a full covariance matrix using rolling pairwise correlations, then calibrate the estimator so estimated volatility tracks realized volatility more closely. This is the most direct project for improving accuracy in `research/exposure/02_portfolio_vol_vs_target.ipynb`. The tradeoff is computational complexity and estimation noise with limited history.

**Files to modify:**
- `core/math_utils.py` — Replace `estimate_portfolio_vol()` with a version that computes the full covariance matrix from rolling returns
- `risk/portfolio.py` — (optional but recommended) expose/tune `vol_lookback` and `min_obs` used by `_estimate_portfolio_vol()` so students can calibrate tracking accuracy

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/risk/portfolio_volatility.ipynb` — Does realized vol track the target better with full covariance?
- `research/risk/correlation_risk.ipynb` — Visualize the correlation structure being used
- `research/exposure/02_portfolio_vol_vs_target.ipynb` — Estimated vs. realized volatility comparison

---

### M10. Change the Execution Model to Use Market Orders

**Description:** The current execution model uses tiered limit orders with different offsets based on signal strength. A simpler approach is to use market orders for everything, accepting immediate execution at the market price. This tests whether the complexity of the limit order system actually improves performance, or whether the missed fills and stale orders outweigh the price improvement from limits. This is a great project for understanding execution quality.

**Files to modify:**
- `execution/execution.py` — In `Execute()`, replace the tiered limit order logic with simple `MarketOrder()` calls for all targets. Remove the stale order cancellation logic since market orders fill immediately.

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/slippage_analysis.ipynb` — Compare slippage: limit fills vs. market fills
- `research/trading/limit_spread_vs_fill.ipynb` — Baseline limit order fill quality (for comparison)
- `research/trading/order_lifecycle.ipynb` — Order lifecycle should be much simpler with market orders

---

## Hard (Architectural & Research-Intensive Changes)

These projects require adding new models, significant research, or architectural changes across multiple files.

---

### H1. Implement a Multi-Factor Alpha Model

**Description:** The current alpha model uses only trend (SMA distance) as its signal source. Academic research shows that combining multiple factors (trend, value, quality, mean-reversion) can improve risk-adjusted returns through diversification of signal sources. Build a new alpha model that blends the existing trend signal with at least one additional factor such as RSI-based mean-reversion, fundamental data (P/E ratio), or a volatility-adjusted momentum score. The challenge is designing a principled weighting scheme between factors.

**Files to modify/create:**
- `signals/alpha.py` — Extend `CompositeTrendAlphaModel` or create a new alpha model class that adds RSI, fundamental, or other indicators alongside the existing SMAs
- `core/math_utils.py` — Add a new pure function for computing the multi-factor composite score
- `main.py` — Wire the new alpha model and pass additional parameters
- `models/__init__.py` — Export the new model

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/signal/signal_profitability_stats.ipynb` — Compare hit rates of trend-only vs. multi-factor signals
- `research/signal/signal_distribution_dashboard.ipynb` — How does the signal distribution change with multiple factors?
- `research/risk/portfolio_volatility.ipynb` — Does factor diversification reduce portfolio volatility?

---

### H2. Build an Adaptive Signal Temperature

**Description:** The signal temperature is currently fixed at 3.0. In high-volatility markets, raw trend scores are naturally larger, so a fixed temperature may produce excessively aggressive signals. In low-volatility markets, scores are smaller, making signals too weak. Build an adaptive temperature that scales with recent realized market volatility (e.g., 20-day rolling vol of SPY or the VIX index). In calm markets, lower the temperature for stronger signals; in volatile markets, raise it for dampened signals. This creates a self-regulating signal system.

**Files to modify:**
- `signals/alpha.py` — Add a rolling volatility indicator (e.g., on SPY). Compute dynamic temperature as a function of current vol vs. historical average vol. Pass the dynamic temperature to `compute_composite_signal()` instead of the static value.
- `core/math_utils.py` — `compute_composite_signal()` already accepts temperature as a parameter, so no change needed here
- `main.py` — Add SPY if needed, remove the static temperature parameter

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/signal/signal_distribution_dashboard.ipynb` — Do signals become more stable across regimes?
- `research/exposure/02_portfolio_vol_vs_target.ipynb` — Does adaptive temperature help realized vol track the target?
- `research/risk/portfolio_volatility.ipynb` — Rolling vol analysis

---

### H3. Implement a Risk Parity Portfolio Construction Model

**Description:** Replace the current target-volatility sizing with a risk parity approach where each position contributes equally to total portfolio risk. In the current model, positions are sized by signal strength and then scaled to a vol target. In risk parity, the weight of each position is determined so that its marginal contribution to portfolio variance equals 1/N of total variance. This requires computing the covariance matrix of returns and iteratively solving for weights (e.g., using the Maillard-Roncalli-Teiletche algorithm). This is one of the most well-known portfolio construction techniques in institutional finance.

**Files to modify/create:**
- `risk/portfolio.py` — Replace or supplement `TargetVolPortfolioConstructionModel` with a new `RiskParityPortfolioConstructionModel` class
- `core/math_utils.py` — Add a `solve_risk_parity_weights()` function that takes a covariance matrix and returns weights with equal risk contribution
- `main.py` — Wire the new PCM
- `models/__init__.py` — Export the new model

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/risk/portfolio_volatility.ipynb` — Is portfolio vol more stable under risk parity?
- `research/risk/correlation_risk.ipynb` — Understand the correlation structure driving weight allocation
- `research/exposure/01_concentration_risk.ipynb` — Risk parity should produce more balanced concentration

---

### H4. Add a Stop-Loss and Trailing-Stop System

**Description:** The current strategy only exits positions when the trend signal reverses or weakens below threshold. Adding stop-losses (exit if a position loses more than X% or 2x ATR from entry) and trailing stops (ratchet the stop level up as the position profits) provides downside protection independent of the signal cycle. This requires tracking per-position entry prices, computing stop levels daily, and overriding normal signal logic when stops are triggered. The challenge is integrating stop logic with the existing scaling and rebalance system without conflicts.

**Files to modify:**
- `risk/portfolio.py` — Track entry prices per symbol. On each rebalance, check if current price has breached the stop level. If so, override the signal-based target to 0% (exit).
- `main.py` — Add stop-loss parameters (e.g., `stop_loss_atr_multiple`, `trailing_stop_atr_multiple`) and pass them to the PCM
- `execution/execution.py` — Stop-triggered exits should use market orders for immediate execution

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison (especially max drawdown and Calmar)
- `research/risk/risk_metrics.ipynb` — Drawdown depth and duration with stops
- `research/signal/signal_profitability_stats.ipynb` — Do stops cut losing trades sooner?
- `research/position_monitor.ipynb` — Track stop activations and early exits

---

### H5. Build a Dynamic Universe Selection Model

**Description:** Replace the static 30-stock universe with a dynamic universe that selects stocks from a larger pool (e.g., S&P 500 constituents) based on a screening criterion refreshed monthly. Possible screens: top 30 by 12-month momentum, top 30 by average daily volume, top 30 by trend signal strength, or a sector-balanced selection. This requires implementing QuantConnect's `UniverseSelectionModel` interface, which controls which securities the algorithm trades. The challenge is handling securities being added/removed from the universe mid-backtest.

**Files to modify/create:**
- Create a new file (e.g., `signals/universe.py`) implementing `FundamentalUniverseSelectionModel` or `ManualUniverseSelectionModel`
- `main.py` — Replace the static `AddEquity()` loop with `self.SetUniverseSelection(YourModel())`
- `signals/alpha.py` — Handle symbols entering and leaving the universe gracefully (indicator warmup, signal cache cleanup)

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/universe_selection/02_weekly_selection_diagnostics.ipynb` — Universe turnover diagnostics
- `research/universe_selection/03_symbol_stickiness_and_why.ipynb` — How often do stocks rotate in/out?
- `research/universe_selection/01_signal_evolution_by_equity.ipynb` — Per-stock signal behavior for dynamically selected stocks

---

### H6. Implement a Pairs/Relative-Value Overlay

**Description:** Instead of trading absolute trends, identify pairs of correlated stocks and trade the spread between them. Compute rolling correlations to find pairs (e.g., KO/PG, JPM/GS). For each pair, calculate the z-score of the price spread. When the spread widens beyond a threshold (e.g., z > 2), go long the underperformer and short the outperformer. This is a fundamentally different signal source (mean-reversion of relative value) that can be combined with or replace the existing trend signals.

**Files to modify/create:**
- Create a new alpha model (e.g., `signals/pairs_alpha.py`) that identifies pairs, computes spread z-scores, and emits pair-based insights
- `core/math_utils.py` — Add pure functions for rolling correlation, spread z-score computation
- `main.py` — Wire the new alpha model (either replacing or combining with the trend alpha)
- `models/__init__.py` — Export the new model

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/risk/correlation_risk.ipynb` — Identify candidate pairs from the correlation matrix
- `research/signal/signal_distribution_dashboard.ipynb` — Spread z-score signal distributions
- `research/risk/beta_vs_spy.ipynb` — Pairs trading should be more market-neutral (lower beta)

---

### H7. Add Transaction Cost Modeling and Optimization

**Description:** The baseline strategy uses zero commissions and doesn't model bid-ask spread or market impact. Add realistic cost estimates: commissions (e.g., $0.005/share), half-spread (e.g., 2-5 bps for large-cap), and market impact (proportional to order size / ADV). Then modify the rebalance logic to only trade when expected alpha (signal magnitude) exceeds estimated round-trip cost. This creates a cost-aware dead-band that dynamically adjusts by stock and market conditions. The challenge is accurately estimating costs and integrating them into the decision logic.

**Files to modify:**
- `main.py` — Set realistic commissions using `self.SetSecurityInitializer()` or per-security fee models
- `risk/portfolio.py` — In `_classify_symbols()`, compute estimated round-trip cost and only classify as RESIZE if expected alpha exceeds cost
- `core/math_utils.py` — Add a `compute_estimated_cost()` function

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison (net of costs)
- `research/slippage_analysis.ipynb` — Compare realized execution costs
- `research/trading/rebalance_week_health.ipynb` — How many trades does cost-awareness eliminate?
- `research/trading/order_lifecycle.ipynb` — Order count and fill quality

---

### H8. Implement Cross-Sectional Momentum (Long-Short)

**Description:** Replace the absolute trend alpha (is the stock above its SMA?) with a cross-sectional momentum alpha (is the stock outperforming its peers?). Rank all universe stocks by 12-month return minus 1-month return (the "12-1 momentum" factor from academic literature). Go long the top quintile (top 6 stocks) and short the bottom quintile. This is a well-documented anomaly in academic finance. The key difference from the current strategy is that signals are relative (rank-based) rather than absolute (price vs. SMA).

**Files to modify/create:**
- Create a new alpha model (e.g., `signals/cross_sectional_alpha.py`) that computes 12-1 momentum, ranks stocks, and emits long insights for top quintile and short insights for bottom quintile
- `main.py` — Wire the new alpha model, adjust warmup period (needs 252+ days)
- `models/__init__.py` — Export the new model
- `core/math_utils.py` — Add a `compute_cross_sectional_momentum()` function

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/signal/signal_distribution_dashboard.ipynb` — Momentum score distributions
- `research/signal/signal_profitability_stats.ipynb` — Is top-quintile momentum profitable?
- `research/risk/beta_vs_spy.ipynb` — Long-short momentum should have lower market beta

---

### H9. Apply Machine Learning to Position Sizing

**Description:** Train a simple ML model to predict optimal position sizes using features available at signal time: signal magnitude, rolling volatility, recent return, volume ratio, ATR, and correlation with SPY. Use the QuantConnect research environment to train on historical data (from ObjectStore CSVs), then deploy the trained model in the algorithm. The model could predict expected return or expected Sharpe contribution per position, which then drives sizing. This is the most research-intensive project and requires comfort with scikit-learn or similar libraries.

**Files to modify/create:**
- Create a new research notebook (e.g., `research/ml_position_sizing.ipynb`) to train the model using ObjectStore data (this file does not exist yet in the repo)
- Create a new module (e.g., `risk/ml_portfolio.py`) implementing a portfolio construction model that uses the trained model's predictions for sizing
- `main.py` — Wire the ML-based PCM, load the trained model from ObjectStore
- Save the trained model to ObjectStore so the algorithm can load it

**Notebooks for analysis:**
- `research/ml_position_sizing.ipynb` — (new; create this notebook first) Model training, feature importance, cross-validation
- `research/TearSheet_CC.ipynb` — Performance comparison
- `research/signal/signal_profitability_stats.ipynb` — Does ML sizing improve per-signal profitability?
- `research/risk/portfolio_volatility.ipynb` — Does ML sizing produce more stable risk?

---

### H10. Build an Ensemble of Alpha Models

**Description:** Run multiple alpha models simultaneously and combine their signals. For example: (1) the existing trend model, (2) a mean-reversion model using RSI, and (3) a volume-breakout model. Each model emits independent insights. A custom portfolio construction model (or an insight combiner) merges the signals using a weighting scheme: equal weight, inverse-volatility weighted, or weights learned from historical performance. This tests whether signal diversification improves risk-adjusted returns, similar to how a fund-of-funds diversifies across strategies.

**Files to modify/create:**
- Create additional alpha models (e.g., `signals/mean_reversion_alpha.py`, `signals/breakout_alpha.py`)
- Create an ensemble combiner (e.g., `signals/ensemble.py`) or use QuantConnect's `CompositeAlphaModel`
- `risk/portfolio.py` — Modify `CreateTargets()` to handle insights from multiple sources, or build a new PCM
- `main.py` — Wire multiple alpha models using `self.AddAlpha(CompositeAlphaModel(model1, model2, model3))`
- `models/__init__.py` — Export new models

**Notebooks for analysis:**
- `research/TearSheet_CC.ipynb` — Performance comparison: individual models vs. ensemble
- `research/signal/signal_distribution_dashboard.ipynb` — Signal distributions per model
- `research/signal/signal_profitability_stats.ipynb` — Hit rates per model and combined
- `research/risk/portfolio_volatility.ipynb` — Does ensemble reduce portfolio volatility through signal diversification?

---

## Presentation Guidelines

For each project, your presentation should include:

1. **Hypothesis**: What do you expect to happen and why?
2. **Implementation**: What code did you change? (show key diffs)
3. **Results**: Side-by-side performance table (baseline vs. modified)
   - Total Return, Sharpe Ratio, Sortino Ratio, Calmar Ratio, Max Drawdown
4. **Analysis**: Did the results match your hypothesis? What did you learn?
5. **Limitations**: What are the caveats or risks of your approach?

### Relevant Research Notebooks

All notebooks read from ObjectStore CSVs generated by the backtest. After running your modified backtest, the same notebooks will automatically reflect your changes (as long as you use the same `TEAM_ID` in `config.py` or set your own team ID to separate your data).

| Category | Notebook | What It Shows |
|----------|----------|---------------|
| **Performance** | `research/TearSheet_CC.ipynb` | Sharpe, Sortino, Calmar, drawdown, total return |
| **Signals** | `research/signal/signal_distribution_dashboard.ipynb` | Signal magnitude histograms and statistics |
| **Signals** | `research/signal/signal_profitability_stats.ipynb` | Per-signal P&L attribution and hit rates |
| **Signals** | `research/signal/signal_direction_persistence.ipynb` | How long signals persist before flipping |
| **Signals** | `research/signal/signal_what_and_why.ipynb` | Drill into individual signal decisions |
| **Risk** | `research/risk/portfolio_volatility.ipynb` | Rolling realized vol vs. target |
| **Risk** | `research/risk/risk_metrics.ipynb` | Drawdown depth, duration, recovery |
| **Risk** | `research/risk/correlation_risk.ipynb` | Pairwise correlation heatmaps |
| **Risk** | `research/risk/beta_vs_spy.ipynb` | Market beta over time |
| **Exposure** | `research/exposure/01_concentration_risk.ipynb` | Herfindahl index, top-N weights |
| **Exposure** | `research/exposure/02_portfolio_vol_vs_target.ipynb` | Estimated vs. realized volatility |
| **Exposure** | `research/exposure/03_exposure_regime_dashboard.ipynb` | Gross/net exposure time series |
| **Exposure** | `research/exposure/04_exposure_split_plots.ipynb` | Long vs. short exposure breakdown |
| **Trading** | `research/trading/rebalance_week_health.ipynb` | Fills and activity per rebalance |
| **Trading** | `research/trading/scaling_adherence.ipynb` | Actual vs. planned scaling schedule |
| **Trading** | `research/trading/order_lifecycle.ipynb` | Order submission → fill → cancel flow |
| **Trading** | `research/trading/limit_spread_vs_fill.ipynb` | Limit order price improvement |
| **Trading** | `research/trading/stale_signal_risk.ipynb` | Signals held too long without update |
| **Trading** | `research/slippage_analysis.ipynb` | Fill price vs. market price at submission |
| **Positions** | `research/position_monitor.ipynb` | Daily position counts and weights |
| **Universe** | `research/universe_selection/01_signal_evolution_by_equity.ipynb` | Per-stock signal over time |
