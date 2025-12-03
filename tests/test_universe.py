import logging
import unittest
from unittest.mock import MagicMock, patch

from config.settings import SYMBOLS, SYMBOL_TO_COIN
from config import (
    get_effective_symbol_universe,
    get_effective_coin_universe,
    set_symbol_universe,
    clear_symbol_universe_override,
)
from config.universe import validate_symbol_for_universe


class SymbolUniverseTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_symbol_universe_override()

    def test_default_universe_matches_settings(self) -> None:
        clear_symbol_universe_override()
        self.assertEqual(get_effective_symbol_universe(), list(SYMBOLS))

        expected_coins = []
        seen = set()
        for symbol in SYMBOLS:
            coin = SYMBOL_TO_COIN[symbol]
            if coin in seen:
                continue
            seen.add(coin)
            expected_coins.append(coin)
        self.assertEqual(get_effective_coin_universe(), expected_coins)

    def test_set_symbol_universe_filters_unknown_and_duplicates(self) -> None:
        symbols = ["ethusdt", "ETHUSDT", "UNKNOWNUSDT"]
        set_symbol_universe(symbols)
        universe = get_effective_symbol_universe()
        # 现在 Universe 允许任意 symbol，去重但不过滤 unknown
        self.assertEqual(universe, ["ETHUSDT", "UNKNOWNUSDT"])

        coins = get_effective_coin_universe()
        # ETHUSDT 通过 SYMBOL_TO_COIN 明确映射，UNKNOWNUSDT 会按 USDT 规则被推导为 UNKNOWN
        self.assertIn(SYMBOL_TO_COIN["ETHUSDT"], coins)

    def test_clear_symbol_universe_override_restores_default(self) -> None:
        set_symbol_universe(["ETHUSDT"])
        self.assertNotEqual(get_effective_symbol_universe(), list(SYMBOLS))
        clear_symbol_universe_override()
        self.assertEqual(get_effective_symbol_universe(), list(SYMBOLS))

    def test_empty_override_results_in_empty_universe(self) -> None:
        """Setting an empty list should result in empty Universe (no trading).
        
        This is intentional safety behavior: an empty or all-invalid override
        should NOT silently fall back to the full default Universe, as that
        could unexpectedly expand trading scope on misconfiguration.
        """
        # Explicit empty list => empty Universe
        set_symbol_universe([])
        self.assertEqual(get_effective_symbol_universe(), [])
        self.assertEqual(get_effective_coin_universe(), [])

        # All-invalid symbols 以前会被视作「unknown 且被过滤」得到空 Universe，
        # 现在允许任何 symbol，因此 Universe 会直接反映用户输入
        set_symbol_universe(["INVALIDUSDT", "ALSOINVALID"])
        self.assertEqual(get_effective_symbol_universe(), ["INVALIDUSDT", "ALSOINVALID"])
        # INVALIDUSDT 会被推导为 coin "INVALID"，ALSOINVALID 没有后缀推导则被忽略
        coins = get_effective_coin_universe()
        self.assertIn("INVALID", coins)

        # Use clear_symbol_universe_override() to explicitly restore default
        clear_symbol_universe_override()
        self.assertEqual(get_effective_symbol_universe(), list(SYMBOLS))


class UniverseIntegrationContractTests(unittest.TestCase):
    """Contract tests verifying Universe abstraction integration points.
    
    These tests ensure that modules using the Universe abstraction
    correctly respect the configured Universe subset.
    """

    def tearDown(self) -> None:
        clear_symbol_universe_override()

    def test_universe_override_affects_effective_universe(self) -> None:
        """Verify Universe override correctly limits the effective symbol set.
        
        This is a contract test ensuring that when Universe is overridden,
        any code using get_effective_symbol_universe() will only see the
        overridden subset, not the full default SYMBOLS list.
        """
        # Default should have multiple symbols
        default_symbols = get_effective_symbol_universe()
        self.assertGreater(len(default_symbols), 1, "Default should have multiple symbols")

        # Override to single symbol
        set_symbol_universe(["ETHUSDT"])
        
        # Now effective universe should only contain ETHUSDT
        overridden_symbols = get_effective_symbol_universe()
        self.assertEqual(overridden_symbols, ["ETHUSDT"])
        self.assertEqual(len(overridden_symbols), 1)

        # Coin universe should also be limited
        overridden_coins = get_effective_coin_universe()
        self.assertEqual(len(overridden_coins), 1)
        self.assertEqual(overridden_coins[0], SYMBOL_TO_COIN["ETHUSDT"])

    def test_orphaned_position_warning_logged(self) -> None:
        """Verify WARNING is logged when positions exist outside Universe."""
        from execution.executor import TradeExecutor

        # Create executor with a position for "DOGE" which won't be in Universe
        mock_positions = {"DOGE": {"entry_price": 0.1, "size": 100}}
        
        executor = TradeExecutor(
            positions=mock_positions,
            get_balance=lambda: 10000.0,
            set_balance=lambda x: None,
            get_current_time=MagicMock(),
            calculate_unrealized_pnl=lambda c, p: 0.0,
            estimate_exit_fee=lambda pos, price: 0.0,
            record_iteration_message=lambda msg: None,
            log_trade=lambda coin, action, data: None,
            log_ai_decision=lambda coin, signal, reason, conf: None,
            save_state=lambda: None,
            send_telegram_message=MagicMock(),
            escape_markdown=lambda s: s,
            fetch_market_data=lambda s: None,
            hyperliquid_trader=MagicMock(is_live=False),
            get_binance_futures_exchange=lambda: None,
            trading_backend="paper",
            binance_futures_live=False,
            backpack_futures_live=False,
        )

        # Set Universe to only include ETH (DOGE is orphaned)
        set_symbol_universe(["ETHUSDT"])

        with self.assertLogs(level=logging.WARNING) as log_context:
            executor.process_ai_decisions({"ETH": {"signal": "hold"}})
        
        # Verify warning about orphaned position was logged
        warning_messages = [r.message for r in log_context.records]
        self.assertTrue(
            any("DOGE" in msg and "outside current Universe" in msg for msg in warning_messages),
            f"Expected orphaned position warning for DOGE, got: {warning_messages}",
        )


class ValidateSymbolBackendAwareTests(unittest.TestCase):
    """Tests for backend-aware symbol validation (Story 9.3).
    
    These tests verify that validate_symbol_for_universe correctly
    dispatches to backend-specific validation logic based on
    MARKET_DATA_BACKEND configuration.
    
    Note: Backend-specific validation tests have been moved to
    tests/test_symbol_validation.py as part of the architecture refactor.
    """

    def test_static_validation_rejects_unknown_symbol(self) -> None:
        """Unknown symbols should be rejected by backend-aware validation."""
        is_valid, error = validate_symbol_for_universe("UNKNOWNUSDT")
        self.assertFalse(is_valid)
        # 现在不再依赖 SYMBOL_TO_COIN 白名单，而是直接委托 backend，错误信息中应包含 backend 标记
        self.assertIn("backend:", error)

    def test_static_validation_rejects_empty_symbol(self) -> None:
        """Static validation should reject empty symbols."""
        is_valid, error = validate_symbol_for_universe("")
        self.assertFalse(is_valid)
        self.assertIn("为空或无效", error)

    @patch("config.universe.get_effective_market_data_backend")
    @patch("exchange.symbol_validation.validate_symbol_for_backend")
    def test_binance_backend_dispatches_to_exchange_layer(
        self, mock_validate_backend, mock_get_backend
    ) -> None:
        """When backend is binance, should dispatch to exchange layer."""
        mock_get_backend.return_value = "binance"
        mock_validate_backend.return_value = (True, "")
        
        is_valid, error = validate_symbol_for_universe("BTCUSDT")
        
        self.assertTrue(is_valid)
        self.assertEqual(error, "")
        mock_validate_backend.assert_called_once_with("BTCUSDT", "binance")

    @patch("config.universe.get_effective_market_data_backend")
    @patch("exchange.symbol_validation.validate_symbol_for_backend")
    def test_backpack_backend_dispatches_to_exchange_layer(
        self, mock_validate_backend, mock_get_backend
    ) -> None:
        """When backend is backpack, should dispatch to exchange layer."""
        mock_get_backend.return_value = "backpack"
        mock_validate_backend.return_value = (True, "")
        
        is_valid, error = validate_symbol_for_universe("BTCUSDT")
        
        self.assertTrue(is_valid)
        self.assertEqual(error, "")
        mock_validate_backend.assert_called_once_with("BTCUSDT", "backpack")

    @patch("config.universe.get_effective_market_data_backend")
    @patch("exchange.symbol_validation.validate_symbol_for_backend")
    def test_unknown_backend_returns_error_with_todo(
        self, mock_validate_backend, mock_get_backend
    ) -> None:
        """Unknown backend should return error with TODO hint from exchange layer."""
        mock_get_backend.return_value = "unknown_backend"
        mock_validate_backend.return_value = (
            False, 
            "Symbol 'BTCUSDT' 无法校验: 未知的 backend 'unknown_backend' (TODO: 需要为此 backend 添加校验支持)"
        )
        
        is_valid, error = validate_symbol_for_universe("BTCUSDT")
        
        self.assertFalse(is_valid)
        self.assertIn("unknown_backend", error)
        self.assertIn("TODO", error)


class ValidateSymbolIntegrationTests(unittest.TestCase):
    """Integration tests for validate_symbol_for_universe with runtime overrides.
    
    These tests verify the full integration path including runtime override
    support for MARKET_DATA_BACKEND.
    """

    def test_validate_with_binance_runtime_override(self) -> None:
        """Validation should respect MARKET_DATA_BACKEND runtime override."""
        from config.runtime_overrides import set_runtime_override, clear_runtime_override
        
        try:
            set_runtime_override("MARKET_DATA_BACKEND", "binance")
            
            # Mock the exchange layer validation to avoid network calls
            with patch("exchange.symbol_validation.validate_symbol_for_backend") as mock_validate:
                mock_validate.return_value = (True, "")
                
                is_valid, error = validate_symbol_for_universe("BTCUSDT")
                
                self.assertTrue(is_valid)
                mock_validate.assert_called_once_with("BTCUSDT", "binance")
        finally:
            clear_runtime_override("MARKET_DATA_BACKEND")

    def test_validate_with_backpack_runtime_override(self) -> None:
        """Validation should respect MARKET_DATA_BACKEND runtime override."""
        from config.runtime_overrides import set_runtime_override, clear_runtime_override
        
        try:
            set_runtime_override("MARKET_DATA_BACKEND", "backpack")
            
            # Mock the exchange layer validation to avoid network calls
            with patch("exchange.symbol_validation.validate_symbol_for_backend") as mock_validate:
                mock_validate.return_value = (True, "")
                
                is_valid, error = validate_symbol_for_universe("BTCUSDT")
                
                self.assertTrue(is_valid)
                mock_validate.assert_called_once_with("BTCUSDT", "backpack")
        finally:
            clear_runtime_override("MARKET_DATA_BACKEND")
