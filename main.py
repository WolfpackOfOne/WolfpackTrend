from AlgorithmImports import *
from models import DOW30, CompositeTrendAlphaModel, TargetVolPortfolioConstructionModel, SignalStrengthExecutionModel, PortfolioLogger


class Dow30TrendAlgorithm(QCAlgorithm):
    """
    Dow 30 Trend-Following Strategy

    Uses a composite trend signal from 3 horizons (20/63/252 day SMAs)
    normalized by ATR. Portfolio targets 10% annualized volatility with
    constraints on gross/net exposure and per-name weights.

    Signal strength controls order type (market vs limit) and position
    scaling pace over the trading week.

    Logs daily portfolio metrics to ObjectStore for research analysis.
    """

    def Initialize(self):
        # Backtest window: 2+ years to allow for warmup
        self.SetStartDate(2022, 1, 1)
        self.SetEndDate(2024, 1, 1)
        self.SetCash(100000)

        # Benchmark
        self.SetBenchmark("SPY")

        # Warmup for SMA(252)
        self.SetWarmUp(252, Resolution.Daily)

        # Add Dow 30 equities
        for ticker in DOW30:
            self.AddEquity(ticker, Resolution.Daily)

        # Initialize logger for portfolio tracking
        self.logger = PortfolioLogger()

        # Clear ObjectStore to remove stale files from previous runs
        if self.ObjectStore.ContainsKey("wolfpack/daily_snapshots.csv"):
            self.ObjectStore.Delete("wolfpack/daily_snapshots.csv")
        if self.ObjectStore.ContainsKey("wolfpack/positions.csv"):
            self.ObjectStore.Delete("wolfpack/positions.csv")
        if self.ObjectStore.ContainsKey("wolfpack/trades.csv"):
            self.ObjectStore.Delete("wolfpack/trades.csv")
        if self.ObjectStore.ContainsKey("wolfpack/signals.csv"):
            self.ObjectStore.Delete("wolfpack/signals.csv")
        if self.ObjectStore.ContainsKey("wolfpack/slippage.csv"):
            self.ObjectStore.Delete("wolfpack/slippage.csv")
        if self.ObjectStore.ContainsKey("wolfpack/targets.csv"):
            self.ObjectStore.Delete("wolfpack/targets.csv")
        if self.ObjectStore.ContainsKey("wolfpack/order_events.csv"):
            self.ObjectStore.Delete("wolfpack/order_events.csv")
        self.Debug("ObjectStore: Cleared previous wolfpack data files")

        # Log initialization
        self.Debug("=" * 60)
        self.Debug("WOLFPACK TREND STRATEGY INITIALIZED")
        self.Debug(f"Period: {self.StartDate.strftime('%Y-%m-%d')} to {self.EndDate.strftime('%Y-%m-%d')}")
        self.Debug(f"Starting Cash: ${self.Portfolio.Cash:,.0f}")
        self.Debug(f"Universe: {len(DOW30)} Dow 30 stocks")
        self.Debug("=" * 60)

        # Portfolio construction model (must be created before alpha so alpha can set is_rebalance_day)
        self.pcm = TargetVolPortfolioConstructionModel(
            target_vol_annual=0.10,
            max_gross=1.50,
            max_net=0.50,
            max_weight=0.10,
            vol_lookback=63,
            scaling_days=5,
            rebalance_interval_trading_days=5,
            algorithm=self
        )
        self.SetPortfolioConstruction(self.pcm)
        self.Debug(f"PCM: Target Vol 10%, Max Gross 150%, Max Net 50%, Max Weight 10%, Scaling 5 days")

        # Alpha model (emits daily, recalculates every 5 trading days)
        self.SetAlpha(CompositeTrendAlphaModel(
            short_period=20,
            medium_period=63,
            long_period=252,
            atr_period=14,
            rebalance_interval_trading_days=5,
            signal_temperature=3.0,
            logger=self.logger,
            algorithm=self
        ))
        self.Debug("Alpha: Composite Trend (SMA 20/63/252, ATR 14, weekly rebalance, daily emission, temp=3.0)")

        self.execution_model = SignalStrengthExecutionModel(
            strong_threshold=0.70,
            moderate_threshold=0.30,
            moderate_offset_pct=0.005,
            weak_offset_pct=0.015,
            default_signal_strength=0.50,
            limit_cancel_after_open_checks=2
        )
        self.SetExecution(self.execution_model)
        self.Debug(
            "Execution: Signal-strength based "
            "(strong>=0.70->market, moderate>=0.30->limit 0.5%, weak->limit 1.5%, "
            "stale limits cancel after 2 open checks)"
        )

        # Schedule stale order cancellation at market open, before the pipeline runs
        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.AfterMarketOpen("SPY", 0),
            self._cancel_stale_orders
        )

        # Settings
        self.Settings.RebalancePortfolioOnInsightChanges = True
        self.Settings.RebalancePortfolioOnSecurityChanges = True

    def _cancel_stale_orders(self):
        """Cancel unfilled limit orders from previous days before today's pipeline runs."""
        if self.execution_model is not None:
            self.execution_model.cancel_stale_orders(self)

    def OnData(self, data):
        # Update rolling returns for volatility estimation
        self.pcm.UpdateReturns(self, data)

        # Log daily portfolio metrics
        self.logger.log_daily(self, self.pcm, data)

    def OnOrderEvent(self, orderEvent):
        """Track slippage by comparing fill price to expected price at signal generation."""
        if self.execution_model is not None:
            self.execution_model.OnOrderEvent(self, orderEvent)

        order = self.Transactions.GetOrderById(orderEvent.OrderId)
        order_type = str(order.Type) if order is not None else ""
        direction = str(order.Direction) if order is not None else (
            "Buy" if orderEvent.FillQuantity > 0 else "Sell"
        )
        quantity = float(order.Quantity) if order is not None else 0.0
        limit_price = getattr(order, "LimitPrice", None) if order is not None else None
        tag = order.Tag if order is not None else ""

        # Get market price at submit time from execution model
        market_price_at_submit = None
        if self.execution_model is not None:
            market_price_at_submit = self.execution_model.market_price_at_submit.get(orderEvent.OrderId)

        self.logger.log_order_event(
            date=self.Time,
            order_id=orderEvent.OrderId,
            symbol=orderEvent.Symbol,
            status=str(orderEvent.Status),
            direction=direction,
            quantity=quantity,
            fill_quantity=float(orderEvent.FillQuantity),
            fill_price=float(orderEvent.FillPrice),
            order_type=order_type,
            limit_price=limit_price,
            market_price_at_submit=market_price_at_submit,
            tag=tag
        )

        # Clean up market price tracking after logging
        if orderEvent.Status in (OrderStatus.Filled, OrderStatus.Canceled, OrderStatus.Invalid):
            if self.execution_model is not None:
                self.execution_model.market_price_at_submit.pop(orderEvent.OrderId, None)

        if orderEvent.Status != OrderStatus.Filled:
            return

        symbol = orderEvent.Symbol
        fill_price = orderEvent.FillPrice
        quantity = orderEvent.FillQuantity

        # Get expected price from PCM (price at target generation)
        expected_price = self.pcm.expected_prices.get(symbol, fill_price)

        # Determine direction
        direction = "Buy" if quantity > 0 else "Sell"

        # Log the trade
        fill_value = abs(quantity * fill_price)
        self.Debug(f"  Trade: {direction} {abs(quantity)} {symbol.Value} @ ${fill_price:.2f} (${fill_value:,.0f})")

        self.logger.log_slippage(
            date=self.Time,
            symbol=symbol,
            direction=direction,
            quantity=quantity,
            expected_price=expected_price,
            fill_price=fill_price
        )

    def OnEndOfAlgorithm(self):
        """Save all logged data to ObjectStore at end of backtest."""
        # Log final summary
        self.Debug("=" * 60)
        self.Debug("BACKTEST COMPLETE")
        nav = self.Portfolio.TotalPortfolioValue
        starting = self.logger.starting_cash or 100000
        total_return = (nav / starting - 1) * 100
        self.Debug(f"Final NAV: ${nav:,.2f}")
        self.Debug(f"Total Return: {total_return:+.2f}%")
        self.Debug(f"Total Trades: {len(self.logger.slippage)}")
        self.Debug("=" * 60)

        self.logger.save_to_objectstore(self)
