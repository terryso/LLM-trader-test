"""
Trading metrics calculations.

COMPATIBILITY LAYER: This module re-exports from core.metrics.
Please import from core.metrics directly in new code.
"""
from core.metrics import (
    DEFAULT_RISK_FREE_RATE,
    calculate_sortino_ratio,
    calculate_pnl_for_price,
    calculate_unrealized_pnl_for_position,
    calculate_net_unrealized_pnl_for_position,
    estimate_exit_fee_for_position,
    calculate_total_margin_for_positions,
    format_leverage_display,
)

__all__ = [
    "DEFAULT_RISK_FREE_RATE",
    "calculate_sortino_ratio",
    "calculate_pnl_for_price",
    "calculate_unrealized_pnl_for_position",
    "calculate_net_unrealized_pnl_for_position",
    "estimate_exit_fee_for_position",
    "calculate_total_margin_for_positions",
    "format_leverage_display",
]
