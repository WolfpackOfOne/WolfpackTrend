"""Centralized strategy configuration defaults.

All strategy parameters are defined here for reference and documentation.
main.py remains the composition root that uses these values.
"""
from config import (
    ALPHA_SIGNAL_WEIGHTS,
    ALPHA_SIGNAL_TEMPERATURE,
    ALPHA_MIN_MAGNITUDE,
)

# --- Signal Generation (Alpha Model) ---
ALPHA = {
    'short_period': 20,
    'medium_period': 63,
    'long_period': 252,
    'atr_period': 14,
    'signal_weights': ALPHA_SIGNAL_WEIGHTS,  # short/medium/long
    'signal_temperature': ALPHA_SIGNAL_TEMPERATURE,
    'min_magnitude': ALPHA_MIN_MAGNITUDE,
    'rebalance_interval_trading_days': 5,
}

# --- Portfolio Construction ---
PORTFOLIO = {
    'target_vol_annual': 0.10,
    'max_gross': 1.50,
    'max_net': 0.50,
    'max_weight': 0.10,
    'vol_lookback': 63,
    'scaling_days': 5,
    'min_obs': 20,
}

# --- Execution ---
EXECUTION = {
    'strong_threshold': 0.70,
    'moderate_threshold': 0.30,
    'strong_offset_pct': 0.0,
    'moderate_offset_pct': 0.005,
    'weak_offset_pct': 0.015,
    'default_signal_strength': 0.50,
    'limit_cancel_after_open_checks': 2,
}

# --- Backtest ---
BACKTEST = {
    'start_date': '2022-01-01',
    'end_date': '2024-01-01',
    'starting_cash': 100_000,
    'warmup_days': 252,
    'benchmark': 'SPY',
}
