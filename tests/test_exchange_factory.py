"""Tests for exchange/factory.py module."""
from unittest.mock import MagicMock, patch
import pytest

from exchange.factory import (
    get_exchange_client,
    reset_clients,
)
from exchange.base import ExchangeClient
from exchange.hyperliquid import HyperliquidExchangeClient
from exchange.binance import BinanceFuturesExchangeClient
from exchange.backpack import BackpackFuturesExchangeClient


class TestGetExchangeClient:
    """Tests for get_exchange_client function."""

    def test_creates_hyperliquid_client(self):
        """Should create HyperliquidExchangeClient."""
        mock_trader = MagicMock()
        
        client = get_exchange_client("hyperliquid", trader=mock_trader)
        
        assert isinstance(client, HyperliquidExchangeClient)

    def test_hyperliquid_requires_trader(self):
        """Should raise if trader not provided for Hyperliquid."""
        with pytest.raises(ValueError, match="trader"):
            get_exchange_client("hyperliquid")

    def test_creates_binance_futures_client(self):
        """Should create BinanceFuturesExchangeClient."""
        mock_exchange = MagicMock()
        
        client = get_exchange_client("binance_futures", exchange=mock_exchange)
        
        assert isinstance(client, BinanceFuturesExchangeClient)

    def test_binance_futures_requires_exchange(self):
        """Should raise if exchange not provided for Binance."""
        with pytest.raises(ValueError, match="exchange"):
            get_exchange_client("binance_futures")

    def test_creates_backpack_futures_client(self):
        """Should create BackpackFuturesExchangeClient."""
        # Backpack requires a valid base64-encoded ED25519 seed
        # Use a valid test seed (32 bytes base64 encoded)
        import base64
        test_seed = base64.b64encode(b'0' * 32).decode()
        
        client = get_exchange_client(
            "backpack_futures",
            api_public_key="test_key",
            api_secret_seed=test_seed,
        )
        
        assert isinstance(client, BackpackFuturesExchangeClient)

    def test_backpack_futures_requires_keys(self):
        """Should raise if API keys not provided for Backpack."""
        with pytest.raises(ValueError, match="api_public_key"):
            get_exchange_client("backpack_futures")
        
        with pytest.raises(ValueError, match="api_secret_seed"):
            get_exchange_client("backpack_futures", api_public_key="key")

    def test_backpack_uses_default_base_url(self):
        """Should use default base URL for Backpack."""
        import base64
        test_seed = base64.b64encode(b'0' * 32).decode()
        
        client = get_exchange_client(
            "backpack_futures",
            api_public_key="test_key",
            api_secret_seed=test_seed,
        )
        
        assert client._base_url == "https://api.backpack.exchange"

    def test_backpack_accepts_custom_base_url(self):
        """Should accept custom base URL for Backpack."""
        import base64
        test_seed = base64.b64encode(b'0' * 32).decode()
        
        client = get_exchange_client(
            "backpack_futures",
            api_public_key="test_key",
            api_secret_seed=test_seed,
            base_url="https://custom.api.com",
        )
        
        assert client._base_url == "https://custom.api.com"

    def test_raises_for_unknown_backend(self):
        """Should raise NotImplementedError for unknown backend."""
        with pytest.raises(NotImplementedError):
            get_exchange_client("unknown_backend")

    def test_normalizes_backend_name(self):
        """Should normalize backend name (case insensitive, strip whitespace)."""
        mock_trader = MagicMock()
        
        client = get_exchange_client("  HYPERLIQUID  ", trader=mock_trader)
        
        assert isinstance(client, HyperliquidExchangeClient)

    def test_handles_empty_backend(self):
        """Should raise for empty backend."""
        with pytest.raises(NotImplementedError):
            get_exchange_client("")


class TestResetClients:
    """Tests for reset_clients function."""

    def test_resets_cached_clients(self):
        """Should reset all cached clients."""
        # This should not raise
        reset_clients()
        
        # After reset, getting clients should require re-initialization
        # (tested implicitly by not raising)


class TestExchangeClientProtocol:
    """Tests for ExchangeClient protocol compliance."""

    def test_hyperliquid_implements_protocol(self):
        """HyperliquidExchangeClient should implement ExchangeClient."""
        mock_trader = MagicMock()
        client = HyperliquidExchangeClient(mock_trader)
        
        assert isinstance(client, ExchangeClient)
        assert hasattr(client, "place_entry")
        assert hasattr(client, "close_position")

    def test_binance_implements_protocol(self):
        """BinanceFuturesExchangeClient should implement ExchangeClient."""
        mock_exchange = MagicMock()
        client = BinanceFuturesExchangeClient(mock_exchange)
        
        assert isinstance(client, ExchangeClient)
        assert hasattr(client, "place_entry")
        assert hasattr(client, "close_position")

    def test_backpack_implements_protocol(self):
        """BackpackFuturesExchangeClient should implement ExchangeClient."""
        import base64
        test_seed = base64.b64encode(b'0' * 32).decode()
        
        client = BackpackFuturesExchangeClient(
            api_public_key="test",
            api_secret_seed=test_seed,
        )
        
        assert isinstance(client, ExchangeClient)
        assert hasattr(client, "place_entry")
        assert hasattr(client, "close_position")
