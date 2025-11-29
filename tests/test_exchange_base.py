"""Tests for exchange/base.py module."""
import pytest

from exchange.base import EntryResult, CloseResult, ExchangeClient


class TestEntryResult:
    """Tests for EntryResult dataclass."""

    def test_creates_successful_result(self):
        """Should create a successful entry result."""
        result = EntryResult(
            success=True,
            backend="hyperliquid",
            errors=[],
            entry_oid=12345,
        )
        
        assert result.success is True
        assert result.backend == "hyperliquid"
        assert result.errors == []
        assert result.entry_oid == 12345

    def test_creates_failed_result(self):
        """Should create a failed entry result."""
        result = EntryResult(
            success=False,
            backend="binance_futures",
            errors=["Insufficient balance", "Order rejected"],
        )
        
        assert result.success is False
        assert result.backend == "binance_futures"
        assert len(result.errors) == 2

    def test_default_values(self):
        """Should have correct default values."""
        result = EntryResult(
            success=True,
            backend="test",
            errors=[],
        )
        
        assert result.entry_oid is None
        assert result.tp_oid is None
        assert result.sl_oid is None
        assert result.raw is None
        assert result.extra == {}

    def test_stores_order_ids(self):
        """Should store all order IDs."""
        result = EntryResult(
            success=True,
            backend="hyperliquid",
            errors=[],
            entry_oid=100,
            tp_oid=101,
            sl_oid=102,
        )
        
        assert result.entry_oid == 100
        assert result.tp_oid == 101
        assert result.sl_oid == 102

    def test_stores_raw_response(self):
        """Should store raw response data."""
        raw_data = {"order_id": 123, "status": "filled"}
        result = EntryResult(
            success=True,
            backend="test",
            errors=[],
            raw=raw_data,
        )
        
        assert result.raw == raw_data

    def test_stores_extra_data(self):
        """Should store extra metadata."""
        result = EntryResult(
            success=True,
            backend="test",
            errors=[],
            extra={"fill_price": 50000.0, "slippage": 0.01},
        )
        
        assert result.extra["fill_price"] == 50000.0
        assert result.extra["slippage"] == 0.01


class TestCloseResult:
    """Tests for CloseResult dataclass."""

    def test_creates_successful_result(self):
        """Should create a successful close result."""
        result = CloseResult(
            success=True,
            backend="hyperliquid",
            errors=[],
            close_oid=54321,
        )
        
        assert result.success is True
        assert result.backend == "hyperliquid"
        assert result.errors == []
        assert result.close_oid == 54321

    def test_creates_failed_result(self):
        """Should create a failed close result."""
        result = CloseResult(
            success=False,
            backend="binance_futures",
            errors=["Position not found"],
        )
        
        assert result.success is False
        assert len(result.errors) == 1

    def test_default_values(self):
        """Should have correct default values."""
        result = CloseResult(
            success=True,
            backend="test",
            errors=[],
        )
        
        assert result.close_oid is None
        assert result.raw is None
        assert result.extra == {}

    def test_stores_raw_response(self):
        """Should store raw response data."""
        raw_data = {"status": "closed", "pnl": 100.0}
        result = CloseResult(
            success=True,
            backend="test",
            errors=[],
            raw=raw_data,
        )
        
        assert result.raw == raw_data


class TestExchangeClientProtocol:
    """Tests for ExchangeClient protocol."""

    def test_protocol_is_runtime_checkable(self):
        """ExchangeClient should be runtime checkable."""
        # Create a mock class that implements the protocol
        class MockExchangeClient:
            def place_entry(self, coin, side, size, entry_price, stop_loss_price,
                          take_profit_price, leverage, liquidity, **kwargs):
                return EntryResult(success=True, backend="mock", errors=[])
            
            def close_position(self, coin, side, size=None, fallback_price=None, **kwargs):
                return CloseResult(success=True, backend="mock", errors=[])
        
        mock_client = MockExchangeClient()
        assert isinstance(mock_client, ExchangeClient)

    def test_non_conforming_class_fails_check(self):
        """Non-conforming class should fail isinstance check."""
        class NotAnExchangeClient:
            def some_other_method(self):
                pass
        
        not_client = NotAnExchangeClient()
        assert not isinstance(not_client, ExchangeClient)

    def test_partial_implementation_fails_check(self):
        """Partial implementation should fail isinstance check."""
        class PartialClient:
            def place_entry(self, coin, side, size, entry_price, stop_loss_price,
                          take_profit_price, leverage, liquidity, **kwargs):
                pass
            # Missing close_position
        
        partial = PartialClient()
        assert not isinstance(partial, ExchangeClient)
