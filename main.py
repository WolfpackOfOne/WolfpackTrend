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

        # Set up framework models (pass logger to alpha for signal tracking)
        self.SetAlpha(CompositeTrendAlphaModel(
            short_period=20,
            medium_period=63,
            long_period=252,
            atr_period=14,
            logger=self.logger
        ))

        # Store reference to portfolio construction model for UpdateReturns
        self.pcm = TargetVolPortfolioConstructionModel(
            target_vol_annual=0.10,
            max_gross=1.50,
            max_net=0.50,
            max_weight=0.10,
            vol_lookback=63
        )
        self.SetPortfolioConstruction(self.pcm)

        # Immediate execution (market orders)
        self.SetExecution(ImmediateExecutionModel())

        # Settings
        self.Settings.RebalancePortfolioOnInsightChanges = True
        self.Settings.RebalancePortfolioOnSecurityChanges = True

    def OnData(self, data):
        # Update rolling returns for volatility estimation
        self.pcm.UpdateReturns(self, data)

        # Log daily portfolio metrics
        self.logger.log_daily(self, self.pcm)

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
        self.logger.save_to_objectstore(self)
