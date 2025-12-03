"""
Tests for exchange.symbol_validation module.

Story 9.3: 基于 MARKET_DATA_BACKEND 的 symbol 校验

This module tests the symbol validation service including:
- Client singleton reuse and caching behavior
- Error type classification (symbol not found vs network error)
- Contract tests ensuring no exceptions are raised
- Integration with BackpackMarketDataClient.symbol_exists()
"""
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from exchange.symbol_validation import (
    SymbolValidationService,
    ValidationErrorType,
    ValidationResult,
    get_validation_service,
    validate_symbol_for_backend,
)
from exchange.market_data import BackpackMarketDataClient


class TestValidationResult(unittest.TestCase):
    """Tests for ValidationResult dataclass."""

    def test_to_tuple_valid(self) -> None:
        """Valid result should convert to (True, '')."""
        result = ValidationResult(
            is_valid=True,
            error_type=ValidationErrorType.NONE,
            error_message="",
            backend="binance",
        )
        self.assertEqual(result.to_tuple(), (True, ""))

    def test_to_tuple_invalid(self) -> None:
        """Invalid result should convert to (False, error_message)."""
        result = ValidationResult(
            is_valid=False,
            error_type=ValidationErrorType.SYMBOL_NOT_FOUND,
            error_message="Symbol not found",
            backend="binance",
        )
        self.assertEqual(result.to_tuple(), (False, "Symbol not found"))


class TestSymbolValidationServiceCaching(unittest.TestCase):
    """Tests for caching behavior in SymbolValidationService."""

    def test_cache_hit_returns_cached_result(self) -> None:
        """Cached results should be returned without calling backend."""
        service = SymbolValidationService(cache_ttl=300.0)
        
        # Mock the Binance client
        with patch.object(service, '_get_binance_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_klines.return_value = [[1, 2, 3, 4, 5]]
            mock_get_client.return_value = mock_client
            
            # First call - should hit backend
            result1 = service.validate_symbol_binance("BTCUSDT")
            self.assertTrue(result1.is_valid)
            self.assertEqual(mock_client.get_klines.call_count, 1)
            
            # Second call - should use cache
            result2 = service.validate_symbol_binance("BTCUSDT")
            self.assertTrue(result2.is_valid)
            self.assertEqual(mock_client.get_klines.call_count, 1)  # Still 1

    def test_cache_miss_after_clear(self) -> None:
        """Clearing cache should cause next call to hit backend."""
        service = SymbolValidationService(cache_ttl=300.0)
        
        with patch.object(service, '_get_binance_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_klines.return_value = [[1, 2, 3, 4, 5]]
            mock_get_client.return_value = mock_client
            
            # First call
            service.validate_symbol_binance("BTCUSDT")
            self.assertEqual(mock_client.get_klines.call_count, 1)
            
            # Clear cache
            service.clear_cache()
            
            # Second call - should hit backend again
            service.validate_symbol_binance("BTCUSDT")
            self.assertEqual(mock_client.get_klines.call_count, 2)

    def test_network_errors_not_cached(self) -> None:
        """Network errors should not be cached."""
        service = SymbolValidationService(cache_ttl=300.0)
        
        with patch.object(service, '_get_binance_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_klines.side_effect = Exception("Connection timeout")
            mock_get_client.return_value = mock_client
            
            # First call - network error
            result1 = service.validate_symbol_binance("BTCUSDT")
            self.assertFalse(result1.is_valid)
            self.assertEqual(result1.error_type, ValidationErrorType.NETWORK_ERROR)
            
            # Second call - should hit backend again (not cached)
            result2 = service.validate_symbol_binance("BTCUSDT")
            self.assertEqual(mock_client.get_klines.call_count, 2)


class TestSymbolValidationServiceBinance(unittest.TestCase):
    """Tests for Binance validation in SymbolValidationService."""

    def test_valid_symbol_returns_success(self) -> None:
        """Valid symbol should return success result."""
        service = SymbolValidationService()
        
        with patch.object(service, '_get_binance_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_klines.return_value = [[1, 2, 3, 4, 5]]
            mock_get_client.return_value = mock_client
            
            result = service.validate_symbol_binance("BTCUSDT")
            
            self.assertTrue(result.is_valid)
            self.assertEqual(result.error_type, ValidationErrorType.NONE)
            self.assertEqual(result.backend, "binance")

    def test_invalid_symbol_returns_not_found(self) -> None:
        """Invalid symbol error should return SYMBOL_NOT_FOUND."""
        service = SymbolValidationService()
        
        with patch.object(service, '_get_binance_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_klines.side_effect = Exception("Invalid symbol")
            mock_get_client.return_value = mock_client
            
            result = service.validate_symbol_binance("INVALIDUSDT")
            
            self.assertFalse(result.is_valid)
            self.assertEqual(result.error_type, ValidationErrorType.SYMBOL_NOT_FOUND)
            self.assertIn("backend: binance", result.error_message)

    def test_network_error_returns_network_error_type(self) -> None:
        """Network errors should return NETWORK_ERROR type."""
        service = SymbolValidationService()
        
        with patch.object(service, '_get_binance_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_klines.side_effect = Exception("Connection timeout")
            mock_get_client.return_value = mock_client
            
            result = service.validate_symbol_binance("BTCUSDT")
            
            self.assertFalse(result.is_valid)
            self.assertEqual(result.error_type, ValidationErrorType.NETWORK_ERROR)
            self.assertIn("网络错误", result.error_message)


class TestSymbolValidationServiceBackpack(unittest.TestCase):
    """Tests for Backpack validation in SymbolValidationService."""

    def test_valid_symbol_returns_success(self) -> None:
        """Valid symbol should return success result."""
        service = SymbolValidationService()
        
        with patch.object(service, '_get_backpack_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.symbol_exists.return_value = (True, "BTC_USDC_PERP", None)
            mock_get_client.return_value = mock_client
            
            result = service.validate_symbol_backpack("BTCUSDT")
            
            self.assertTrue(result.is_valid)
            self.assertEqual(result.error_type, ValidationErrorType.NONE)
            self.assertEqual(result.backend, "backpack")

    def test_symbol_not_found_returns_not_found(self) -> None:
        """Symbol not found should return SYMBOL_NOT_FOUND."""
        service = SymbolValidationService()
        
        with patch.object(service, '_get_backpack_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.symbol_exists.return_value = (False, "INVALID_USDC_PERP", None)
            mock_get_client.return_value = mock_client
            
            result = service.validate_symbol_backpack("INVALIDUSDT")
            
            self.assertFalse(result.is_valid)
            self.assertEqual(result.error_type, ValidationErrorType.SYMBOL_NOT_FOUND)
            self.assertIn("backend: backpack", result.error_message)

    def test_network_error_returns_network_error_type(self) -> None:
        """Network errors should return NETWORK_ERROR type."""
        service = SymbolValidationService()
        
        with patch.object(service, '_get_backpack_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.symbol_exists.return_value = (False, "BTC_USDC_PERP", "Network timeout: connection refused")
            mock_get_client.return_value = mock_client
            
            result = service.validate_symbol_backpack("BTCUSDT")
            
            self.assertFalse(result.is_valid)
            self.assertEqual(result.error_type, ValidationErrorType.NETWORK_ERROR)
            self.assertIn("网络错误", result.error_message)

    def test_api_error_returns_api_error_type(self) -> None:
        """Non-network backend errors should return API_ERROR type and not be cached."""
        service = SymbolValidationService()
        
        with patch.object(service, '_get_backpack_client') as mock_get_client:
            mock_client = MagicMock()
            # Simulate HTTP 500 or JSON parse error propagated via error_info
            mock_client.symbol_exists.return_value = (False, "BTC_USDC_PERP", "HTTP 500: Internal Server Error")
            mock_get_client.return_value = mock_client
            
            result = service.validate_symbol_backpack("BTCUSDT")
            
            self.assertFalse(result.is_valid)
            self.assertEqual(result.error_type, ValidationErrorType.API_ERROR)
            self.assertIn("HTTP 500", result.error_message)


class TestSymbolValidationServiceUnknownBackend(unittest.TestCase):
    """Tests for unknown backend handling."""

    def test_unknown_backend_returns_error(self) -> None:
        """Unknown backend should return UNKNOWN_BACKEND error."""
        service = SymbolValidationService()
        
        result = service.validate_symbol("BTCUSDT", "unknown_backend")
        
        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_type, ValidationErrorType.UNKNOWN_BACKEND)
        self.assertIn("TODO", result.error_message)
        self.assertIn("unknown_backend", result.error_message)


class TestValidateSymbolForBackendFunction(unittest.TestCase):
    """Tests for the module-level validate_symbol_for_backend function."""

    @patch('exchange.symbol_validation.get_validation_service')
    def test_delegates_to_service(self, mock_get_service) -> None:
        """Function should delegate to singleton service."""
        mock_service = MagicMock()
        mock_service.validate_symbol.return_value = ValidationResult(
            is_valid=True,
            error_type=ValidationErrorType.NONE,
            error_message="",
            backend="binance",
        )
        mock_get_service.return_value = mock_service
        
        result = validate_symbol_for_backend("BTCUSDT", "binance")
        
        self.assertEqual(result, (True, ""))
        mock_service.validate_symbol.assert_called_once_with("BTCUSDT", "binance")


class TestBackpackMarketDataClientSymbolExists(unittest.TestCase):
    """Tests for BackpackMarketDataClient.symbol_exists() public method."""

    @patch('exchange.market_data.requests.Session')
    def test_symbol_exists_success(self, mock_session_class) -> None:
        """Successful symbol check should return (True, normalized, None)."""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"symbol": "BTC_USDC_PERP", "markPrice": "50000"}
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        client = BackpackMarketDataClient("https://api.backpack.exchange")
        exists, normalized, error = client.symbol_exists("BTCUSDT")
        
        self.assertTrue(exists)
        self.assertEqual(normalized, "BTC_USDC_PERP")
        self.assertIsNone(error)

    @patch('exchange.market_data.requests.Session')
    def test_symbol_not_found(self, mock_session_class) -> None:
        """Symbol not found should return (False, normalized, None)."""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []  # Empty list = not found
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        client = BackpackMarketDataClient("https://api.backpack.exchange")
        exists, normalized, error = client.symbol_exists("INVALIDUSDT")
        
        self.assertFalse(exists)
        self.assertEqual(normalized, "INVALID_USDC_PERP")
        self.assertIsNone(error)  # No error, just not found

    @patch('exchange.market_data.requests.Session')
    def test_network_timeout_returns_error(self, mock_session_class) -> None:
        """Network timeout should return error info."""
        import requests.exceptions
        
        mock_session = MagicMock()
        mock_session.get.side_effect = requests.exceptions.Timeout("Connection timed out")
        mock_session_class.return_value = mock_session
        
        client = BackpackMarketDataClient("https://api.backpack.exchange")
        exists, normalized, error = client.symbol_exists("BTCUSDT")
        
        self.assertFalse(exists)
        self.assertIsNotNone(error)
        self.assertIn("timeout", error.lower())

    @patch('exchange.market_data.requests.Session')
    def test_http_error_returns_error(self, mock_session_class) -> None:
        """HTTP error should return error info."""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        client = BackpackMarketDataClient("https://api.backpack.exchange")
        exists, normalized, error = client.symbol_exists("BTCUSDT")
        
        self.assertFalse(exists)
        self.assertIsNotNone(error)
        self.assertIn("500", error)


# ═══════════════════════════════════════════════════════════════════
# Contract Tests (Issue #6): Ensure no exceptions are raised
# ═══════════════════════════════════════════════════════════════════


class TestSymbolValidationContractNeverRaises(unittest.TestCase):
    """
    Contract tests ensuring symbol validation NEVER raises exceptions.
    
    These tests verify the contract that validate_symbol_for_backend()
    and related functions always return (is_valid, error_message) tuples
    instead of raising exceptions, regardless of the error type.
    
    This is critical for AC6 compliance: callers should not need try/except.
    """

    def test_binance_invalid_symbol_never_raises(self) -> None:
        """Binance invalid symbol should return tuple, not raise."""
        service = SymbolValidationService()
        
        with patch.object(service, '_get_binance_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_klines.side_effect = Exception("Invalid symbol FOOBAR")
            mock_get_client.return_value = mock_client
            
            # Should NOT raise, should return tuple
            result = service.validate_symbol_binance("FOOBAR")
            self.assertIsInstance(result, ValidationResult)
            self.assertFalse(result.is_valid)

    def test_binance_network_error_never_raises(self) -> None:
        """Binance network error should return tuple, not raise."""
        service = SymbolValidationService()
        
        with patch.object(service, '_get_binance_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_klines.side_effect = Exception("Connection refused")
            mock_get_client.return_value = mock_client
            
            result = service.validate_symbol_binance("BTCUSDT")
            self.assertIsInstance(result, ValidationResult)
            self.assertFalse(result.is_valid)

    def test_binance_timeout_never_raises(self) -> None:
        """Binance timeout should return tuple, not raise."""
        service = SymbolValidationService()
        
        with patch.object(service, '_get_binance_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_klines.side_effect = Exception("Read timed out")
            mock_get_client.return_value = mock_client
            
            result = service.validate_symbol_binance("BTCUSDT")
            self.assertIsInstance(result, ValidationResult)
            self.assertFalse(result.is_valid)

    def test_backpack_network_error_never_raises(self) -> None:
        """Backpack network error should return tuple, not raise."""
        service = SymbolValidationService()
        
        with patch.object(service, '_get_backpack_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.symbol_exists.return_value = (False, "BTC_USDC_PERP", "Network error")
            mock_get_client.return_value = mock_client
            
            result = service.validate_symbol_backpack("BTCUSDT")
            self.assertIsInstance(result, ValidationResult)
            self.assertFalse(result.is_valid)

    def test_backpack_unexpected_exception_never_raises(self) -> None:
        """Backpack unexpected exception should return tuple, not raise."""
        service = SymbolValidationService()
        
        with patch.object(service, '_get_backpack_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.symbol_exists.side_effect = RuntimeError("Unexpected error")
            mock_get_client.return_value = mock_client
            
            result = service.validate_symbol_backpack("BTCUSDT")
            self.assertIsInstance(result, ValidationResult)
            self.assertFalse(result.is_valid)
            self.assertEqual(result.error_type, ValidationErrorType.API_ERROR)

    def test_unknown_backend_never_raises(self) -> None:
        """Unknown backend should return tuple, not raise."""
        service = SymbolValidationService()
        
        result = service.validate_symbol("BTCUSDT", "nonexistent_backend")
        self.assertIsInstance(result, ValidationResult)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_type, ValidationErrorType.UNKNOWN_BACKEND)

    def test_validate_symbol_for_backend_never_raises(self) -> None:
        """Module-level function should never raise for any input."""
        # Test with mocked service to avoid real network calls
        with patch('exchange.symbol_validation.get_validation_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.validate_symbol.side_effect = RuntimeError("Service crashed")
            mock_get_service.return_value = mock_service
            
            # Function should NOT raise even if the underlying service crashes
            result = validate_symbol_for_backend("BTCUSDT", "binance")
            self.assertIsInstance(result, tuple)
            is_valid, error = result
            self.assertFalse(is_valid)
            self.assertIn("internal error", error)


class TestSymbolValidationClientSingleton(unittest.TestCase):
    """Tests for client singleton behavior."""

    def test_binance_client_reused(self) -> None:
        """Binance client should be created once and reused."""
        service = SymbolValidationService()
        
        with patch('exchange.symbol_validation.Client') as mock_client_class:
            with patch('exchange.symbol_validation.BinanceMarketDataClient') as mock_md_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                
                mock_md = MagicMock()
                mock_md.get_klines.return_value = [[1, 2, 3]]
                mock_md_class.return_value = mock_md
                
                # Clear any cached client
                service._binance_client = None
                
                # First call
                service._get_binance_client()
                self.assertEqual(mock_client_class.call_count, 1)
                
                # Second call - should reuse
                service._get_binance_client()
                self.assertEqual(mock_client_class.call_count, 1)

    def test_backpack_client_reused(self) -> None:
        """Backpack client should be created once and reused."""
        service = SymbolValidationService()
        
        with patch('exchange.symbol_validation.BackpackMarketDataClient') as mock_class:
            mock_client = MagicMock()
            mock_class.return_value = mock_client
            
            # Clear any cached client
            service._backpack_client = None
            
            # First call
            service._get_backpack_client()
            self.assertEqual(mock_class.call_count, 1)
            
            # Second call - should reuse
            service._get_backpack_client()
            self.assertEqual(mock_class.call_count, 1)


if __name__ == "__main__":
    unittest.main()
