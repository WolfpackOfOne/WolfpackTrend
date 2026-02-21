import math
from AlgorithmImports import *


class TargetVolPortfolioConstructionModel(PortfolioConstructionModel):
    """
    Portfolio construction model that:
    - Converts insights to signed weights
    - Scales portfolio to target annualized volatility (diagonal approximation)
    - Enforces max gross exposure, max net exposure, and per-name caps
    - Scales into positions over scaling_days trading days with signal-dependent pace
    """

    def __init__(self, target_vol_annual=0.10, max_gross=1.50, max_net=0.50,
                 max_weight=0.10, vol_lookback=63, scaling_days=5,
                 rebalance_interval_trading_days=None, algorithm=None):
        self.target_vol_annual = target_vol_annual
        self.max_gross = max_gross
        self.max_net = max_net
        self.max_weight = max_weight
        self.vol_lookback = vol_lookback
        self.scaling_days = max(1, int(scaling_days))
        if rebalance_interval_trading_days is None:
            rebalance_interval_trading_days = self.scaling_days
        self.rebalance_interval_trading_days = max(1, int(rebalance_interval_trading_days))

        # Minimum observations required for vol estimation
        self.min_obs = 20

        # Rolling returns per symbol
        self.rolling_returns = {}  # symbol -> RollingWindow[float]
        self.prev_close = {}  # symbol -> float

        # Track symbols we're managing
        self.symbols = set()

        # Expected prices at target generation (for slippage tracking)
        self.expected_prices = {}

        # Algorithm reference for Debug logging
        self.algorithm = algorithm

        # Scaling state
        self.weekly_targets = {}       # symbol -> final target weight from last rebalance
        self.signal_strengths = {}     # symbol -> abs(magnitude) from last rebalance
        self.current_scale_day = 0         # Which day of the scaling period (0-indexed)
        self.trading_days_since_rebalance = None
        # Optional external override (set by alpha); counter-based logic is primary.
        self.is_rebalance_day = False
        self.current_week_id = None        # Rebalance date (YYYY-MM-DD)
        self.week_plan = {}                # symbol -> {start_w, weekly_target_w}
        self.last_cancel_check_date = None  # date of last stale-order cancellation pass

        # Build dynamic scaling schedules
        self.strong_schedule = self._build_schedule(front_load_factor=2.0)
        self.moderate_schedule = self._build_schedule(front_load_factor=1.3)
        self.weak_schedule = self._build_schedule(front_load_factor=1.0)

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

        exponent = 1.0 / front_load_factor
        schedule = []
        for i in range(1, n + 1):
            fraction = (i / n) ** exponent
            schedule.append(round(fraction, 4))
        schedule[-1] = 1.0
        return schedule

    def _get_scaling_schedule(self, signal_strength):
        if signal_strength >= 0.7:
            return self.strong_schedule
        elif signal_strength >= 0.3:
            return self.moderate_schedule
        else:
            return self.weak_schedule

    def UpdateReturns(self, algorithm, data):
        """
        Update rolling returns incrementally from daily bars.
        Call this once per day from OnData.
        """
        self._ensure_symbols_from_data(data)

        for symbol in list(self.symbols):
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

        counter_rebalance = (
            self.trading_days_since_rebalance is None or
            self.trading_days_since_rebalance >= self.rebalance_interval_trading_days
        )
        is_rebalance_today = bool(self.is_rebalance_day) or counter_rebalance
        # External flag is one-shot when present.
        self.is_rebalance_day = False

        if is_rebalance_today:
            # Full rebalance: compute new weekly targets
            self.current_scale_day = 0
            self.trading_days_since_rebalance = 0
            self._compute_weekly_targets(algorithm, active_insights)
            self._initialize_week_plan(algorithm)
        else:
            # Scaling day: increment scale day
            self.trading_days_since_rebalance += 1
            self.current_scale_day = min(
                self.current_scale_day + 1,
                self.scaling_days - 1
            )

        # Run stale-order cancellation once per day inside pipeline.
        # On rebalance days, this executes after current_week_id is refreshed.
        today = algorithm.Time.date()
        if self.last_cancel_check_date != today:
            execution_model = getattr(algorithm, "execution_model", None)
            if execution_model is not None:
                execution_model.cancel_stale_orders(algorithm)
            self.last_cancel_check_date = today

        # Emit scaled targets for each symbol
        for symbol, final_weight in self.weekly_targets.items():
            sig_str = self.signal_strengths.get(symbol, 0.5)
            schedule = self._get_scaling_schedule(sig_str)
            day_idx = min(self.current_scale_day, len(schedule) - 1)
            cumulative_fraction = schedule[day_idx]

            today_weight = final_weight * cumulative_fraction
            targets.append(PortfolioTarget.Percent(algorithm, symbol, today_weight))

        # Zero out positions not in current targets
        exits = []
        for symbol in self.symbols:
            if symbol not in self.weekly_targets:
                targets.append(PortfolioTarget.Percent(algorithm, symbol, 0))
                exits.append(symbol)
                if symbol in algorithm.Securities:
                    self.expected_prices[symbol] = algorithm.Securities[symbol].Price

        # Store expected prices for slippage tracking
        for symbol in self.weekly_targets.keys():
            if symbol in algorithm.Securities:
                self.expected_prices[symbol] = algorithm.Securities[symbol].Price

        # Log portfolio construction summary
        if self.algorithm:
            # Compute effective weights for logging
            vol_annual = self._estimate_portfolio_vol(
                {s: w * self._get_current_fraction(s) for s, w in self.weekly_targets.items()})
            eff_weights = {s: self.weekly_targets[s] * self._get_current_fraction(s)
                          for s in self.weekly_targets}
            gross = sum(abs(w) for w in eff_weights.values())
            net = sum(eff_weights.values())
            long_exp = sum(w for w in eff_weights.values() if w > 0)
            short_exp = sum(abs(w) for w in eff_weights.values() if w < 0)
            vol_str = f"{vol_annual*100:.1f}%" if vol_annual else "N/A"
            self.algorithm.Debug(
                f"[{algorithm.Time.strftime('%Y-%m-%d')}] PCM: "
                f"Scale day {self.current_scale_day}/{self.scaling_days}, "
                f"Vol={vol_str}, Gross={gross*100:.0f}%, Net={net*100:+.0f}%, "
                f"L/S={long_exp*100:.0f}%/{short_exp*100:.0f}%"
            )

        return targets

    def _get_current_fraction(self, symbol):
        """Get the cumulative scaling fraction for a symbol at current_scale_day."""
        sig_str = self.signal_strengths.get(symbol, 0.5)
        schedule = self._get_scaling_schedule(sig_str)
        day_idx = min(self.current_scale_day, len(schedule) - 1)
        return schedule[day_idx]

    def _compute_weekly_targets(self, algorithm, active_insights):
        """Compute full weekly target weights from insights."""
        # Keep only the most recent active insight per symbol.
        latest_by_symbol = {}
        latest_time_by_symbol = {}
        for insight in active_insights:
            symbol = insight.Symbol
            generated = getattr(insight, "GeneratedTimeUtc", None)
            previous = latest_time_by_symbol.get(symbol, None)
            if previous is None or generated is None or generated >= previous:
                latest_by_symbol[symbol] = insight
                latest_time_by_symbol[symbol] = generated

        # Convert insights to signed raw weights
        raw_weights = {}
        for symbol, insight in latest_by_symbol.items():
            self._track_symbol(symbol)
            sign = 1.0 if insight.Direction == InsightDirection.Up else -1.0
            weight = insight.Weight if insight.Weight else 0.0
            raw_weights[symbol] = sign * weight

        # Normalize to unit gross
        total_abs = sum(abs(w) for w in raw_weights.values())
        if total_abs < 1e-8:
            self.weekly_targets = {}
            self.signal_strengths = {}
            return

        weights = {s: w / total_abs for s, w in raw_weights.items()}

        # Estimate portfolio volatility (diagonal approximation)
        vol_annual = self._estimate_portfolio_vol(weights)

        # Scale to target vol
        if vol_annual is not None and vol_annual > 1e-8:
            scale = self.target_vol_annual / vol_annual
            weights = {s: w * scale for s, w in weights.items()}

        # Apply constraints in order: per-name cap -> gross cap -> net cap
        weights = self._apply_per_name_cap(weights)
        weights = self._apply_gross_cap(weights)
        weights = self._apply_net_cap(weights)

        self.weekly_targets = weights
        self.signal_strengths = {
            insight.Symbol: (insight.Weight if insight.Weight else 0.0)
            for insight in latest_by_symbol.values()
        }

    def _initialize_week_plan(self, algorithm):
        """
        Initialize per-symbol weekly order plan on rebalance day.
        """
        nav = float(algorithm.Portfolio.TotalPortfolioValue)
        invested_symbols = set()
        for symbol, holding in algorithm.Portfolio.items():
            if holding.Invested:
                invested_symbols.add(symbol)

        plan_symbols = set(self.weekly_targets.keys()) | invested_symbols
        self.current_week_id = algorithm.Time.strftime('%Y-%m-%d')
        self.week_plan = {}

        for symbol in plan_symbols:
            start_w = 0.0
            if nav > 0 and symbol in algorithm.Portfolio:
                holding = algorithm.Portfolio[symbol]
                start_w = float(holding.Quantity * holding.Price) / nav

            self.week_plan[symbol] = {
                'start_w': start_w,
                'weekly_target_w': float(self.weekly_targets.get(symbol, 0.0))
            }

    def get_daily_target_state(self, algorithm):
        """
        Return per-symbol target state for current day.
        """
        if not self.week_plan:
            return []

        nav = float(algorithm.Portfolio.TotalPortfolioValue)
        rows = []
        for symbol in sorted(self.week_plan.keys(), key=lambda s: str(s.Value)):
            plan = self.week_plan[symbol]
            weekly_target_w = float(plan['weekly_target_w'])
            start_w = float(plan['start_w'])

            if symbol in self.weekly_targets:
                scheduled_fraction = float(self._get_current_fraction(symbol))
                scheduled_w = weekly_target_w * scheduled_fraction
            else:
                scheduled_fraction = 1.0
                scheduled_w = weekly_target_w

            actual_w = 0.0
            if nav > 0 and symbol in algorithm.Portfolio:
                holding = algorithm.Portfolio[symbol]
                actual_w = float(holding.Quantity * holding.Price) / nav

            rows.append({
                'week_id': self.current_week_id or '',
                'symbol': str(symbol.Value),
                'start_w': round(start_w, 8),
                'weekly_target_w': round(weekly_target_w, 8),
                'scheduled_fraction': round(scheduled_fraction, 8),
                'scheduled_w': round(scheduled_w, 8),
                'actual_w': round(actual_w, 8),
                'scale_day': int(self.current_scale_day)
            })

        return rows

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
            scale = self.max_net / abs(net)
            weights = {s: w * scale for s, w in weights.items()}
        return weights

    def _ensure_symbols_from_data(self, data):
        if not hasattr(data, "Bars"):
            return

        for symbol in data.Bars.Keys:
            self._track_symbol(symbol)

    def _track_symbol(self, symbol):
        self.symbols.add(symbol)
        if symbol not in self.rolling_returns:
            self.rolling_returns[symbol] = RollingWindow[float](self.vol_lookback)

    def OnSecuritiesChanged(self, algorithm, changes):
        for security in changes.AddedSecurities:
            self._track_symbol(security.Symbol)

        for security in changes.RemovedSecurities:
            symbol = security.Symbol
            self.symbols.discard(symbol)
            if symbol in self.rolling_returns:
                del self.rolling_returns[symbol]
            if symbol in self.prev_close:
                del self.prev_close[symbol]
            # Clean up scaling state for removed symbols
            if symbol in self.weekly_targets:
                del self.weekly_targets[symbol]
            if symbol in self.signal_strengths:
                del self.signal_strengths[symbol]
            if symbol in self.week_plan:
                del self.week_plan[symbol]
