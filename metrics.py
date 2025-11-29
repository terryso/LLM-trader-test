from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

import numpy as np


# Annualized baseline for Sortino ratio calculations
DEFAULT_RISK_FREE_RATE: float = 0.0


def calculate_sortino_ratio(
    equity_values: Iterable[float],
    period_seconds: float,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
) -> Optional[float]:
    """Compute the annualized Sortino ratio from equity snapshots.

    Args:
        equity_values: Sequence of equity values in chronological order.
        period_seconds: Average period between snapshots (used to annualize).
        risk_free_rate: Annualized risk-free rate (decimal form).
    """
    values = [
        float(v)
        for v in equity_values
        if isinstance(v, (int, float, np.floating)) and np.isfinite(v)
    ]
    if len(values) < 2:
        return None

    returns = np.diff(values) / np.array(values[:-1], dtype=float)
    returns = returns[np.isfinite(returns)]
    if returns.size == 0:
        return None

    # Require a valid positive period; callers (bot/backtest) already pass
    # meaningful intervals, so this primarily guards against bad inputs.
    if not period_seconds or period_seconds <= 0:
        return None
    period_seconds = float(period_seconds)

    periods_per_year = (365 * 24 * 60 * 60) / period_seconds
    if not np.isfinite(periods_per_year) or periods_per_year <= 0:
        return None

    per_period_rf = risk_free_rate / periods_per_year
    excess_return = returns.mean() - per_period_rf
    if not np.isfinite(excess_return):
        return None

    downside_diff = np.minimum(returns - per_period_rf, 0.0)
    downside_squared = downside_diff ** 2
    downside_deviation = np.sqrt(np.mean(downside_squared))
    if downside_deviation <= 0 or not np.isfinite(downside_deviation):
        return None

    sortino = (excess_return / downside_deviation) * np.sqrt(periods_per_year)
    if not np.isfinite(sortino):
        return None
    return float(sortino)


def calculate_pnl_for_price(pos: Dict[str, Any], target_price: float) -> float:
    """Return gross PnL for a hypothetical exit price.

    This helper operates purely on the provided position mapping and target
    price, without depending on any global state.
    """
    try:
        quantity = float(pos.get("quantity", 0.0))
        entry_price = float(pos.get("entry_price", 0.0))
    except (TypeError, ValueError):
        return 0.0

    side = str(pos.get("side", "long")).lower()
    if side == "short":
        return (entry_price - target_price) * quantity
    return (target_price - entry_price) * quantity


def calculate_unrealized_pnl_for_position(
    pos: Dict[str, Any],
    current_price: float,
) -> float:
    """Calculate unrealized PnL for a single position at the given price."""
    return calculate_pnl_for_price(pos, current_price)


def calculate_net_unrealized_pnl_for_position(
    pos: Dict[str, Any],
    current_price: float,
) -> float:
    """Calculate unrealized PnL after subtracting fees already paid."""
    gross_pnl = calculate_unrealized_pnl_for_position(pos, current_price)
    try:
        fees_paid = float(pos.get("fees_paid", 0.0))
    except (TypeError, ValueError):
        fees_paid = 0.0
    return gross_pnl - fees_paid


def estimate_exit_fee_for_position(
    pos: Dict[str, Any],
    exit_price: float,
    default_fee_rate: float,
) -> float:
    """Estimate taker/maker fee required to exit the position.

    The caller is responsible for providing the default taker fee rate so that
    this helper remains independent from bot module globals.
    """
    try:
        quantity = float(pos.get("quantity", 0.0))
    except (TypeError, ValueError):
        quantity = 0.0

    fee_rate = pos.get("fee_rate", default_fee_rate)
    try:
        fee_rate_value = float(fee_rate)
    except (TypeError, ValueError):
        fee_rate_value = default_fee_rate

    estimated_fee = quantity * exit_price * fee_rate_value
    return max(estimated_fee, 0.0)


def calculate_total_margin_for_positions(
    positions: Iterable[Dict[str, Any]],
) -> float:
    """Return sum of margin allocated across the provided positions."""
    total = 0.0
    for pos in positions:
        try:
            total += float(pos.get("margin", 0.0))
        except (TypeError, ValueError):
            continue
    return total


def format_leverage_display(leverage: Any) -> str:
    if leverage is None:
        return "n/a"
    if isinstance(leverage, str):
        cleaned = leverage.strip()
        if not cleaned:
            return "n/a"
        if cleaned.lower().endswith("x"):
            return cleaned.lower()
        try:
            value = float(cleaned)
        except (TypeError, ValueError):
            return cleaned
    else:
        try:
            value = float(leverage)
        except (TypeError, ValueError):
            return str(leverage)
    if value.is_integer():
        return f"{int(value)}x"
    return f"{value:g}x"
