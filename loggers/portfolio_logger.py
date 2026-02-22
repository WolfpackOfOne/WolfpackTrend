"""Portfolio logger facade that delegates to focused sub-loggers.

Preserves the complete public API of the original PortfolioLogger.
"""
from datetime import datetime
from typing import Dict, List, Any, Optional

from loggers.snapshot_logger import SnapshotLogger
from loggers.position_logger import PositionLogger
from loggers.signal_logger import SignalLogger
from loggers.slippage_logger import SlippageLogger
from loggers.order_event_logger import OrderEventLogger
from loggers.target_logger import TargetLogger


class PortfolioLogger:
    """
    Logs daily portfolio metrics to QuantConnect ObjectStore for research analysis.
    Stores: daily snapshots, positions, signals, slippage, trades, targets, order events.
    """

    def __init__(self, team_id="production"):
        self.team_id = team_id
        self._snapshot_logger = SnapshotLogger(team_id=team_id)
        self._position_logger = PositionLogger(team_id=team_id)
        self._signal_logger = SignalLogger(team_id=team_id)
        self._slippage_logger = SlippageLogger(team_id=team_id)
        self._order_event_logger = OrderEventLogger(team_id=team_id)
        self._target_logger = TargetLogger(team_id=team_id)

        # Track previous NAV for daily P&L
        self.prev_nav: Optional[float] = None
        self.starting_cash: Optional[float] = None

        # Daily dividends accumulator (reset each day)
        self.daily_dividends_by_symbol: Dict[str, float] = {}
        self.last_dividends_date: Optional[datetime] = None

    # --- Public properties for compatibility ---

    @property
    def snapshots(self):
        return self._snapshot_logger.snapshots

    @property
    def positions(self):
        return self._position_logger.positions

    @property
    def trades(self):
        return self._position_logger.trades

    @property
    def signals(self):
        return self._signal_logger.signals

    @property
    def slippage(self):
        return self._slippage_logger.slippage

    @property
    def targets(self):
        return self._target_logger.targets

    @property
    def order_events(self):
        return self._order_event_logger.order_events

    @property
    def daily_slippage(self):
        return self._slippage_logger.daily_slippage

    @daily_slippage.setter
    def daily_slippage(self, value):
        self._slippage_logger.daily_slippage = value

    @property
    def last_slippage_date(self):
        return self._slippage_logger.last_slippage_date

    @last_slippage_date.setter
    def last_slippage_date(self, value):
        self._slippage_logger.last_slippage_date = value

    @property
    def prev_positions(self):
        return self._position_logger.prev_positions

    @property
    def prev_symbol_totals(self):
        return self._position_logger.prev_symbol_totals

    # --- Public API (preserved exactly) ---

    def log_daily(self, algorithm, pcm, data=None) -> None:
        """Log daily portfolio snapshot. Call from OnData()."""
        if algorithm.IsWarmingUp:
            return

        current_date = algorithm.Time.date()

        if self.starting_cash is None:
            self.starting_cash = float(algorithm.Portfolio.TotalPortfolioValue)

        nav = algorithm.Portfolio.TotalPortfolioValue
        cash = algorithm.Portfolio.Cash

        # Calculate exposures
        long_value = 0.0
        short_value = 0.0
        num_positions = 0

        for symbol, holding in algorithm.Portfolio.items():
            if not holding.Invested:
                continue
            position_value = holding.Quantity * holding.Price
            num_positions += 1
            if position_value > 0:
                long_value += position_value
            else:
                short_value += abs(position_value)

        gross_exposure = (long_value + short_value) / nav if nav > 0 else 0
        net_exposure = (long_value - short_value) / nav if nav > 0 else 0
        long_exposure = long_value / nav if nav > 0 else 0
        short_exposure = short_value / nav if nav > 0 else 0

        daily_pnl = 0.0
        if self.prev_nav is not None:
            daily_pnl = nav - self.prev_nav
        self.prev_nav = nav

        cumulative_pnl = nav - self.starting_cash

        # Reset daily slippage if new day
        self._slippage_logger.reset_daily(current_date)

        # Reset daily dividends accumulator if new day
        if self.last_dividends_date != current_date:
            self.daily_dividends_by_symbol = {}
            self.last_dividends_date = current_date

        # Capture dividends from Slice if provided
        if data is not None and hasattr(data, 'Dividends'):
            for dividend in data.Dividends.Values:
                if dividend is None:
                    continue
                symbol = dividend.Symbol
                if symbol not in algorithm.Securities:
                    continue
                quantity = algorithm.Portfolio[symbol].Quantity
                if quantity == 0:
                    continue
                conversion_rate = algorithm.Securities[symbol].QuoteCurrency.ConversionRate
                amount = float(quantity) * float(dividend.Distribution) * float(conversion_rate)
                sym_str = str(symbol.Value)
                self.daily_dividends_by_symbol[sym_str] = self.daily_dividends_by_symbol.get(sym_str, 0.0) + amount

        # Estimate portfolio volatility from PCM if available
        estimated_vol = None
        if hasattr(pcm, '_estimate_portfolio_vol') and hasattr(pcm, 'symbols'):
            weights = {}
            for symbol in pcm.symbols:
                if symbol in algorithm.Portfolio and algorithm.Portfolio[symbol].Invested:
                    holding = algorithm.Portfolio[symbol]
                    weights[symbol] = (holding.Quantity * holding.Price) / nav if nav > 0 else 0
            if weights:
                estimated_vol = pcm._estimate_portfolio_vol(weights)

        self._snapshot_logger.log({
            'date': current_date.strftime('%Y-%m-%d'),
            'nav': round(nav, 2),
            'cash': round(cash, 2),
            'gross_exposure': round(gross_exposure, 4),
            'net_exposure': round(net_exposure, 4),
            'long_exposure': round(long_exposure, 4),
            'short_exposure': round(short_exposure, 4),
            'daily_pnl': round(daily_pnl, 2),
            'cumulative_pnl': round(cumulative_pnl, 2),
            'daily_slippage': round(self._slippage_logger.daily_slippage, 2),
            'num_positions': num_positions,
            'estimated_vol': round(estimated_vol, 4) if estimated_vol else ''
        })

        # Log positions
        self._position_logger.log_positions(algorithm, current_date, nav, self.daily_dividends_by_symbol)
        # Log daily target state snapshot
        self._target_logger.log(algorithm, pcm, current_date)

    def log_signal(self, date, symbol, direction, magnitude, price,
                   sma_short, sma_medium, sma_long, atr) -> None:
        """Log a signal from the alpha model."""
        self._signal_logger.log(date, symbol, direction, magnitude, price,
                                sma_short, sma_medium, sma_long, atr)

    def log_slippage(self, date, symbol, direction, quantity,
                     expected_price, fill_price) -> None:
        """Log slippage for a filled order."""
        self._slippage_logger.log(date, symbol, direction, quantity,
                                  expected_price, fill_price)

    def log_order_event(self, date, order_id, symbol, status, direction,
                        quantity, fill_quantity, fill_price, order_type,
                        limit_price=None, market_price_at_submit=None,
                        tag="") -> None:
        """Log all order events."""
        self._order_event_logger.log(date, order_id, symbol, status, direction,
                                     quantity, fill_quantity, fill_price,
                                     order_type, limit_price,
                                     market_price_at_submit, tag)

    def save_to_objectstore(self, algorithm) -> None:
        """Save all logged data to ObjectStore as CSV files."""
        snap_count = self._snapshot_logger.save(algorithm)
        pos_count, trade_count = self._position_logger.save(algorithm)
        signal_count = self._signal_logger.save(algorithm)
        slip_count = self._slippage_logger.save(algorithm)
        target_count = self._target_logger.save(algorithm)
        event_count = self._order_event_logger.save(algorithm)

        algorithm.Debug(f"ObjectStore: Saved {snap_count} snapshots, "
                       f"{pos_count} position records, "
                       f"{trade_count} trades, "
                       f"{signal_count} signals, "
                       f"{slip_count} slippage records, "
                       f"{target_count} target-state rows, "
                       f"{event_count} order events")
