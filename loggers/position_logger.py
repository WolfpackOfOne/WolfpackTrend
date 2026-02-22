"""Position and trade logging."""
from core.formatting import build_csv


POSITION_COLUMNS = [
    'date', 'symbol', 'invested', 'quantity', 'price', 'market_value', 'weight',
    'unrealized_pnl', 'daily_pnl', 'daily_unrealized_pnl', 'daily_realized_pnl',
    'daily_fees', 'daily_dividends', 'daily_total_net_pnl', 'avg_price'
]

TRADE_COLUMNS = [
    'date', 'symbol', 'action', 'quantity', 'avg_price',
    'exit_price', 'realized_pnl'
]


class PositionLogger:
    def __init__(self, team_id="production"):
        self.team_id = team_id
        self.positions = []
        self.trades = []
        self.prev_positions = {}
        self.prev_symbol_totals = {}

    def log_positions(self, algorithm, current_date, nav, daily_dividends_by_symbol):
        """Log all current positions and detect closed positions."""
        current_symbols = set()

        for symbol, holding in algorithm.Portfolio.items():
            sym_str = str(symbol.Value)
            invested = holding.Invested
            if invested:
                current_symbols.add(sym_str)

            profit = float(holding.Profit)
            unrealized = float(holding.UnrealizedProfit)
            fees = float(holding.TotalFees)
            dividends = float(holding.TotalDividends)
            net_total = profit + unrealized - fees

            prev_totals = self.prev_symbol_totals.get(sym_str, {
                'profit': 0.0, 'unrealized': 0.0, 'fees': 0.0,
                'net': 0.0, 'dividends': 0.0
            })
            daily_realized = profit - prev_totals['profit']
            daily_unrealized = unrealized - prev_totals['unrealized']
            daily_fees = fees - prev_totals['fees']
            daily_total_net = net_total - prev_totals['net']
            daily_dividends = daily_dividends_by_symbol.get(
                sym_str, dividends - prev_totals['dividends']
            )

            has_activity = any(
                abs(x) > 1e-6 for x in (daily_realized, daily_unrealized, daily_fees, daily_total_net, daily_dividends)
            )
            if not invested and not has_activity:
                self.prev_symbol_totals[sym_str] = {
                    'profit': profit, 'unrealized': unrealized,
                    'fees': fees, 'net': net_total, 'dividends': dividends
                }
                continue

            market_value = holding.Quantity * holding.Price if invested else 0.0
            weight = market_value / nav if nav > 0 else 0

            prev_unrealized = 0.0
            if sym_str in self.prev_positions:
                prev_unrealized = self.prev_positions[sym_str].get('unrealized_pnl', 0.0)
            daily_pnl = holding.UnrealizedProfit - prev_unrealized

            self.positions.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'symbol': sym_str,
                'invested': int(invested),
                'quantity': holding.Quantity if invested else 0,
                'price': round(holding.Price, 2) if invested else 0.0,
                'market_value': round(market_value, 2),
                'weight': round(weight, 4),
                'unrealized_pnl': round(unrealized, 2),
                'daily_pnl': round(daily_pnl, 2),
                'daily_unrealized_pnl': round(daily_unrealized, 2),
                'daily_realized_pnl': round(daily_realized, 2),
                'daily_fees': round(daily_fees, 2),
                'daily_dividends': round(daily_dividends, 2),
                'daily_total_net_pnl': round(daily_total_net, 2),
                'avg_price': round(holding.AveragePrice, 2)
            })

            if invested:
                self.prev_positions[sym_str] = {
                    'quantity': holding.Quantity,
                    'avg_price': holding.AveragePrice,
                    'unrealized_pnl': holding.UnrealizedProfit,
                    'price': holding.Price
                }

            self.prev_symbol_totals[sym_str] = {
                'profit': profit, 'unrealized': unrealized,
                'fees': fees, 'net': net_total, 'dividends': dividends
            }

        # Detect closed positions
        for sym_str, prev_data in list(self.prev_positions.items()):
            if sym_str not in current_symbols:
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
                del self.prev_positions[sym_str]

    def save(self, algorithm):
        pos_count = len(self.positions)
        trade_count = len(self.trades)
        if self.positions:
            csv_content = build_csv(self.positions, POSITION_COLUMNS)
            algorithm.ObjectStore.Save(f"{self.team_id}/positions.csv", csv_content)
        if self.trades:
            csv_content = build_csv(self.trades, TRADE_COLUMNS)
            algorithm.ObjectStore.Save(f"{self.team_id}/trades.csv", csv_content)
        return pos_count, trade_count
