"""Exchange integration layer for trading operations."""
from exchange.base import EntryResult, CloseResult, ExchangeClient
from exchange.factory import (
    get_exchange_client,
    get_binance_client,
    get_binance_futures_exchange,
    get_hyperliquid_trader,
    get_market_data_client,
    set_market_data_client,
    reset_clients,
)
from exchange.market_data import (
    BinanceMarketDataClient,
    BackpackMarketDataClient,
)

__all__ = [
    # Base types
    "EntryResult",
    "CloseResult",
    "ExchangeClient",
    # Factory functions
    "get_exchange_client",
    "get_binance_client",
    "get_binance_futures_exchange",
    "get_hyperliquid_trader",
    "get_market_data_client",
    "set_market_data_client",
    "reset_clients",
    # Market data clients
    "BinanceMarketDataClient",
    "BackpackMarketDataClient",
]
