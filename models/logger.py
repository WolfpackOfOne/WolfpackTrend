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
        self.trades: List[Dict[str, Any]] = []  # Track realized P&L from closes
        self.targets: List[Dict[str, Any]] = []  # Daily target-state tracking
        self.order_events: List[Dict[str, Any]] = []  # Full order lifecycle events

        # Track previous NAV for daily P&L
        self.prev_nav: Optional[float] = None
        self.starting_cash: Optional[float] = None

        # Daily slippage accumulator (reset each day)
        self.daily_slippage: float = 0.0
        self.last_slippage_date: Optional[datetime] = None
        # Daily dividends accumulator (reset each day)
        self.daily_dividends_by_symbol: Dict[str, float] = {}
        self.last_dividends_date: Optional[datetime] = None

        # Track previous day's positions for detecting closes
        self.prev_positions: Dict[str, Dict[str, Any]] = {}  # symbol -> {qty, avg_price, unrealized}
        # Track cumulative totals for daily delta calculations
        self.prev_symbol_totals: Dict[str, Dict[str, float]] = {}  # symbol -> {profit, unrealized, fees, net, dividends}

    def log_daily(self, algorithm, pcm, data=None) -> None:
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
        # Log daily target state snapshot
        self._log_targets(algorithm, pcm, current_date)

    def _log_positions(self, algorithm, current_date, nav: float) -> None:
        """Log all current positions and detect closed positions."""
        current_symbols = set()

        for symbol, holding in algorithm.Portfolio.items():
            sym_str = str(symbol.Value)
            invested = holding.Invested
            if invested:
                current_symbols.add(sym_str)

            # Calculate daily deltas from cumulative totals (realized, unrealized, fees)
            profit = float(holding.Profit)
            unrealized = float(holding.UnrealizedProfit)
            fees = float(holding.TotalFees)
            dividends = float(holding.TotalDividends)
            net_total = profit + unrealized - fees

            prev_totals = self.prev_symbol_totals.get(sym_str, {
                'profit': 0.0,
                'unrealized': 0.0,
                'fees': 0.0,
                'net': 0.0,
                'dividends': 0.0
            })
            daily_realized = profit - prev_totals['profit']
            daily_unrealized = unrealized - prev_totals['unrealized']
            daily_fees = fees - prev_totals['fees']
            daily_total_net = net_total - prev_totals['net']
            daily_dividends = self.daily_dividends_by_symbol.get(
                sym_str, dividends - prev_totals['dividends']
            )

            # Only append a row if invested or there is P&L/fee activity
            has_activity = any(
                abs(x) > 1e-6 for x in (daily_realized, daily_unrealized, daily_fees, daily_total_net, daily_dividends)
            )
            if not invested and not has_activity:
                self.prev_symbol_totals[sym_str] = {
                    'profit': profit,
                    'unrealized': unrealized,
                    'fees': fees,
                    'net': net_total,
                    'dividends': dividends
                }
                continue

            market_value = holding.Quantity * holding.Price if invested else 0.0
            weight = market_value / nav if nav > 0 else 0

            # Get previous day's unrealized P&L for this symbol
            prev_unrealized = 0.0
            if sym_str in self.prev_positions:
                prev_unrealized = self.prev_positions[sym_str].get('unrealized_pnl', 0.0)

            # Daily P&L = change in unrealized P&L
            # For new positions, this equals the current unrealized (P&L since entry)
            daily_pnl = holding.UnrealizedProfit - prev_unrealized

            self.positions.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'symbol': sym_str,
                'invested': int(invested),
                'quantity': holding.Quantity if invested else 0,
                'price': round(holding.Price, 2) if invested else 0.0,  # Current price for returns calc
                'market_value': round(market_value, 2),
                'weight': round(weight, 4),
                'unrealized_pnl': round(unrealized, 2),
                'daily_pnl': round(daily_pnl, 2),  # Daily MTM P&L
                'daily_unrealized_pnl': round(daily_unrealized, 2),
                'daily_realized_pnl': round(daily_realized, 2),
                'daily_fees': round(daily_fees, 2),
                'daily_dividends': round(daily_dividends, 2),
                'daily_total_net_pnl': round(daily_total_net, 2),
                'avg_price': round(holding.AveragePrice, 2)
            })

            # Update tracking for next day
            if invested:
                self.prev_positions[sym_str] = {
                    'quantity': holding.Quantity,
                    'avg_price': holding.AveragePrice,
                    'unrealized_pnl': holding.UnrealizedProfit,
                    'price': holding.Price
                }

            self.prev_symbol_totals[sym_str] = {
                'profit': profit,
                'unrealized': unrealized,
                'fees': fees,
                'net': net_total,
                'dividends': dividends
            }

        # Detect closed positions (were held yesterday, not today)
        for sym_str, prev_data in list(self.prev_positions.items()):
            if sym_str not in current_symbols:
                # Position was closed - log the realized P&L
                # The realized P&L is approximately the last unrealized P&L
                # (actual realized = sale proceeds - cost basis, but we approximate)
                realized_pnl = prev_data.get('unrealized_pnl', 0.0)

                self.trades.append({
                    'date': current_date.strftime('%Y-%m-%d'),
                    'symbol': sym_str,
                    'action': 'CLOSE',
                    'quantity': prev_data.get('quantity', 0),
                    'avg_price': round(prev_data.get('avg_price', 0), 2),
                    'exit_price': round(prev_data.get('price', 0), 2),
                    'realized_pnl': round(realized_pnl, 2)
                })

                # Remove from tracking
                del self.prev_positions[sym_str]

    def _log_targets(self, algorithm, pcm, current_date) -> None:
        """Log per-symbol weekly target state for exact outstanding-order analytics."""
        if pcm is None or not hasattr(pcm, 'get_daily_target_state'):
            return

        rows = pcm.get_daily_target_state(algorithm)
        if not rows:
            return

        for row in rows:
            self.targets.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'week_id': row.get('week_id', ''),
                'symbol': row.get('symbol', ''),
                'start_w': row.get('start_w', ''),
                'weekly_target_w': row.get('weekly_target_w', ''),
                'scheduled_fraction': row.get('scheduled_fraction', ''),
                'scheduled_w': row.get('scheduled_w', ''),
                'actual_w': row.get('actual_w', ''),
                'scale_day': row.get('scale_day', '')
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

    def log_order_event(self, date: datetime, order_id: int, symbol,
                        status: str, direction: str, quantity: float,
                        fill_quantity: float, fill_price: float,
                        order_type: str, limit_price: Optional[float] = None,
                        tag: str = "") -> None:
        """Log all order events (submitted, partially filled, filled, canceled, etc.)."""
        self.order_events.append({
            'date': date.strftime('%Y-%m-%d'),
            'order_id': order_id,
            'symbol': str(symbol.Value) if hasattr(symbol, 'Value') else str(symbol),
            'status': status,
            'direction': direction,
            'quantity': quantity,
            'fill_quantity': fill_quantity,
            'fill_price': round(fill_price, 4) if fill_price else '',
            'order_type': order_type,
            'limit_price': round(limit_price, 4) if limit_price is not None else '',
            'tag': tag
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

        # Positions (with daily P&L for attribution)
        if self.positions:
            csv_content = self._build_csv(self.positions, [
                'date', 'symbol', 'invested', 'quantity', 'price', 'market_value', 'weight',
                'unrealized_pnl', 'daily_pnl', 'daily_unrealized_pnl', 'daily_realized_pnl',
                'daily_fees', 'daily_dividends', 'daily_total_net_pnl', 'avg_price'
            ])
            algorithm.ObjectStore.Save("wolfpack/positions.csv", csv_content)

        # Trades (realized P&L from closed positions)
        if self.trades:
            csv_content = self._build_csv(self.trades, [
                'date', 'symbol', 'action', 'quantity', 'avg_price',
                'exit_price', 'realized_pnl'
            ])
            algorithm.ObjectStore.Save("wolfpack/trades.csv", csv_content)

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

        # Daily target-state logs
        if self.targets:
            csv_content = self._build_csv(self.targets, [
                'date', 'week_id', 'symbol', 'start_w', 'weekly_target_w',
                'scheduled_fraction', 'scheduled_w', 'actual_w', 'scale_day'
            ])
            algorithm.ObjectStore.Save("wolfpack/targets.csv", csv_content)

        # Full order lifecycle events
        if self.order_events:
            csv_content = self._build_csv(self.order_events, [
                'date', 'order_id', 'symbol', 'status', 'direction',
                'quantity', 'fill_quantity', 'fill_price',
                'order_type', 'limit_price', 'tag'
            ])
            algorithm.ObjectStore.Save("wolfpack/order_events.csv", csv_content)

        algorithm.Debug(f"ObjectStore: Saved {len(self.snapshots)} snapshots, "
                       f"{len(self.positions)} position records, "
                       f"{len(self.trades)} trades, "
                       f"{len(self.signals)} signals, "
                       f"{len(self.slippage)} slippage records, "
                       f"{len(self.targets)} target-state rows, "
                       f"{len(self.order_events)} order events")

    def _build_csv(self, data: List[Dict], columns: List[str]) -> str:
        """Build CSV string from list of dictionaries."""
        lines = [','.join(columns)]
        for row in data:
            values = [str(row.get(col, '')) for col in columns]
            lines.append(','.join(values))
        return '\n'.join(lines)
