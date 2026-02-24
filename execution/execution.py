"""Execution organism - signal-strength execution model.

Uses pricing and cancellation molecules with LEAN framework integration.
"""
from AlgorithmImports import *
from core.math_utils import compute_limit_price
from core.formatting import build_order_tag, extract_week_id_from_tag


class SignalStrengthExecutionModel(ExecutionModel):
    """
    Custom execution model that selects order type based on signal strength:
    - Strong signals (>= strong_threshold): Limit orders at market price
    - Moderate signals (>= moderate_threshold): Limit orders at moderate_offset_pct
    - Weak signals (< moderate_threshold): Limit orders at weak_offset_pct
    - Exits: Always market orders

    Unfilled limit orders are cancelled via week_id cycle logic inside
    portfolio construction (after current_week_id is refreshed on rebalance days).
    Legacy 2-check fallback applies when week_id tracking is unavailable.
    """

    def __init__(self,
                 strong_threshold=0.70,
                 moderate_threshold=0.30,
                 strong_offset_pct=0.0,
                 moderate_offset_pct=0.005,
                 weak_offset_pct=0.015,
                 default_signal_strength=0.50,
                 limit_cancel_after_open_checks=2,
                 portfolio_model=None):
        self.strong_threshold = strong_threshold
        self.moderate_threshold = moderate_threshold
        self.strong_offset_pct = strong_offset_pct
        self.moderate_offset_pct = moderate_offset_pct
        self.weak_offset_pct = weak_offset_pct
        self.default_signal_strength = default_signal_strength
        self.limit_cancel_after_open_checks = max(1, int(limit_cancel_after_open_checks))
        self.portfolio_model = portfolio_model

        self.open_limit_tickets = []
        self.limit_open_checks = {}
        self.market_price_at_submit = {}
        self.order_week_ids = {}

    def Execute(self, algorithm, targets):
        if not targets:
            return

        # Process only the targets emitted in this pipeline call.
        # Keeping stale targets across days can keep generating orders even when
        # the PCM intentionally stops emitting for steady-state symbols.
        target_collection = PortfolioTargetCollection()
        target_collection.AddRange(targets)
        if target_collection.IsEmpty:
            return

        for target in target_collection.OrderByMarginImpact(algorithm):
            symbol = target.Symbol
            security = algorithm.Securities[symbol]

            unordered_quantity = OrderSizing.GetUnorderedQuantity(algorithm, target, security)
            if unordered_quantity == 0:
                continue

            price = security.Price
            if price <= 0:
                continue

            holding = algorithm.Portfolio[symbol]
            is_exit = (holding.Invested and
                       abs(holding.Quantity + unordered_quantity) < abs(holding.Quantity) * 0.01)

            signal_strength = self._get_signal_strength(algorithm, symbol)

            tick_size = security.SymbolProperties.MinimumPriceVariation
            pcm = self._get_portfolio_model(algorithm)
            week_id_val = getattr(pcm, 'current_week_id', None) if pcm is not None else None
            if not week_id_val:
                # Keep week-aware tags populated even if external wiring is unavailable.
                week_id_val = algorithm.Time.strftime('%Y-%m-%d')
                if pcm is not None:
                    pcm.current_week_id = week_id_val

            if pcm is not None:
                symbol_state = getattr(pcm, 'symbol_scale_state', {}).get(symbol, {})
                scale_day_val = symbol_state.get("scale_day", 0)
            else:
                scale_day_val = 0

            if is_exit:
                tier = "exit"
                tag = build_order_tag(tier, signal_strength, week_id_val, scale_day_val)
                ticket = algorithm.MarketOrder(symbol, unordered_quantity, tag=tag)
                if ticket is not None:
                    self.market_price_at_submit[ticket.OrderId] = price
            elif signal_strength >= self.strong_threshold:
                tier = "strong"
                limit_price = compute_limit_price(price, unordered_quantity, self.strong_offset_pct, tick_size)
                tag = build_order_tag(tier, signal_strength, week_id_val, scale_day_val)
                ticket = algorithm.LimitOrder(symbol, unordered_quantity, limit_price, tag=tag)
                if ticket is not None:
                    self.open_limit_tickets.append(ticket)
                    self.limit_open_checks[ticket.OrderId] = 0
                    self.market_price_at_submit[ticket.OrderId] = price
                    wid = extract_week_id_from_tag(tag)
                    if wid:
                        self.order_week_ids[ticket.OrderId] = wid
            elif signal_strength >= self.moderate_threshold:
                tier = "moderate"
                limit_price = compute_limit_price(price, unordered_quantity, self.moderate_offset_pct, tick_size)
                tag = build_order_tag(tier, signal_strength, week_id_val, scale_day_val)
                ticket = algorithm.LimitOrder(symbol, unordered_quantity, limit_price, tag=tag)
                if ticket is not None:
                    self.open_limit_tickets.append(ticket)
                    self.limit_open_checks[ticket.OrderId] = 0
                    self.market_price_at_submit[ticket.OrderId] = price
                    wid = extract_week_id_from_tag(tag)
                    if wid:
                        self.order_week_ids[ticket.OrderId] = wid
            else:
                tier = "weak"
                limit_price = compute_limit_price(price, unordered_quantity, self.weak_offset_pct, tick_size)
                tag = build_order_tag(tier, signal_strength, week_id_val, scale_day_val)
                ticket = algorithm.LimitOrder(symbol, unordered_quantity, limit_price, tag=tag)
                if ticket is not None:
                    self.open_limit_tickets.append(ticket)
                    self.limit_open_checks[ticket.OrderId] = 0
                    self.market_price_at_submit[ticket.OrderId] = price
                    wid = extract_week_id_from_tag(tag)
                    if wid:
                        self.order_week_ids[ticket.OrderId] = wid

    def cancel_stale_orders(self, algorithm):
        """Cancel limit orders from PREVIOUS rebalance cycles only."""
        pcm = self._get_portfolio_model(algorithm)
        current_week_id = getattr(pcm, 'current_week_id', None) if pcm is not None else None

        if not current_week_id:
            algorithm.Debug("  [Signal-Aware] Warning: current_week_id not set, using legacy 2-check cancellation")
            self._cancel_stale_orders_legacy(algorithm)
            return

        orders_to_cancel = []
        for ticket in self.open_limit_tickets:
            if ticket.Status in (OrderStatus.Submitted, OrderStatus.PartiallyFilled):
                order_week_id = self.order_week_ids.get(ticket.OrderId)

                if not order_week_id:
                    algorithm.Debug(f"  [Signal-Aware] Warning: Order {ticket.OrderId} has no week_id; applying legacy check")
                    checks = self.limit_open_checks.get(ticket.OrderId, 0) + 1
                    self.limit_open_checks[ticket.OrderId] = checks
                    if checks >= self.limit_cancel_after_open_checks:
                        algorithm.Debug(
                            f"  [LEGACY] Cancelling stale order {ticket.OrderId} ({ticket.Symbol.Value}) after {checks} checks"
                        )
                        orders_to_cancel.append(ticket)
                    continue

                if order_week_id < current_week_id:
                    algorithm.Debug(
                        f"  [Signal-Aware] Cancelling order {ticket.OrderId} ({ticket.Symbol.Value}) "
                        f"from week {order_week_id} (current: {current_week_id})"
                    )
                    orders_to_cancel.append(ticket)

        for ticket in orders_to_cancel:
            ticket.Cancel()
            if ticket.OrderId in self.limit_open_checks:
                del self.limit_open_checks[ticket.OrderId]
            if ticket.OrderId in self.market_price_at_submit:
                del self.market_price_at_submit[ticket.OrderId]
            if ticket.OrderId in self.order_week_ids:
                del self.order_week_ids[ticket.OrderId]
            self.open_limit_tickets.remove(ticket)

    def _cancel_stale_orders_legacy(self, algorithm):
        """Legacy 2-check cancellation logic (fallback only)."""
        still_open = []
        for ticket in self.open_limit_tickets:
            if ticket.Status in (OrderStatus.Submitted, OrderStatus.PartiallyFilled):
                checks = self.limit_open_checks.get(ticket.OrderId, 0) + 1
                self.limit_open_checks[ticket.OrderId] = checks

                if checks >= self.limit_cancel_after_open_checks:
                    algorithm.Debug(
                        f"  [LEGACY] Cancelling stale limit: {ticket.Symbol.Value} "
                        f"qty={ticket.Quantity} open_checks={checks}")
                    ticket.Cancel()
                    if ticket.OrderId in self.limit_open_checks:
                        del self.limit_open_checks[ticket.OrderId]
                    if ticket.OrderId in self.market_price_at_submit:
                        del self.market_price_at_submit[ticket.OrderId]
                    if ticket.OrderId in self.order_week_ids:
                        del self.order_week_ids[ticket.OrderId]

            if ticket.Status not in (OrderStatus.Filled, OrderStatus.Canceled, OrderStatus.Invalid):
                still_open.append(ticket)
            else:
                self.limit_open_checks.pop(ticket.OrderId, None)

        self.open_limit_tickets = still_open

    def OnOrderEvent(self, algorithm, order_event):
        if order_event.Status in (OrderStatus.Filled, OrderStatus.Canceled, OrderStatus.Invalid):
            self.open_limit_tickets = [
                t for t in self.open_limit_tickets
                if t.OrderId != order_event.OrderId
            ]
            self.limit_open_checks.pop(order_event.OrderId, None)
            self.order_week_ids.pop(order_event.OrderId, None)

    def OnSecuritiesChanged(self, algorithm, changes):
        for removed in changes.RemovedSecurities:
            symbol = removed.Symbol
            removed_order_ids = []
            for ticket in self.open_limit_tickets:
                if ticket.Symbol != symbol:
                    continue
                removed_order_ids.append(ticket.OrderId)
                if ticket.Status in (OrderStatus.Submitted, OrderStatus.PartiallyFilled):
                    ticket.Cancel()
            self.open_limit_tickets = [
                t for t in self.open_limit_tickets if t.Symbol != symbol
            ]
            for order_id in removed_order_ids:
                self.limit_open_checks.pop(order_id, None)
                self.order_week_ids.pop(order_id, None)

    def _get_signal_strength(self, algorithm, symbol):
        pcm = self._get_portfolio_model(algorithm)
        if pcm is None:
            return self.default_signal_strength
        strengths = getattr(pcm, 'signal_strengths', {})
        return strengths.get(symbol, self.default_signal_strength)

    def _get_portfolio_model(self, algorithm):
        if self.portfolio_model is not None:
            return self.portfolio_model
        return getattr(algorithm, 'pcm', None)
