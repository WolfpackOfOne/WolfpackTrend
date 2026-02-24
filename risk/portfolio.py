"""Portfolio organism - target vol portfolio construction model.

Uses molecules from risk domain and core utilities.
"""
import math
from AlgorithmImports import *
from core.math_utils import (
    build_scaling_schedule,
    estimate_portfolio_vol,
    apply_per_name_cap,
    apply_gross_cap,
    apply_net_cap,
)


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
                 rebalance_interval_trading_days=None, algorithm=None,
                 rebalance_dead_band=0.015):
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

        # Dead-band for HOLD classification (fraction of NAV)
        self.rebalance_dead_band = rebalance_dead_band

        # Scaling state
        self.weekly_targets = {}       # symbol -> final target weight from last rebalance
        self.signal_strengths = {}     # symbol -> abs(magnitude) from last rebalance
        self.symbol_scale_state = {}   # {Symbol: {"scale_day": int, "is_scaling": bool}}
        self.trading_days_since_rebalance = None
        # Optional external override (set by alpha); counter-based logic is primary.
        self.is_rebalance_day = False
        self.current_week_id = None        # Rebalance date (YYYY-MM-DD)
        self.week_plan = {}                # symbol -> {start_w, weekly_target_w}
        self.last_cancel_check_date = None  # date of last stale-order cancellation pass
        self.previous_weekly_targets = {}  # {Symbol: float} from last rebalance
        self.last_classifications = {}     # {Symbol: str} most recent rebalance classifications

        # Build dynamic scaling schedules
        self.strong_schedule = build_scaling_schedule(self.scaling_days, front_load_factor=2.0)
        self.moderate_schedule = build_scaling_schedule(self.scaling_days, front_load_factor=1.3)
        self.weak_schedule = build_scaling_schedule(self.scaling_days, front_load_factor=1.0)

    def _get_scaling_schedule(self, signal_strength):
        if signal_strength >= 0.7:
            return self.strong_schedule
        elif signal_strength >= 0.3:
            return self.moderate_schedule
        else:
            return self.weak_schedule

    def UpdateReturns(self, algorithm, data):
        """Update rolling returns incrementally from daily bars."""
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

        active_insights = [i for i in insights if i.IsActive(algorithm.UtcTime)]
        if not active_insights:
            return targets

        counter_rebalance = (
            self.trading_days_since_rebalance is None or
            self.trading_days_since_rebalance >= self.rebalance_interval_trading_days
        )
        is_rebalance_today = bool(self.is_rebalance_day) or counter_rebalance
        self.is_rebalance_day = False

        # Track FLIP symbols so the daily emission loop can skip them on rebalance day
        flip_symbols = set()

        if is_rebalance_today:
            # 1. Snapshot actual holdings BEFORE recomputing targets
            actual_weights = self._get_actual_weights(algorithm)

            # 2. Recompute weekly targets from fresh insights
            self.trading_days_since_rebalance = 1
            self._compute_weekly_targets(algorithm, active_insights)
            self._initialize_week_plan(algorithm)

            # 3. Classify symbols
            classifications = self._classify_symbols(
                self.weekly_targets, self.previous_weekly_targets,
                actual_weights, self.rebalance_dead_band
            )
            self.last_classifications = classifications

            # 4. Update per-symbol scale state based on classification
            for symbol, action in classifications.items():
                if action == "NEW_ENTRY":
                    self.symbol_scale_state[symbol] = {"scale_day": 0, "is_scaling": True}
                elif action == "FLIP":
                    # scale_day=0: on rebalance day, FLIP is in flip_symbols so emission
                    # is skipped. Next non-rebalance day advances 0→1 before emission,
                    # so first scale-in fraction is schedule[1] (correct).
                    self.symbol_scale_state[symbol] = {"scale_day": 0, "is_scaling": True}
                elif action == "RESIZE":
                    self.symbol_scale_state[symbol] = {"scale_day": 0, "is_scaling": False}
                elif action == "HOLD":
                    # Force steady state — position is within dead-band of target.
                    # Prior is_scaling=True must not leak through or the emission
                    # loop will emit a target that creates a micro-order from NAV drift.
                    self.symbol_scale_state[symbol] = {"scale_day": 0, "is_scaling": False}
                elif action == "EXIT":
                    self.symbol_scale_state.pop(symbol, None)

            # 5. Emit EXIT/FLIP targets (before updating previous_weekly_targets)
            for symbol, action in classifications.items():
                if action == "EXIT":
                    targets.append(PortfolioTarget.Percent(algorithm, symbol, 0))
                    if symbol in algorithm.Securities:
                        self.expected_prices[symbol] = algorithm.Securities[symbol].Price
                elif action == "FLIP":
                    # Only the 0% exit. No entry target today.
                    targets.append(PortfolioTarget.Percent(algorithm, symbol, 0))
                    flip_symbols.add(symbol)
                    if symbol in algorithm.Securities:
                        self.expected_prices[symbol] = algorithm.Securities[symbol].Price

            # 6. NOW safe to update previous_weekly_targets
            self.previous_weekly_targets = dict(self.weekly_targets)

        else:
            # Non-rebalance day: advance scale state BEFORE emission
            self.trading_days_since_rebalance += 1
            for symbol, state in self.symbol_scale_state.items():
                if state["is_scaling"]:
                    if state["scale_day"] < self.scaling_days - 1:
                        state["scale_day"] += 1
                    else:
                        state["is_scaling"] = False  # Scale-in complete

        # Run stale-order cancellation once per day inside pipeline.
        today = algorithm.Time.date()
        if self.last_cancel_check_date != today:
            execution_model = getattr(algorithm, "execution_model", None)
            if execution_model is not None:
                execution_model.cancel_stale_orders(algorithm)
            self.last_cancel_check_date = today

        # Emit targets only for symbols that need action.
        # HOLD symbols are NOT emitted -- PortfolioTarget.Percent converts % to shares
        # based on current NAV/price, so even tiny price moves create non-zero deltas
        # in GetUnorderedQuantity, generating unnecessary orders every day.
        # On rebalance day: emit for NEW_ENTRY (scaled) and RESIZE (full weight).
        #   EXIT/FLIP 0% targets were already emitted in step 5.
        # On non-rebalance days: emit only for symbols still scaling in.
        for symbol, final_weight in self.weekly_targets.items():
            # Skip FLIP symbols on rebalance day -- they already got a 0% exit target.
            if is_rebalance_today and symbol in flip_symbols:
                continue

            state = self.symbol_scale_state.get(symbol, {"scale_day": 0, "is_scaling": False})

            if state["is_scaling"]:
                # Actively scaling in -- emit scaled target
                sig_str = self.signal_strengths.get(symbol, 0.5)
                schedule = self._get_scaling_schedule(sig_str)
                day_idx = min(state["scale_day"], len(schedule) - 1)
                today_weight = final_weight * schedule[day_idx]
                targets.append(PortfolioTarget.Percent(algorithm, symbol, today_weight))
            elif is_rebalance_today:
                # Rebalance day: emit for RESIZE (immediate adjustment to new weight).
                # HOLD symbols are skipped -- their position is already close enough.
                classification = classifications.get(symbol, "")
                if classification == "RESIZE":
                    targets.append(PortfolioTarget.Percent(algorithm, symbol, final_weight))

        # Store expected prices for slippage tracking
        for symbol in self.weekly_targets.keys():
            if symbol in algorithm.Securities:
                self.expected_prices[symbol] = algorithm.Securities[symbol].Price

        # Log portfolio construction summary
        if self.algorithm:
            vol_annual = self._estimate_portfolio_vol(
                {s: w * self._get_current_fraction(s) for s, w in self.weekly_targets.items()})
            eff_weights = {s: self.weekly_targets[s] * self._get_current_fraction(s)
                          for s in self.weekly_targets}
            gross = sum(abs(w) for w in eff_weights.values())
            net = sum(eff_weights.values())
            long_exp = sum(w for w in eff_weights.values() if w > 0)
            short_exp = sum(abs(w) for w in eff_weights.values() if w < 0)
            vol_str = f"{vol_annual*100:.1f}%" if vol_annual else "N/A"

            scaling_count = sum(1 for s in self.symbol_scale_state.values() if s["is_scaling"])
            if scaling_count > 0:
                max_day = max(s["scale_day"] for s in self.symbol_scale_state.values() if s["is_scaling"])
                scale_str = f"Scaling {scaling_count} symbols (max day {max_day}/{self.scaling_days})"
            else:
                scale_str = "Steady state (no symbols scaling)"

            self.algorithm.Debug(
                f"[{algorithm.Time.strftime('%Y-%m-%d')}] PCM: "
                f"{scale_str}, "
                f"Vol={vol_str}, Gross={gross*100:.0f}%, Net={net*100:+.0f}%, "
                f"L/S={long_exp*100:.0f}%/{short_exp*100:.0f}%"
            )

        return targets

    def _get_current_fraction(self, symbol):
        """Get the current scaling fraction for a symbol."""
        state = self.symbol_scale_state.get(symbol, {"scale_day": 0, "is_scaling": False})
        if not state["is_scaling"]:
            return 1.0  # Fully scaled -- steady state
        sig_str = self.signal_strengths.get(symbol, 0.5)
        schedule = self._get_scaling_schedule(sig_str)
        day_idx = min(state["scale_day"], len(schedule) - 1)
        return schedule[day_idx]

    def _get_actual_weights(self, algorithm):
        """Snapshot current portfolio weights from actual holdings."""
        nav = float(algorithm.Portfolio.TotalPortfolioValue)
        if nav <= 0:
            return {}
        actual = {}
        for symbol in self.symbols:
            holding = algorithm.Portfolio[symbol]
            if holding.Invested:
                actual[symbol] = float(holding.Quantity * holding.Price) / nav
        return actual

    def _classify_symbols(self, new_targets, old_targets, actual_weights, dead_band):
        """
        Classify each symbol's rebalance action.

        Uses old_targets for direction/intent comparison.
        Uses actual_weights for dead-band check (handles partial fills).

        Returns: {Symbol: "HOLD" | "RESIZE" | "FLIP" | "NEW_ENTRY" | "EXIT"}
        """
        classifications = {}
        all_symbols = set(new_targets.keys()) | set(old_targets.keys()) | set(actual_weights.keys())

        for symbol in all_symbols:
            new_w = new_targets.get(symbol, 0.0)
            old_w = old_targets.get(symbol, 0.0)
            actual_w = actual_weights.get(symbol, 0.0)

            has_new_target = symbol in new_targets
            was_targeted = symbol in old_targets
            is_held = abs(actual_w) > 1e-8

            if has_new_target and not was_targeted and not is_held:
                classifications[symbol] = "NEW_ENTRY"
            elif has_new_target and not was_targeted and is_held:
                if (actual_w > 0) != (new_w > 0):
                    classifications[symbol] = "FLIP"
                else:
                    classifications[symbol] = "RESIZE"
            elif not has_new_target and (was_targeted or is_held):
                classifications[symbol] = "EXIT"
            elif not has_new_target and not was_targeted and not is_held:
                continue
            elif (new_w > 0) != (old_w > 0):
                classifications[symbol] = "FLIP"
            elif abs(new_w - actual_w) <= dead_band:
                classifications[symbol] = "HOLD"
            else:
                classifications[symbol] = "RESIZE"

        return classifications

    def _compute_weekly_targets(self, algorithm, active_insights):
        latest_by_symbol = {}
        latest_time_by_symbol = {}
        for insight in active_insights:
            symbol = insight.Symbol
            generated = getattr(insight, "GeneratedTimeUtc", None)
            previous = latest_time_by_symbol.get(symbol, None)
            if previous is None or generated is None or generated >= previous:
                latest_by_symbol[symbol] = insight
                latest_time_by_symbol[symbol] = generated

        raw_weights = {}
        for symbol, insight in latest_by_symbol.items():
            self._track_symbol(symbol)
            sign = 1.0 if insight.Direction == InsightDirection.Up else -1.0
            weight = insight.Weight if insight.Weight else 0.0
            raw_weights[symbol] = sign * weight

        total_abs = sum(abs(w) for w in raw_weights.values())
        if total_abs < 1e-8:
            self.weekly_targets = {}
            self.signal_strengths = {}
            return

        weights = {s: w / total_abs for s, w in raw_weights.items()}

        vol_annual = self._estimate_portfolio_vol(weights)

        if vol_annual is not None and vol_annual > 1e-8:
            scale = self.target_vol_annual / vol_annual
            weights = {s: w * scale for s, w in weights.items()}

        # Apply constraints in order: per-name cap -> gross cap -> net cap
        weights = apply_per_name_cap(weights, self.max_weight)
        weights = apply_gross_cap(weights, self.max_gross)
        weights = apply_net_cap(weights, self.max_net)

        self.weekly_targets = weights
        self.signal_strengths = {
            insight.Symbol: (insight.Weight if insight.Weight else 0.0)
            for insight in latest_by_symbol.values()
        }

    def _initialize_week_plan(self, algorithm):
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
        if not self.week_plan:
            return []

        nav = float(algorithm.Portfolio.TotalPortfolioValue)
        rows = []
        for symbol in sorted(self.week_plan.keys(), key=lambda s: str(s.Value)):
            plan = self.week_plan[symbol]
            weekly_target_w = float(plan['weekly_target_w'])
            start_w = float(plan['start_w'])

            # Per-symbol scale state
            state = self.symbol_scale_state.get(symbol, {"scale_day": 0, "is_scaling": False})
            symbol_scale_day = state["scale_day"]
            symbol_is_scaling = state["is_scaling"]

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

            classification = self.last_classifications.get(symbol, "")

            rows.append({
                'week_id': self.current_week_id or '',
                'symbol': str(symbol.Value),
                'start_w': round(start_w, 8),
                'weekly_target_w': round(weekly_target_w, 8),
                'scheduled_fraction': round(scheduled_fraction, 8),
                'scheduled_w': round(scheduled_w, 8),
                'actual_w': round(actual_w, 8),
                'scale_day': int(symbol_scale_day),
                'is_scaling': symbol_is_scaling,
                'classification': classification,
            })

        return rows

    def _estimate_portfolio_vol(self, weights):
        """Convert RollingWindow objects to plain lists for core utility."""
        rolling_returns_lists = {}
        for symbol in weights.keys():
            if symbol not in self.rolling_returns:
                continue
            window = self.rolling_returns[symbol]
            if window.Count < self.min_obs:
                continue
            rolling_returns_lists[symbol] = [window[i] for i in range(window.Count)]

        return estimate_portfolio_vol(weights, rolling_returns_lists, self.min_obs)

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
            if symbol in self.weekly_targets:
                del self.weekly_targets[symbol]
            if symbol in self.signal_strengths:
                del self.signal_strengths[symbol]
            if symbol in self.week_plan:
                del self.week_plan[symbol]
            self.symbol_scale_state.pop(symbol, None)
            self.previous_weekly_targets.pop(symbol, None)
            self.last_classifications.pop(symbol, None)
