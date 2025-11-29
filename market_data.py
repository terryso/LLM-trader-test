"""
Market data clients for different exchanges.

COMPATIBILITY LAYER: This module re-exports from exchange.market_data.
Please import from exchange.market_data directly in new code.
"""
from exchange.market_data import (
    BinanceMarketDataClient,
    BackpackMarketDataClient,
)

__all__ = [
    "BinanceMarketDataClient",
    "BackpackMarketDataClient",
]
