"""Order lifecycle event logging."""
from core.formatting import build_csv


ORDER_EVENT_COLUMNS = [
    'date', 'order_id', 'symbol', 'status', 'direction',
    'quantity', 'fill_quantity', 'fill_price',
    'order_type', 'limit_price', 'market_price_at_submit', 'tag'
]


class OrderEventLogger:
    def __init__(self):
        self.order_events = []

    def log(self, date, order_id, symbol, status, direction, quantity,
            fill_quantity, fill_price, order_type, limit_price=None,
            market_price_at_submit=None, tag=""):
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
            'market_price_at_submit': round(market_price_at_submit, 4) if market_price_at_submit is not None else '',
            'tag': tag
        })

    def save(self, algorithm):
        if self.order_events:
            csv_content = build_csv(self.order_events, ORDER_EVENT_COLUMNS)
            algorithm.ObjectStore.Save("wolfpack/order_events.csv", csv_content)
        return len(self.order_events)
