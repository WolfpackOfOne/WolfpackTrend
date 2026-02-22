"""Trend signal computation molecule.

Pure signal logic extracted from alpha model.
"""
from core.math_utils import compute_composite_signal


def compute_trend_signals(symbols_data, weights, temperature, min_magnitude):
    """
    Compute trend signals for all symbols with ready indicators.

    Args:
        symbols_data: list of dicts with keys:
            symbol, price, sma_short, sma_medium, sma_long, atr
        weights: tuple of (weight_short, weight_medium, weight_long)
        temperature: signal temperature divisor
        min_magnitude: minimum signal magnitude

    Returns:
        dict: symbol -> magnitude (positive=Up, negative=Down)
    """
    signals = {}
    for sd in symbols_data:
        mag = compute_composite_signal(
            sd['price'], sd['sma_short'], sd['sma_medium'], sd['sma_long'],
            sd['atr'], weights, temperature, min_magnitude
        )
        if mag is not None:
            signals[sd['symbol']] = mag
    return signals
