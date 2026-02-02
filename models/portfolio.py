import math
from AlgorithmImports import *


class TargetVolPortfolioConstructionModel(PortfolioConstructionModel):
    """
    Portfolio construction model that:
    - Converts insights to signed weights
    - Scales portfolio to target annualized volatility (diagonal approximation)
    - Enforces max gross exposure, max net exposure, and per-name caps
    """

    def __init__(self, target_vol_annual=0.10, max_gross=1.50, max_net=0.50,
                 max_weight=0.10, vol_lookback=63):
        self.target_vol_annual = target_vol_annual
        self.max_gross = max_gross
        self.max_net = max_net
        self.max_weight = max_weight
        self.vol_lookback = vol_lookback

        # Minimum observations required for vol estimation
        self.min_obs = 20

        # Rolling returns per symbol
        self.rolling_returns = {}  # symbol -> RollingWindow[float]
        self.prev_close = {}  # symbol -> float

        # Track symbols we're managing
        self.symbols = set()

        # Expected prices at target generation (for slippage tracking)
        self.expected_prices = {}

    def UpdateReturns(self, algorithm, data):
        """
        Update rolling returns incrementally from daily bars.
        Call this once per day from OnData.
        """
        for symbol in self.symbols:
            if not data.Bars.ContainsKey(symbol):
                continue

            bar = data.Bars[symbol]
            close = bar.Close

            if symbol in self.prev_close and self.prev_close[symbol] > 0:
                daily_return = close / self.prev_close[symbol] - 1.0
                if symbol not in self.rolling_returns:
                    self.rolling_returns[symbol] = RollingWindow[float](self.vol_lookback)
                self.rolling_returns[symbol].Add(daily_return)

            self.prev_close[symbol] = close

    def CreateTargets(self, algorithm, insights):
        targets = []

        if not insights:
            return targets

        # Filter to active insights (not expired)
        active_insights = [i for i in insights if i.IsActive(algorithm.UtcTime)]
        if not active_insights:
            return targets

        # Convert insights to signed raw weights
        raw_weights = {}
        for insight in active_insights:
            symbol = insight.Symbol
            sign = 1.0 if insight.Direction == InsightDirection.Up else -1.0
            weight = insight.Weight if insight.Weight else 0.0
            raw_weights[symbol] = sign * weight

        # Normalize to unit gross
        total_abs = sum(abs(w) for w in raw_weights.values())
        if total_abs < 1e-8:
            return targets

        weights = {s: w / total_abs for s, w in raw_weights.items()}

        # Estimate portfolio volatility (diagonal approximation)
        vol_annual = self._estimate_portfolio_vol(weights)

        # Scale to target vol
        if vol_annual is not None and vol_annual > 1e-8:
            scale = self.target_vol_annual / vol_annual
            weights = {s: w * scale for s, w in weights.items()}
        # If vol estimate not available, use scale=1 (no scaling)

        # Apply constraints in order: per-name cap -> gross cap -> net cap
        weights = self._apply_per_name_cap(weights)
        weights = self._apply_gross_cap(weights)
        weights = self._apply_net_cap(weights)

        # Store expected prices for slippage tracking
        self.expected_prices = {}
        for symbol in weights.keys():
            if symbol in algorithm.Securities:
                self.expected_prices[symbol] = algorithm.Securities[symbol].Price

        # Create portfolio targets
        for symbol, weight in weights.items():
            targets.append(PortfolioTarget.Percent(algorithm, symbol, weight))

        # Zero out positions not in current insights
        for symbol in self.symbols:
            if symbol not in weights:
                targets.append(PortfolioTarget.Percent(algorithm, symbol, 0))
                # Also store expected price for exits
                if symbol in algorithm.Securities:
                    self.expected_prices[symbol] = algorithm.Securities[symbol].Price

        return targets

    def _estimate_portfolio_vol(self, weights):
        """
        Estimate annualized portfolio volatility using diagonal approximation.
        Returns None if insufficient data.
        """
        daily_variances = {}

        for symbol in weights.keys():
            if symbol not in self.rolling_returns:
                continue
            window = self.rolling_returns[symbol]
            if window.Count < self.min_obs:
                continue

            # Compute daily variance
            returns = [window[i] for i in range(window.Count)]
            mean_ret = sum(returns) / len(returns)
            variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
            daily_variances[symbol] = variance

        # Need variance for all symbols with non-zero weight
        symbols_with_weight = [s for s, w in weights.items() if abs(w) > 1e-8]
        if not all(s in daily_variances for s in symbols_with_weight):
            return None

        # Portfolio daily variance (diagonal approximation)
        port_var = sum(weights[s] ** 2 * daily_variances[s] for s in symbols_with_weight)

        # Annualize
        vol_annual = math.sqrt(port_var) * math.sqrt(252)
        return vol_annual

    def _apply_per_name_cap(self, weights):
        """Clip each weight to [-max_weight, +max_weight]."""
        return {s: max(-self.max_weight, min(self.max_weight, w)) for s, w in weights.items()}

    def _apply_gross_cap(self, weights):
        """If gross exposure exceeds max_gross, scale down proportionally."""
        gross = sum(abs(w) for w in weights.values())
        if gross > self.max_gross:
            scale = self.max_gross / gross
            weights = {s: w * scale for s, w in weights.items()}
        return weights

    def _apply_net_cap(self, weights):
        """If abs(net exposure) exceeds max_net, scale down proportionally."""
        net = sum(weights.values())
        if abs(net) > self.max_net:
            # Scale all weights proportionally to bring net within cap
            # This is a simple approach; more sophisticated would shift longs/shorts
            scale = self.max_net / abs(net)
            weights = {s: w * scale for s, w in weights.items()}
        return weights

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
