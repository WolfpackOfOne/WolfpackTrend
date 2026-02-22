"""Signal logging for alpha model."""
from core.formatting import build_csv


SIGNAL_COLUMNS = [
    'date', 'symbol', 'direction', 'magnitude', 'price',
    'sma_short', 'sma_medium', 'sma_long', 'atr'
]


class SignalLogger:
    def __init__(self, team_id="production"):
        self.team_id = team_id
        self.signals = []

    def log(self, date, symbol, direction, magnitude, price,
            sma_short, sma_medium, sma_long, atr):
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

    def save(self, algorithm):
        if self.signals:
            csv_content = build_csv(self.signals, SIGNAL_COLUMNS)
            algorithm.ObjectStore.Save(f"{self.team_id}/signals.csv", csv_content)
        return len(self.signals)
