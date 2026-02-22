"""Pure math and deterministic decision helpers.

Rules:
- No self
- No algorithm references
- No QuantConnect runtime objects
- Plain inputs and plain outputs only
"""
import math


def build_scaling_schedule(scaling_days, front_load_factor):
    """
    Generate a cumulative scaling schedule of length scaling_days.

    front_load_factor controls how front-loaded the schedule is:
      - 1.0 = even spread (linear: 1/N, 2/N, ..., 1.0)
      - >1.0 = front-loaded (power curve, reaches target faster early on)

    The last element is always 1.0 (reach 100% on final day).
    """
    n = max(1, int(scaling_days))
    if n <= 1:
        return [1.0]

    exponent = 1.0 / front_load_factor
    schedule = []
    for i in range(1, n + 1):
        fraction = (i / n) ** exponent
        schedule.append(round(fraction, 4))
    schedule[-1] = 1.0
    return schedule


def estimate_portfolio_vol(weights, rolling_returns_lists, min_obs):
    """
    Estimate annualized portfolio volatility using diagonal approximation.

    Args:
        weights: dict of symbol -> weight
        rolling_returns_lists: dict of symbol -> list of daily returns
        min_obs: minimum number of observations required

    Returns:
        float or None if insufficient data.
    """
    daily_variances = {}

    for symbol in weights.keys():
        if symbol not in rolling_returns_lists:
            continue
        returns = rolling_returns_lists[symbol]
        if len(returns) < min_obs:
            continue

        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
        daily_variances[symbol] = variance

    symbols_with_weight = [s for s, w in weights.items() if abs(w) > 1e-8]
    if not all(s in daily_variances for s in symbols_with_weight):
        return None

    port_var = sum(weights[s] ** 2 * daily_variances[s] for s in symbols_with_weight)
    vol_annual = math.sqrt(port_var) * math.sqrt(252)
    return vol_annual


def apply_per_name_cap(weights, max_weight):
    """Clip each weight to [-max_weight, +max_weight]."""
    return {s: max(-max_weight, min(max_weight, w)) for s, w in weights.items()}


def apply_gross_cap(weights, max_gross):
    """If gross exposure exceeds max_gross, scale down proportionally."""
    gross = sum(abs(w) for w in weights.values())
    if gross > max_gross:
        scale = max_gross / gross
        weights = {s: w * scale for s, w in weights.items()}
    return weights


def apply_net_cap(weights, max_net):
    """If abs(net exposure) exceeds max_net, scale down proportionally."""
    net = sum(weights.values())
    if abs(net) > max_net:
        scale = max_net / abs(net)
        weights = {s: w * scale for s, w in weights.items()}
    return weights


def compute_limit_price(price, quantity, offset_pct, tick_size):
    """
    Compute limit price with offset, rounded to tick size.

    Args:
        price: current market price
        quantity: order quantity (positive=buy, negative=sell)
        offset_pct: limit offset as decimal (e.g., 0.005 for 0.5%)
        tick_size: minimum price variation (0 means round to 2 decimals)

    Returns:
        float: limit price
    """
    if quantity > 0:
        raw_price = price * (1 - offset_pct)
    else:
        raw_price = price * (1 + offset_pct)

    if tick_size > 0:
        return round(raw_price / tick_size) * tick_size
    return round(raw_price, 2)


def compute_composite_signal(price, sma_short, sma_medium, sma_long, atr_value,
                              weights, temperature, min_magnitude):
    """
    Compute composite trend signal from SMA distances normalized by ATR.

    Args:
        price: current close price
        sma_short: short-period SMA value
        sma_medium: medium-period SMA value
        sma_long: long-period SMA value
        atr_value: ATR value (clamped to min 1e-8)
        weights: tuple of (weight_short, weight_medium, weight_long)
        temperature: divisor before tanh (controls signal sensitivity)
        min_magnitude: minimum abs(magnitude) to produce a signal

    Returns:
        float or None: signal magnitude (positive=Up, negative=Down), or None if
                       signals don't agree in direction or magnitude too small.
    """
    atr_clamped = max(atr_value, 1e-8)

    dist_short = (price - sma_short) / atr_clamped
    dist_medium = (price - sma_medium) / atr_clamped
    dist_long = (price - sma_long) / atr_clamped

    all_positive = (dist_short > 0 and dist_medium > 0 and dist_long > 0)
    all_negative = (dist_short < 0 and dist_medium < 0 and dist_long < 0)
    if not (all_positive or all_negative):
        return None

    w_short, w_medium, w_long = weights
    score = w_short * dist_short + w_medium * dist_medium + w_long * dist_long

    mag = math.tanh(score / temperature)

    if abs(mag) < min_magnitude:
        return None

    return mag
