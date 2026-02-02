from datetime import datetime
from typing import Dict, List, Any, Optional


class PortfolioLogger:
    """
    Logs daily portfolio metrics to QuantConnect ObjectStore for research analysis.
    Stores: daily snapshots, positions, signals, and slippage data.
    """

    def __init__(self):
        # In-memory storage for CSV data
        self.snapshots: List[Dict[str, Any]] = []
        self.positions: List[Dict[str, Any]] = []
        self.signals: List[Dict[str, Any]] = []
        self.slippage: List[Dict[str, Any]] = []

        # Track previous NAV for daily P&L
        self.prev_nav: Optional[float] = None
        self.starting_cash: Optional[float] = None

        # Daily slippage accumulator (reset each day)
        self.daily_slippage: float = 0.0
        self.last_slippage_date: Optional[datetime] = None

    def log_daily(self, algorithm, pcm) -> None:
        """
        Log daily portfolio snapshot. Call from OnData().
        """
        if algorithm.IsWarmingUp:
            return

        current_date = algorithm.Time.date()

        # Initialize starting cash on first call
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

        # Daily P&L
        daily_pnl = 0.0
        if self.prev_nav is not None:
            daily_pnl = nav - self.prev_nav
        self.prev_nav = nav

        cumulative_pnl = nav - self.starting_cash

        # Get daily slippage (reset if new day)
        if self.last_slippage_date != current_date:
            self.daily_slippage = 0.0
            self.last_slippage_date = current_date

        # Estimate portfolio volatility from PCM if available
        estimated_vol = None
        if hasattr(pcm, '_estimate_portfolio_vol') and hasattr(pcm, 'symbols'):
            # Get current weights from portfolio
            weights = {}
            for symbol in pcm.symbols:
                if symbol in algorithm.Portfolio and algorithm.Portfolio[symbol].Invested:
                    holding = algorithm.Portfolio[symbol]
                    weights[symbol] = (holding.Quantity * holding.Price) / nav if nav > 0 else 0
            if weights:
                estimated_vol = pcm._estimate_portfolio_vol(weights)

        self.snapshots.append({
            'date': current_date.strftime('%Y-%m-%d'),
            'nav': round(nav, 2),
            'cash': round(cash, 2),
            'gross_exposure': round(gross_exposure, 4),
            'net_exposure': round(net_exposure, 4),
            'long_exposure': round(long_exposure, 4),
            'short_exposure': round(short_exposure, 4),
            'daily_pnl': round(daily_pnl, 2),
            'cumulative_pnl': round(cumulative_pnl, 2),
            'daily_slippage': round(self.daily_slippage, 2),
            'num_positions': num_positions,
            'estimated_vol': round(estimated_vol, 4) if estimated_vol else ''
        })

        # Log positions
        self._log_positions(algorithm, current_date, nav)

    def _log_positions(self, algorithm, current_date, nav: float) -> None:
        """Log all current positions."""
        for symbol, holding in algorithm.Portfolio.items():
            if not holding.Invested:
                continue

            market_value = holding.Quantity * holding.Price
            weight = market_value / nav if nav > 0 else 0

            self.positions.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'symbol': str(symbol.Value),
                'quantity': holding.Quantity,
                'market_value': round(market_value, 2),
                'weight': round(weight, 4),
                'unrealized_pnl': round(holding.UnrealizedProfit, 2),
                'avg_price': round(holding.AveragePrice, 2)
            })

    def log_signal(self, date: datetime, symbol, direction: str, magnitude: float,
                   price: float, sma_short: float, sma_medium: float,
                   sma_long: float, atr: float) -> None:
        """Log a signal from the alpha model."""
        self.signals.append({
            'date': date.strftime('%Y-%m-%d'),
            'symbol': str(symbol.Value) if hasattr(symbol, 'Value') else str(symbol),
            'direction': direction,
            'magnitude': round(magnitude, 4),
            'price': round(price, 2),
            'sma_short': round(sma_short, 2),
            'sma_medium': round(sma_medium, 2),
            'sma_long': round(sma_long, 2),
            'atr': round(atr, 4)
        })

    def log_slippage(self, date: datetime, symbol, direction: str, quantity: float,
                     expected_price: float, fill_price: float) -> None:
        """Log slippage for a filled order."""
        slippage_dollars = (fill_price - expected_price) * quantity

        # Accumulate daily slippage
        current_date = date.date()
        if self.last_slippage_date != current_date:
            self.daily_slippage = 0.0
            self.last_slippage_date = current_date
        self.daily_slippage += abs(slippage_dollars)

        self.slippage.append({
            'date': date.strftime('%Y-%m-%d'),
            'symbol': str(symbol.Value) if hasattr(symbol, 'Value') else str(symbol),
            'direction': direction,
            'quantity': quantity,
            'expected_price': round(expected_price, 4),
            'fill_price': round(fill_price, 4),
            'slippage_dollars': round(slippage_dollars, 2)
        })

    def save_to_objectstore(self, algorithm) -> None:
        """Save all logged data to ObjectStore as CSV files."""
        # Daily snapshots
        if self.snapshots:
            csv_content = self._build_csv(self.snapshots, [
                'date', 'nav', 'cash', 'gross_exposure', 'net_exposure',
                'long_exposure', 'short_exposure', 'daily_pnl', 'cumulative_pnl',
                'daily_slippage', 'num_positions', 'estimated_vol'
            ])
            algorithm.ObjectStore.Save("wolfpack/daily_snapshots.csv", csv_content)

        # Positions
        if self.positions:
            csv_content = self._build_csv(self.positions, [
                'date', 'symbol', 'quantity', 'market_value', 'weight',
                'unrealized_pnl', 'avg_price'
            ])
            algorithm.ObjectStore.Save("wolfpack/positions.csv", csv_content)

        # Signals
        if self.signals:
            csv_content = self._build_csv(self.signals, [
                'date', 'symbol', 'direction', 'magnitude', 'price',
                'sma_short', 'sma_medium', 'sma_long', 'atr'
            ])
            algorithm.ObjectStore.Save("wolfpack/signals.csv", csv_content)

        # Slippage
        if self.slippage:
            csv_content = self._build_csv(self.slippage, [
                'date', 'symbol', 'direction', 'quantity',
                'expected_price', 'fill_price', 'slippage_dollars'
            ])
            algorithm.ObjectStore.Save("wolfpack/slippage.csv", csv_content)

        algorithm.Debug(f"ObjectStore: Saved {len(self.snapshots)} snapshots, "
                       f"{len(self.positions)} position records, "
                       f"{len(self.signals)} signals, "
                       f"{len(self.slippage)} slippage records")

    def _build_csv(self, data: List[Dict], columns: List[str]) -> str:
        """Build CSV string from list of dictionaries."""
        lines = [','.join(columns)]
        for row in data:
            values = [str(row.get(col, '')) for col in columns]
            lines.append(','.join(values))
        return '\n'.join(lines)
