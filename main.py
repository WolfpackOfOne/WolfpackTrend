from AlgorithmImports import *
from models import DOW30, CompositeTrendAlphaModel, TargetVolPortfolioConstructionModel, PortfolioLogger


class Dow30TrendAlgorithm(QCAlgorithm):
    """
    Dow 30 Trend-Following Strategy

    Uses a composite trend signal from 3 horizons (20/63/252 day SMAs)
    normalized by ATR. Portfolio targets 10% annualized volatility with
    constraints on gross/net exposure and per-name weights.

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
        self.Debug("ObjectStore: Cleared previous wolfpack data files")

        # Log initialization
        self.Debug("=" * 60)
        self.Debug("WOLFPACK TREND STRATEGY INITIALIZED")
        self.Debug(f"Period: {self.StartDate.strftime('%Y-%m-%d')} to {self.EndDate.strftime('%Y-%m-%d')}")
        self.Debug(f"Starting Cash: ${self.Portfolio.Cash:,.0f}")
        self.Debug(f"Universe: {len(DOW30)} Dow 30 stocks")
        self.Debug("=" * 60)

        # Set up framework models (pass logger to alpha for signal tracking)
        self.SetAlpha(CompositeTrendAlphaModel(
            short_period=20,
            medium_period=63,
            long_period=252,
            atr_period=14,
            rebalance_interval_days=7,
            logger=self.logger,
            algorithm=self
        ))
        self.Debug("Alpha: Composite Trend (SMA 20/63/252, ATR 14, weekly rebalance)")

        # Store reference to portfolio construction model for UpdateReturns
        self.pcm = TargetVolPortfolioConstructionModel(
            target_vol_annual=0.10,
            max_gross=1.50,
            max_net=0.50,
            max_weight=0.10,
            vol_lookback=63,
            algorithm=self
        )
        self.SetPortfolioConstruction(self.pcm)
        self.Debug(f"PCM: Target Vol 10%, Max Gross 150%, Max Net 50%, Max Weight 10%")

        # Immediate execution (market orders)
        self.SetExecution(ImmediateExecutionModel())

        # Settings
        self.Settings.RebalancePortfolioOnInsightChanges = True
        self.Settings.RebalancePortfolioOnSecurityChanges = True

    def OnData(self, data):
        # Update rolling returns for volatility estimation
        self.pcm.UpdateReturns(self, data)

        # Log daily portfolio metrics
        self.logger.log_daily(self, self.pcm, data)

    def OnOrderEvent(self, orderEvent):
        """Track slippage by comparing fill price to expected price at signal generation."""
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
