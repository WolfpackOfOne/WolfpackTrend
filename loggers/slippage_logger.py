"""Per-order slippage logging."""
from core.formatting import build_csv


SLIPPAGE_COLUMNS = [
    'date', 'symbol', 'direction', 'quantity',
    'expected_price', 'fill_price', 'slippage_dollars'
]


class SlippageLogger:
    def __init__(self):
        self.slippage = []
        self.daily_slippage = 0.0
        self.last_slippage_date = None

    def log(self, date, symbol, direction, quantity, expected_price, fill_price):
        slippage_dollars = (fill_price - expected_price) * quantity

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

    def reset_daily(self, current_date):
        """Reset daily accumulator if new day."""
        if self.last_slippage_date != current_date:
            self.daily_slippage = 0.0
            self.last_slippage_date = current_date

    def save(self, algorithm):
        if self.slippage:
            csv_content = build_csv(self.slippage, SLIPPAGE_COLUMNS)
            algorithm.ObjectStore.Save("wolfpack/slippage.csv", csv_content)
        return len(self.slippage)
