import math
from datetime import timedelta
from AlgorithmImports import *


class CompositeTrendAlphaModel(AlphaModel):
    """
    Composite trend-following alpha model using 3 horizons (short/medium/long).
    Emits daily insights with direction and magnitude based on price distance
    from moving averages, normalized by ATR.

    Signals are recalculated every rebalance_interval_trading_days trading days.
    On non-rebalance days, cached signals are re-emitted to trigger the
    daily scaling pipeline in the PCM and execution model.
    """

    def __init__(self, short_period=20, medium_period=63, long_period=252,
                 atr_period=14, rebalance_interval_trading_days=5,
                 logger=None, algorithm=None):
        self.short_period = short_period
        self.medium_period = medium_period
        self.long_period = long_period
        self.atr_period = atr_period
        self.rebalance_interval_trading_days = max(1, int(rebalance_interval_trading_days))

        # Weights for composite score
        self.weight_short = 0.5
        self.weight_medium = 0.3
        self.weight_long = 0.2

        # Minimum magnitude threshold to emit insight
        self.min_magnitude = 0.05

        # Indicators keyed by symbol
        self.sma_short = {}
        self.sma_medium = {}
        self.sma_long = {}
        self.atr = {}

        # Track last emit date to prevent duplicate same-day emission
        self.last_emit_date = None

        # Trading-day counter for rebalance interval
        self.trading_days_since_rebalance = None  # None = first day triggers rebalance

        # Cached signals from last rebalance: symbol -> (direction, magnitude)
        self.cached_signals = {}

        # Optional logger for signal tracking
        self.logger = logger

        # Algorithm reference for Debug logging
        self.algorithm = algorithm

    def Update(self, algorithm, data):
        insights = []
        self._ensure_indicators_from_data(algorithm, data)

        # Don't emit during warmup — prevents insight deduplication issues
        if algorithm.IsWarmingUp:
            return insights

        # Wait for a data slice that actually contains bars for tracked symbols.
        # This avoids consuming the daily emit slot on empty slices.
        has_relevant_bars = any(data.Bars.ContainsKey(symbol) for symbol in self.sma_short.keys())
        if not has_relevant_bars:
            return insights

        # Only emit once per calendar day
        current_date = algorithm.Time.date()
        if self.last_emit_date == current_date:
            return insights
        self.last_emit_date = current_date

        # Determine if this is a rebalance day (trading-day counter)
        is_rebalance = False
        if self.trading_days_since_rebalance is None:
            is_rebalance = True
        elif self.trading_days_since_rebalance >= self.rebalance_interval_trading_days:
            is_rebalance = True

        if is_rebalance:
            self.trading_days_since_rebalance = 0
            self.cached_signals = {}
            self._compute_signals(algorithm, data)
            # Set flag on PCM for rebalance vs scaling day
            pcm = getattr(algorithm, 'pcm', None)
            if pcm is not None:
                pcm.is_rebalance_day = True
        else:
            self.trading_days_since_rebalance += 1
            pcm = getattr(algorithm, 'pcm', None)
            if pcm is not None:
                pcm.is_rebalance_day = False

        # Emit insights for all cached signals (fresh or cached)
        for symbol, (direction, mag) in self.cached_signals.items():
            if not data.Bars.ContainsKey(symbol):
                continue

            insight = Insight.Price(
                symbol,
                timedelta(days=1),
                direction,
                None,       # magnitude (optional, not used)
                abs(mag),   # confidence
                None,       # source model
                abs(mag)    # weight
            )
            insights.append(insight)

        # Log summary
        if insights and self.algorithm:
            long_count = sum(1 for i in insights if i.Direction == InsightDirection.Up)
            short_count = len(insights) - long_count
            day_type = "rebalance" if is_rebalance else f"scaling, day {self.trading_days_since_rebalance}/{self.rebalance_interval_trading_days}"
            self.algorithm.Debug(
                f"[{algorithm.Time.strftime('%Y-%m-%d')}] Alpha ({day_type}): "
                f"{len(insights)} signals ({long_count} long, {short_count} short)")

        return insights

    def _compute_signals(self, algorithm, data):
        """Compute fresh signals and store in cached_signals. Log to logger."""
        for symbol in self.sma_short.keys():
            # Check all indicators are ready
            if not self.sma_short[symbol].IsReady:
                continue
            if not self.sma_medium[symbol].IsReady:
                continue
            if not self.sma_long[symbol].IsReady:
                continue
            if not self.atr[symbol].IsReady:
                continue

            # Check bar exists
            if not data.Bars.ContainsKey(symbol):
                continue

            bar = data.Bars[symbol]
            price = bar.Close

            # Get indicator values
            sma_s = self.sma_short[symbol].Current.Value
            sma_m = self.sma_medium[symbol].Current.Value
            sma_l = self.sma_long[symbol].Current.Value
            atr_value = max(self.atr[symbol].Current.Value, 1e-8)

            # Compute distance from each SMA normalized by ATR
            dist_short = (price - sma_s) / atr_value
            dist_medium = (price - sma_m) / atr_value
            dist_long = (price - sma_l) / atr_value

            # Composite score
            score = (self.weight_short * dist_short +
                     self.weight_medium * dist_medium +
                     self.weight_long * dist_long)

            # Smooth bounded magnitude
            mag = math.tanh(score)

            # Skip tiny signals
            if abs(mag) < self.min_magnitude:
                continue

            # Determine direction
            direction = InsightDirection.Up if mag > 0 else InsightDirection.Down

            # Cache signal
            self.cached_signals[symbol] = (direction, mag)

            # Log signal if logger is available
            if self.logger is not None:
                direction_str = "Up" if direction == InsightDirection.Up else "Down"
                self.logger.log_signal(
                    date=algorithm.Time,
                    symbol=symbol,
                    direction=direction_str,
                    magnitude=mag,
                    price=price,
                    sma_short=sma_s,
                    sma_medium=sma_m,
                    sma_long=sma_l,
                    atr=atr_value
                )

    def _ensure_indicators_from_data(self, algorithm, data):
        """Fallback initialization when security-change callbacks are delayed or absent."""
        if not hasattr(data, "Bars"):
            return

        for symbol in data.Bars.Keys:
            self._track_symbol(algorithm, symbol)

    def _track_symbol(self, algorithm, symbol):
        if symbol in self.sma_short:
            return

        # Create indicators
        self.sma_short[symbol] = algorithm.SMA(symbol, self.short_period, Resolution.Daily)
        self.sma_medium[symbol] = algorithm.SMA(symbol, self.medium_period, Resolution.Daily)
        self.sma_long[symbol] = algorithm.SMA(symbol, self.long_period, Resolution.Daily)
        self.atr[symbol] = algorithm.ATR(
            symbol,
            self.atr_period,
            MovingAverageType.Simple,
            Resolution.Daily
        )

    def OnSecuritiesChanged(self, algorithm, changes):
        for security in changes.AddedSecurities:
            self._track_symbol(algorithm, security.Symbol)

        for security in changes.RemovedSecurities:
            symbol = security.Symbol

            # Remove from tracking
            if symbol in self.sma_short:
                del self.sma_short[symbol]
            if symbol in self.sma_medium:
                del self.sma_medium[symbol]
            if symbol in self.sma_long:
                del self.sma_long[symbol]
            if symbol in self.atr:
                del self.atr[symbol]
            # Clean up cached signals for removed symbols
            if symbol in self.cached_signals:
                del self.cached_signals[symbol]
