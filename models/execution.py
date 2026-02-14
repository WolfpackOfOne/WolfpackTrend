from AlgorithmImports import *


class SignalStrengthExecutionModel(ExecutionModel):
    """
    Custom execution model that selects order type based on signal strength:
    - Strong signals (>= strong_threshold): Market orders
    - Moderate signals (>= moderate_threshold): Limit orders at moderate_offset_pct
    - Weak signals (< moderate_threshold): Limit orders at weak_offset_pct
    - Exits: Always market orders

    Unfilled limit orders are cancelled via a scheduled event at market open
    (called from main.py), before the pipeline runs.
    """

    def __init__(self,
                 strong_threshold=0.70,
                 moderate_threshold=0.30,
                 strong_offset_pct=0.0,
                 moderate_offset_pct=0.005,
                 weak_offset_pct=0.015,
                 default_signal_strength=0.50,
                 limit_cancel_after_open_checks=2):
        self.strong_threshold = strong_threshold
        self.moderate_threshold = moderate_threshold
        self.strong_offset_pct = strong_offset_pct
        self.moderate_offset_pct = moderate_offset_pct
        self.weak_offset_pct = weak_offset_pct
        self.default_signal_strength = default_signal_strength
        # Number of market-open checks before an unfilled limit order is cancelled.
        # With daily bars, 2 checks gives orders at least one full session to fill.
        self.limit_cancel_after_open_checks = max(1, int(limit_cancel_after_open_checks))

        self.targets_collection = PortfolioTargetCollection()
        self.open_limit_tickets = []
        self.limit_open_checks = {}  # order_id -> number of open checks observed
        self.market_price_at_submit = {}  # order_id -> market price when order was submitted
        self.order_week_ids = {}  # order_id -> week_id (rebalance cycle identifier)

    def Execute(self, algorithm, targets):
        self.targets_collection.AddRange(targets)

        if self.targets_collection.IsEmpty:
            return

        for target in self.targets_collection.OrderByMarginImpact(algorithm):
            symbol = target.Symbol
            security = algorithm.Securities[symbol]

            unordered_quantity = OrderSizing.GetUnorderedQuantity(algorithm, target, security)
            if unordered_quantity == 0:
                continue

            price = security.Price
            if price <= 0:
                continue

            # Exits always use market orders
            holding = algorithm.Portfolio[symbol]
            is_exit = (holding.Invested and
                       abs(holding.Quantity + unordered_quantity) < abs(holding.Quantity) * 0.01)

            signal_strength = self._get_signal_strength(algorithm, symbol)

            if is_exit:
                # Exits always use market orders
                order_type = "market"
                tier = "exit"
                tag = self._build_order_tag(algorithm, tier, signal_strength)
                ticket = algorithm.MarketOrder(symbol, unordered_quantity, tag=tag)
                if ticket is not None:
                    self.market_price_at_submit[ticket.OrderId] = price
            elif signal_strength >= self.strong_threshold:
                # Strong signals use limit orders at market price
                order_type = "limit"
                tier = "strong"
                limit_price = self._compute_limit_price(
                    security, price, unordered_quantity, self.strong_offset_pct)
                tag = self._build_order_tag(algorithm, tier, signal_strength)
                ticket = algorithm.LimitOrder(symbol, unordered_quantity, limit_price, tag=tag)
                if ticket is not None:
                    self.open_limit_tickets.append(ticket)
                    self.limit_open_checks[ticket.OrderId] = 0
                    self.market_price_at_submit[ticket.OrderId] = price
                    # Extract and store week_id for signal-aware cancellation
                    week_id = self._extract_week_id_from_tag(tag)
                    if week_id:
                        self.order_week_ids[ticket.OrderId] = week_id
            elif signal_strength >= self.moderate_threshold:
                order_type = "limit"
                tier = "moderate"
                limit_price = self._compute_limit_price(
                    security, price, unordered_quantity, self.moderate_offset_pct)
                tag = self._build_order_tag(algorithm, tier, signal_strength)
                ticket = algorithm.LimitOrder(symbol, unordered_quantity, limit_price, tag=tag)
                if ticket is not None:
                    self.open_limit_tickets.append(ticket)
                    self.limit_open_checks[ticket.OrderId] = 0
                    self.market_price_at_submit[ticket.OrderId] = price
                    # Extract and store week_id for signal-aware cancellation
                    week_id = self._extract_week_id_from_tag(tag)
                    if week_id:
                        self.order_week_ids[ticket.OrderId] = week_id
            else:
                order_type = "limit"
                tier = "weak"
                limit_price = self._compute_limit_price(
                    security, price, unordered_quantity, self.weak_offset_pct)
                tag = self._build_order_tag(algorithm, tier, signal_strength)
                ticket = algorithm.LimitOrder(symbol, unordered_quantity, limit_price, tag=tag)
                if ticket is not None:
                    self.open_limit_tickets.append(ticket)
                    self.limit_open_checks[ticket.OrderId] = 0
                    self.market_price_at_submit[ticket.OrderId] = price
                    # Extract and store week_id for signal-aware cancellation
                    week_id = self._extract_week_id_from_tag(tag)
                    if week_id:
                        self.order_week_ids[ticket.OrderId] = week_id

            # Debug logging
            if order_type == "market":
                algorithm.Debug(
                    f"  {order_type.title()}: {'Buy' if unordered_quantity > 0 else 'Sell'} "
                    f"{abs(unordered_quantity)} {symbol.Value} (signal={signal_strength:.2f})")
            else:
                algorithm.Debug(
                    f"  Limit: {'Buy' if unordered_quantity > 0 else 'Sell'} "
                    f"{abs(unordered_quantity)} {symbol.Value} @ ${limit_price:.2f} "
                    f"(signal={signal_strength:.2f})")

        self.targets_collection.ClearFulfilled(algorithm)

    def cancel_stale_orders(self, algorithm):
        """
        Cancel limit orders from PREVIOUS rebalance cycles only.

        This allows the full 5-day scaling window to complete for current-cycle orders
        while still preventing stale orders from old signals.

        Falls back to legacy 2-check behavior if week_id tracking is unavailable.
        """
        # Get current week_id from PCM (set on rebalance day in portfolio model)
        pcm = getattr(algorithm, 'pcm', None)
        current_week_id = getattr(pcm, 'current_week_id', None) if pcm is not None else None

        if not current_week_id:
            # Fallback: if no current_week_id set, use old 2-check behavior
            algorithm.Debug("  [Signal-Aware] Warning: current_week_id not set, using legacy 2-check cancellation")
            self._cancel_stale_orders_legacy(algorithm)
            return

        # Cancel orders from previous rebalance cycles
        orders_to_cancel = []
        for ticket in self.open_limit_tickets:
            if ticket.Status in (OrderStatus.Submitted, OrderStatus.PartiallyFilled):
                order_week_id = self.order_week_ids.get(ticket.OrderId)

                if not order_week_id:
                    # Order has no week_id (possible early in run); fall back to legacy logic for this order
                    algorithm.Debug(f"  [Signal-Aware] Warning: Order {ticket.OrderId} has no week_id; applying legacy check")
                    # Legacy behavior for this ticket only
                    checks = self.limit_open_checks.get(ticket.OrderId, 0) + 1
                    self.limit_open_checks[ticket.OrderId] = checks
                    if checks >= self.limit_cancel_after_open_checks:
                        algorithm.Debug(
                            f"  [LEGACY] Cancelling stale order {ticket.OrderId} ({ticket.Symbol.Value}) after {checks} checks"
                        )
                        orders_to_cancel.append(ticket)
                    continue

                # Compare week_id dates directly (YYYY-MM-DD format allows lexicographic comparison)
                # Only cancel if order is from PREVIOUS cycle (older date)
                if order_week_id < current_week_id:
                    algorithm.Debug(
                        f"  [Signal-Aware] Cancelling order {ticket.OrderId} ({ticket.Symbol.Value}) "
                        f"from week {order_week_id} (current: {current_week_id})"
                    )
                    orders_to_cancel.append(ticket)

        # Execute cancellations and cleanup
        for ticket in orders_to_cancel:
            ticket.Cancel()

            # Cleanup tracking dictionaries
            if ticket.OrderId in self.limit_open_checks:
                del self.limit_open_checks[ticket.OrderId]
            if ticket.OrderId in self.market_price_at_submit:
                del self.market_price_at_submit[ticket.OrderId]
            if ticket.OrderId in self.order_week_ids:
                del self.order_week_ids[ticket.OrderId]

            self.open_limit_tickets.remove(ticket)

    def _cancel_stale_orders_legacy(self, algorithm):
        """
        Legacy 2-check cancellation logic (fallback only).

        Used when week_id tracking is unavailable or during warmup period.
        """
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

                    # Cleanup
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

    def _extract_week_id_from_tag(self, tag):
        """
        Extract week_id from order tag string.

        Args:
            tag (str): Order tag in format 'tier=moderate;week_id=2024-01-02;...'

        Returns:
            str: Week ID (YYYY-MM-DD format) or None if not found
        """
        if not tag:
            return None

        import re
        match = re.search(r'week_id=([^;]+)', tag)
        if match:
            week_id = match.group(1).strip()
            # Return None if week_id is empty string (can happen early in run)
            return week_id if week_id else None
        return None

    def OnOrderEvent(self, algorithm, order_event):
        if order_event.Status in (OrderStatus.Filled, OrderStatus.Canceled, OrderStatus.Invalid):
            self.open_limit_tickets = [
                t for t in self.open_limit_tickets
                if t.OrderId != order_event.OrderId
            ]
            self.limit_open_checks.pop(order_event.OrderId, None)
            self.order_week_ids.pop(order_event.OrderId, None)
            # Keep market_price_at_submit until after logging is complete
            # Will be cleaned up in main.py after logger.log_order_event is called

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
        """
        Safely look up signal strength for a symbol.
        Returns default_signal_strength if not found.
        """
        pcm = getattr(algorithm, 'pcm', None)
        if pcm is None:
            return self.default_signal_strength
        strengths = getattr(pcm, 'signal_strengths', {})
        return strengths.get(symbol, self.default_signal_strength)

    def _build_order_tag(self, algorithm, tier, signal_strength):
        """Attach execution metadata for research notebooks."""
        pcm = getattr(algorithm, 'pcm', None)
        week_id = getattr(pcm, 'current_week_id', '') if pcm is not None else ''
        scale_day = getattr(pcm, 'current_scale_day', '') if pcm is not None else ''
        return (
            f"tier={tier};"
            f"signal={signal_strength:.4f};"
            f"week_id={week_id};"
            f"scale_day={scale_day}"
        )

    def _compute_limit_price(self, security, price, quantity, offset_pct):
        """
        Compute limit price with offset, rounded to the security's tick size.
        """
        if quantity > 0:
            raw_price = price * (1 - offset_pct)
        else:
            raw_price = price * (1 + offset_pct)

        tick = security.SymbolProperties.MinimumPriceVariation
        if tick > 0:
            return round(raw_price / tick) * tick
        return round(raw_price, 2)
