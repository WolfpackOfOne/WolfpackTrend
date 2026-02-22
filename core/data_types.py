"""Typed dataclasses for internal data flow.

These are stubs for Phase 02. They will be adopted incrementally in Phase 13.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Signal:
    symbol: str
    direction: str  # "Up" or "Down"
    magnitude: float
    price: float
    sma_short: float
    sma_medium: float
    sma_long: float
    atr: float


@dataclass
class TargetState:
    week_id: str
    symbol: str
    start_w: float
    weekly_target_w: float
    scheduled_fraction: float
    scheduled_w: float
    actual_w: float
    scale_day: int


@dataclass
class OrderRecord:
    date: str
    order_id: int
    symbol: str
    status: str
    direction: str
    quantity: float
    fill_quantity: float
    fill_price: Optional[float]
    order_type: str
    limit_price: Optional[float] = None
    market_price_at_submit: Optional[float] = None
    tag: str = ""


@dataclass
class TradeRecord:
    date: str
    symbol: str
    action: str
    quantity: float
    avg_price: float
    exit_price: float
    realized_pnl: float


@dataclass
class PositionSnapshot:
    date: str
    symbol: str
    invested: int
    quantity: float
    price: float
    market_value: float
    weight: float
    unrealized_pnl: float
    daily_pnl: float
    daily_unrealized_pnl: float
    daily_realized_pnl: float
    daily_fees: float
    daily_dividends: float
    daily_total_net_pnl: float
    avg_price: float


@dataclass
class SlippageRecord:
    date: str
    symbol: str
    direction: str
    quantity: float
    expected_price: float
    fill_price: float
    slippage_dollars: float


@dataclass
class OrderEventRecord:
    date: str
    order_id: int
    symbol: str
    status: str
    direction: str
    quantity: float
    fill_quantity: float
    fill_price: Optional[float]
    order_type: str
    limit_price: Optional[float] = None
    market_price_at_submit: Optional[float] = None
    tag: str = ""
