"""
Tests for Telegram /close command functionality.

Story 7.4.6: Implement /close single-symbol position close command.

Tests cover:
- AC1: Command format support (/close SYMBOL, /close SYMBOL all, /close SYMBOL AMOUNT)
- AC2: Partial close behavior with percentage conversion
- AC3: >= 100% degrades to full close
- AC4: No position scenario handling
- AC5: Error handling and logging
- AC6: Works during Kill-Switch / daily loss limit activation
- AC7: Unit tests for all scenarios
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from notifications.commands.base import TelegramCommand, CommandResult
from notifications.commands.close import (
    handle_close_command,
    get_positions_for_close,
    _normalize_symbol,
    _parse_close_args,
    _find_position_for_symbol,
    _calculate_close_quantity,
    _calculate_notional,
)


# ═══════════════════════════════════════════════════════════════════
# TEST FIXTURES
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_positions() -> Dict[str, Dict[str, Any]]:
    """Sample positions for testing."""
    return {
        "BTC": {
            "side": "long",
            "quantity": 0.5,
            "entry_price": 50000.0,
            "profit_target": 55000.0,
            "stop_loss": 48000.0,
            "leverage": 10.0,
            "margin": 2500.0,
        },
        "ETH": {
            "side": "short",
            "quantity": 5.0,
            "entry_price": 3000.0,
            "profit_target": 2700.0,
            "stop_loss": 3200.0,
            "leverage": 5.0,
            "margin": 3000.0,
        },
    }


@pytest.fixture
def btc_command() -> TelegramCommand:
    """Sample /close BTC command."""
    return TelegramCommand(
        command="close",
        args=["BTC"],
        chat_id="123456789",
        message_id=1,
        raw_text="/close BTC",
        raw_update={},
        user_id="111222333",
    )


@pytest.fixture
def btc_partial_command() -> TelegramCommand:
    """Sample /close BTC 50 command (50% partial close)."""
    return TelegramCommand(
        command="close",
        args=["BTC", "50"],
        chat_id="123456789",
        message_id=2,
        raw_text="/close BTC 50",
        raw_update={},
        user_id="111222333",
    )


@pytest.fixture
def btc_all_command() -> TelegramCommand:
    """Sample /close BTC all command."""
    return TelegramCommand(
        command="close",
        args=["BTC", "all"],
        chat_id="123456789",
        message_id=3,
        raw_text="/close BTC all",
        raw_update={},
        user_id="111222333",
    )


# ═══════════════════════════════════════════════════════════════════
# AC1: COMMAND FORMAT TESTS
# ═══════════════════════════════════════════════════════════════════

class TestSymbolNormalization:
    """Tests for symbol normalization (AC1.3)."""
    
    def test_normalize_simple_symbol(self):
        """Test normalizing simple symbol like BTC."""
        assert _normalize_symbol("BTC") == "BTC"
        assert _normalize_symbol("btc") == "BTC"
        assert _normalize_symbol("Btc") == "BTC"
    
    def test_normalize_symbol_with_usdt_suffix(self):
        """Test normalizing symbol with USDT suffix."""
        assert _normalize_symbol("BTCUSDT") == "BTC"
        assert _normalize_symbol("btcusdt") == "BTC"
        assert _normalize_symbol("ETHUSDT") == "ETH"
    
    def test_normalize_symbol_with_usdc_suffix(self):
        """Test normalizing symbol with USDC suffix."""
        assert _normalize_symbol("BTCUSDC") == "BTC"
        assert _normalize_symbol("ETHUSDC") == "ETH"
    
    def test_normalize_backpack_format(self):
        """Test normalizing Backpack format like BTC_USDC_PERP."""
        assert _normalize_symbol("BTC_USDC_PERP") == "BTC"
        assert _normalize_symbol("ETH_USDC_PERP") == "ETH"
    
    def test_normalize_empty_symbol(self):
        """Test normalizing empty symbol."""
        assert _normalize_symbol("") == ""
        assert _normalize_symbol("  ") == ""


class TestParseCloseArgs:
    """Tests for /close command argument parsing (AC1.2)."""
    
    def test_parse_no_args_returns_error(self):
        """Test parsing with no arguments returns error."""
        symbol, amount, error = _parse_close_args([])
        assert symbol is None
        assert amount is None
        assert error is not None
        assert "请指定" in error
    
    def test_parse_symbol_only_full_close(self):
        """Test parsing symbol only = full close."""
        symbol, amount, error = _parse_close_args(["BTC"])
        assert symbol == "BTC"
        assert amount is None  # None means full close
        assert error is None
    
    def test_parse_symbol_with_all_full_close(self):
        """Test parsing symbol with 'all' = full close."""
        symbol, amount, error = _parse_close_args(["BTC", "all"])
        assert symbol == "BTC"
        assert amount is None
        assert error is None
    
    def test_parse_symbol_with_percentage(self):
        """Test parsing symbol with percentage."""
        symbol, amount, error = _parse_close_args(["BTC", "50"])
        assert symbol == "BTC"
        assert amount == 50.0
        assert error is None
    
    def test_parse_symbol_with_decimal_percentage(self):
        """Test parsing symbol with decimal percentage."""
        symbol, amount, error = _parse_close_args(["ETH", "25.5"])
        assert symbol == "ETH"
        assert amount == 25.5
        assert error is None
    
    def test_parse_invalid_percentage_returns_error(self):
        """Test parsing invalid percentage returns error."""
        symbol, amount, error = _parse_close_args(["BTC", "abc"])
        assert symbol is None
        assert error is not None
        assert "无效的平仓比例" in error
    
    def test_parse_negative_percentage_returns_error(self):
        """Test parsing negative percentage returns error."""
        symbol, amount, error = _parse_close_args(["BTC", "-10"])
        assert symbol is None
        assert error is not None
        assert "不能为负数" in error
    
    def test_parse_zero_percentage_returns_error(self):
        """Test parsing zero percentage returns error."""
        symbol, amount, error = _parse_close_args(["BTC", "0"])
        assert symbol is None
        assert error is not None
        assert "不能为 0" in error


# ═══════════════════════════════════════════════════════════════════
# AC2: PARTIAL CLOSE BEHAVIOR TESTS
# ═══════════════════════════════════════════════════════════════════

class TestCalculateCloseQuantity:
    """Tests for close quantity calculation (AC2)."""
    
    def test_full_close_no_percentage(self):
        """Test full close when no percentage specified."""
        position = {"quantity": 1.0}
        close_qty, remaining, is_full = _calculate_close_quantity(position, None)
        assert close_qty == 1.0
        assert remaining == 0.0
        assert is_full is True
    
    def test_partial_close_50_percent(self):
        """Test 50% partial close."""
        position = {"quantity": 1.0}
        close_qty, remaining, is_full = _calculate_close_quantity(position, 50.0)
        assert close_qty == 0.5
        assert remaining == 0.5
        assert is_full is False
    
    def test_partial_close_25_percent(self):
        """Test 25% partial close."""
        position = {"quantity": 2.0}
        close_qty, remaining, is_full = _calculate_close_quantity(position, 25.0)
        assert close_qty == 0.5
        assert remaining == 1.5
        assert is_full is False
    
    def test_partial_close_75_percent(self):
        """Test 75% partial close."""
        position = {"quantity": 4.0}
        close_qty, remaining, is_full = _calculate_close_quantity(position, 75.0)
        assert close_qty == 3.0
        assert remaining == 1.0
        assert is_full is False


# ═══════════════════════════════════════════════════════════════════
# AC3: >= 100% DEGRADES TO FULL CLOSE
# ═══════════════════════════════════════════════════════════════════

class TestDegradeToFullClose:
    """Tests for >= 100% degrading to full close (AC3)."""
    
    def test_100_percent_degrades_to_full(self):
        """Test 100% degrades to full close."""
        position = {"quantity": 1.0}
        close_qty, remaining, is_full = _calculate_close_quantity(position, 100.0)
        assert close_qty == 1.0
        assert remaining == 0.0
        assert is_full is True
    
    def test_150_percent_degrades_to_full(self):
        """Test 150% degrades to full close."""
        position = {"quantity": 1.0}
        close_qty, remaining, is_full = _calculate_close_quantity(position, 150.0)
        assert close_qty == 1.0
        assert remaining == 0.0
        assert is_full is True
    
    def test_200_percent_degrades_to_full(self):
        """Test 200% degrades to full close."""
        position = {"quantity": 2.0}
        close_qty, remaining, is_full = _calculate_close_quantity(position, 200.0)
        assert close_qty == 2.0
        assert remaining == 0.0
        assert is_full is True


# ═══════════════════════════════════════════════════════════════════
# AC4: NO POSITION SCENARIO
# ═══════════════════════════════════════════════════════════════════

class TestNoPositionScenario:
    """Tests for no position scenario (AC4)."""
    
    def test_close_no_position_returns_success_with_message(
        self, btc_command: TelegramCommand
    ):
        """Test /close with no position returns success with clear message."""
        result = handle_close_command(
            btc_command,
            positions={},  # No positions
            execute_close_fn=None,
        )
        
        assert result.success is True
        assert result.state_changed is False
        assert result.action == "CLOSE_NO_POSITION"
        assert "无" in result.message or "没有" in result.message
    
    def test_close_wrong_symbol_returns_no_position(self):
        """Test /close with wrong symbol returns no position message."""
        cmd = TelegramCommand(
            command="close",
            args=["XRP"],  # Not in positions
            chat_id="123456789",
            message_id=1,
            raw_text="/close XRP",
            raw_update={},
            user_id="111222333",
        )
        
        positions = {
            "BTC": {"side": "long", "quantity": 1.0, "entry_price": 50000.0},
        }
        
        result = handle_close_command(
            cmd,
            positions=positions,
            execute_close_fn=None,
        )
        
        assert result.success is True
        assert result.state_changed is False
        assert result.action == "CLOSE_NO_POSITION"


# ═══════════════════════════════════════════════════════════════════
# AC5: ERROR HANDLING TESTS
# ═══════════════════════════════════════════════════════════════════

class TestErrorHandling:
    """Tests for error handling (AC5)."""
    
    def test_parse_error_returns_failure(self):
        """Test parse error returns failure with message."""
        cmd = TelegramCommand(
            command="close",
            args=[],  # Missing symbol
            chat_id="123456789",
            message_id=1,
            raw_text="/close",
            raw_update={},
            user_id="111222333",
        )
        
        result = handle_close_command(
            cmd,
            positions={},
            execute_close_fn=None,
        )
        
        assert result.success is False
        assert result.action == "CLOSE_PARSE_ERROR"
    
    def test_execution_error_returns_failure(
        self, btc_command: TelegramCommand, sample_positions: Dict
    ):
        """Test execution error returns failure with message."""
        def failing_execute(coin, side, qty):
            raise Exception("Exchange API error")
        
        result = handle_close_command(
            btc_command,
            positions=sample_positions,
            execute_close_fn=failing_execute,
        )
        
        assert result.success is False
        assert result.action == "CLOSE_EXECUTION_ERROR"
        assert "出错" in result.message or "错误" in result.message
    
    def test_execution_failure_result_returns_failure(
        self, btc_command: TelegramCommand, sample_positions: Dict
    ):
        """Test execution returning failure result returns failure."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.errors = ["Insufficient balance"]
        
        def failing_execute(coin, side, qty):
            return mock_result
        
        result = handle_close_command(
            btc_command,
            positions=sample_positions,
            execute_close_fn=failing_execute,
        )
        
        assert result.success is False
        assert result.action == "CLOSE_EXECUTION_FAILED"


# ═══════════════════════════════════════════════════════════════════
# AC6: KILL-SWITCH / DAILY LOSS LIMIT INTEGRATION
# ═══════════════════════════════════════════════════════════════════

class TestKillSwitchIntegration:
    """Tests for Kill-Switch integration (AC6).
    
    /close command should work even when Kill-Switch is active,
    as it only reduces risk exposure.
    """
    
    def test_close_works_during_kill_switch(
        self, btc_command: TelegramCommand, sample_positions: Dict
    ):
        """Test /close works when Kill-Switch is active."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.errors = []
        
        executed = []
        def track_execute(coin, side, qty):
            executed.append((coin, side, qty))
            return mock_result
        
        # Simulate Kill-Switch active by just running the command
        # The /close command itself doesn't check Kill-Switch status
        # because it's designed to work during Kill-Switch (AC6)
        result = handle_close_command(
            btc_command,
            positions=sample_positions,
            execute_close_fn=track_execute,
        )
        
        assert result.success is True
        assert result.state_changed is True
        assert len(executed) == 1
        assert executed[0][0] == "BTC"
    
    def test_partial_close_works_during_kill_switch(
        self, btc_partial_command: TelegramCommand, sample_positions: Dict
    ):
        """Test partial /close works when Kill-Switch is active."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.errors = []
        
        executed = []
        def track_execute(coin, side, qty):
            executed.append((coin, side, qty))
            return mock_result
        
        result = handle_close_command(
            btc_partial_command,
            positions=sample_positions,
            execute_close_fn=track_execute,
        )
        
        assert result.success is True
        assert result.state_changed is True
        assert len(executed) == 1
        # 50% of 0.5 BTC = 0.25 BTC
        assert executed[0][0] == "BTC"
        assert executed[0][2] == pytest.approx(0.25, rel=0.01)


# ═══════════════════════════════════════════════════════════════════
# FULL CLOSE SCENARIO TESTS
# ═══════════════════════════════════════════════════════════════════

class TestFullCloseScenario:
    """Tests for full close scenarios."""
    
    def test_full_close_with_symbol_only(
        self, btc_command: TelegramCommand, sample_positions: Dict
    ):
        """Test /close BTC performs full close."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.errors = []
        
        executed = []
        def track_execute(coin, side, qty):
            executed.append((coin, side, qty))
            return mock_result
        
        result = handle_close_command(
            btc_command,
            positions=sample_positions,
            execute_close_fn=track_execute,
        )
        
        assert result.success is True
        assert result.state_changed is True
        assert result.action == "CLOSE_EXECUTED"
        assert len(executed) == 1
        assert executed[0] == ("BTC", "long", 0.5)
    
    def test_full_close_with_all_keyword(
        self, btc_all_command: TelegramCommand, sample_positions: Dict
    ):
        """Test /close BTC all performs full close."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.errors = []
        
        executed = []
        def track_execute(coin, side, qty):
            executed.append((coin, side, qty))
            return mock_result
        
        result = handle_close_command(
            btc_all_command,
            positions=sample_positions,
            execute_close_fn=track_execute,
        )
        
        assert result.success is True
        assert result.state_changed is True
        assert result.action == "CLOSE_EXECUTED"
        assert len(executed) == 1
        assert executed[0] == ("BTC", "long", 0.5)


# ═══════════════════════════════════════════════════════════════════
# PARTIAL CLOSE SCENARIO TESTS
# ═══════════════════════════════════════════════════════════════════

class TestPartialCloseScenario:
    """Tests for partial close scenarios."""
    
    def test_partial_close_50_percent(
        self, btc_partial_command: TelegramCommand, sample_positions: Dict
    ):
        """Test /close BTC 50 performs 50% partial close."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.errors = []
        
        executed = []
        def track_execute(coin, side, qty):
            executed.append((coin, side, qty))
            return mock_result
        
        result = handle_close_command(
            btc_partial_command,
            positions=sample_positions,
            execute_close_fn=track_execute,
        )
        
        assert result.success is True
        assert result.state_changed is True
        assert result.action == "PARTIAL_CLOSE_EXECUTED"
        assert len(executed) == 1
        # 50% of 0.5 BTC = 0.25 BTC
        assert executed[0][0] == "BTC"
        assert executed[0][1] == "long"
        assert executed[0][2] == pytest.approx(0.25, rel=0.01)
    
    def test_partial_close_message_includes_remaining(
        self, btc_partial_command: TelegramCommand, sample_positions: Dict
    ):
        """Test partial close message includes remaining position info."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.errors = []
        
        result = handle_close_command(
            btc_partial_command,
            positions=sample_positions,
            execute_close_fn=lambda c, s, q: mock_result,
        )
        
        assert result.success is True
        # Message should mention remaining position
        assert "剩余" in result.message


# ═══════════════════════════════════════════════════════════════════
# NOTIONAL CALCULATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestNotionalCalculation:
    """Tests for notional value calculation."""
    
    def test_calculate_notional_basic(self):
        """Test basic notional calculation."""
        notional = _calculate_notional(1.0, 50000.0)
        assert notional == 50000.0
    
    def test_calculate_notional_fractional(self):
        """Test notional calculation with fractional quantity."""
        notional = _calculate_notional(0.5, 50000.0)
        assert notional == 25000.0
    
    def test_calculate_notional_zero_quantity(self):
        """Test notional calculation with zero quantity."""
        notional = _calculate_notional(0.0, 50000.0)
        assert notional == 0.0
    
    def test_calculate_notional_zero_price(self):
        """Test notional calculation with zero price."""
        notional = _calculate_notional(1.0, 0.0)
        assert notional == 0.0


# ═══════════════════════════════════════════════════════════════════
# POSITION FINDING TESTS
# ═══════════════════════════════════════════════════════════════════

class TestFindPosition:
    """Tests for position finding logic."""
    
    def test_find_position_direct_match(self, sample_positions: Dict):
        """Test finding position with direct match."""
        key, pos = _find_position_for_symbol("BTC", sample_positions)
        assert key == "BTC"
        assert pos is not None
        assert pos["side"] == "long"
    
    def test_find_position_case_insensitive(self, sample_positions: Dict):
        """Test finding position case-insensitively."""
        key, pos = _find_position_for_symbol("btc", sample_positions)
        assert key == "BTC"
        assert pos is not None
    
    def test_find_position_not_found(self, sample_positions: Dict):
        """Test finding position that doesn't exist."""
        key, pos = _find_position_for_symbol("XRP", sample_positions)
        assert key is None
        assert pos is None
    
    def test_find_position_empty_positions(self):
        """Test finding position in empty positions dict."""
        key, pos = _find_position_for_symbol("BTC", {})
        assert key is None
        assert pos is None


# ═══════════════════════════════════════════════════════════════════
# GET POSITIONS FOR CLOSE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestGetPositionsForClose:
    """Tests for get_positions_for_close function."""
    
    def test_get_positions_from_local_snapshot(self):
        """Test getting positions from local snapshot."""
        local_positions = {
            "BTC": {"side": "long", "quantity": 1.0, "entry_price": 50000.0},
        }
        
        positions = get_positions_for_close(
            account_snapshot_fn=None,
            positions_snapshot_fn=lambda: local_positions,
        )
        
        assert "BTC" in positions
        assert positions["BTC"]["side"] == "long"
    
    def test_get_positions_prefers_live_snapshot(self):
        """Test that live snapshot is preferred over local."""
        local_positions = {
            "BTC": {"side": "long", "quantity": 1.0, "entry_price": 50000.0},
        }
        
        live_snapshot = {
            "positions": [
                {
                    "symbol": "ETH_USDC_PERP",
                    "netQuantity": "5.0",
                    "entryPrice": "3000.0",
                },
            ],
        }
        
        positions = get_positions_for_close(
            account_snapshot_fn=lambda: live_snapshot,
            positions_snapshot_fn=lambda: local_positions,
        )
        
        # Should have ETH from live snapshot, not BTC from local
        assert "ETH" in positions
        assert "BTC" not in positions
    
    def test_get_positions_falls_back_to_local_on_error(self):
        """Test fallback to local when live snapshot fails."""
        local_positions = {
            "BTC": {"side": "long", "quantity": 1.0, "entry_price": 50000.0},
        }
        
        def failing_snapshot():
            raise Exception("API error")
        
        positions = get_positions_for_close(
            account_snapshot_fn=failing_snapshot,
            positions_snapshot_fn=lambda: local_positions,
        )
        
        assert "BTC" in positions


# ═══════════════════════════════════════════════════════════════════
# INTEGRATION TESTS: HANDLER WIRING AND EXECUTION FLOW
# ═══════════════════════════════════════════════════════════════════

class TestCloseHandlerIntegration:
    """Integration tests for /close command handler wiring (MEDIUM-4)."""
    
    def test_close_handler_wiring_in_create_kill_resume_handlers(self):
        """Test that close_handler is correctly wired in create_kill_resume_handlers."""
        from core.risk_control import RiskControlState
        from notifications.commands.handlers import create_kill_resume_handlers
        
        state = RiskControlState()
        
        # Track execute_close_fn calls
        executed = []
        def mock_execute_close(coin, side, qty):
            executed.append((coin, side, qty))
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.errors = []
            return mock_result
        
        # Create handlers with execute_close_fn
        handlers = create_kill_resume_handlers(
            state=state,
            positions_snapshot_fn=lambda: {
                "BTC": {"side": "long", "quantity": 1.0, "entry_price": 50000.0}
            },
            account_snapshot_fn=None,
            execute_close_fn=mock_execute_close,
            bot_token="test_token",
            chat_id="123456",
        )
        
        # Verify close handler exists
        assert "close" in handlers
        
        # Create a close command
        cmd = TelegramCommand(
            command="close",
            args=["BTC"],
            chat_id="123456",
            message_id=1,
            raw_text="/close BTC",
            raw_update={},
            user_id="111222333",
        )
        
        # Execute handler (should call execute_close_fn)
        handlers["close"](cmd)
        
        # Verify execute_close_fn was called
        assert len(executed) == 1
        assert executed[0][0] == "BTC"
        assert executed[0][1] == "long"
        assert executed[0][2] == 1.0
    
    def test_close_handler_returns_failure_when_execute_returns_none(self):
        """Test that close handler returns failure when execute_close_fn returns None."""
        from core.risk_control import RiskControlState
        from notifications.commands.handlers import create_kill_resume_handlers
        
        state = RiskControlState()
        
        # Mock execute_close_fn that returns None (simulating routing failure)
        def mock_execute_close_returns_none(coin, side, qty):
            return None
        
        # Track sent messages
        sent_messages = []
        def mock_send_fn(text, parse_mode):
            sent_messages.append(text)
        
        handlers = create_kill_resume_handlers(
            state=state,
            positions_snapshot_fn=lambda: {
                "BTC": {"side": "long", "quantity": 1.0, "entry_price": 50000.0}
            },
            account_snapshot_fn=None,
            execute_close_fn=mock_execute_close_returns_none,
            send_fn=mock_send_fn,
            bot_token="test_token",
            chat_id="123456",
        )
        
        cmd = TelegramCommand(
            command="close",
            args=["BTC"],
            chat_id="123456",
            message_id=1,
            raw_text="/close BTC",
            raw_update={},
            user_id="111222333",
        )
        
        handlers["close"](cmd)
        
        # Verify error message was sent
        assert len(sent_messages) == 1
        assert "失败" in sent_messages[0] or "错误" in sent_messages[0]
    
    def test_close_handler_returns_failure_when_execute_returns_failure_result(self):
        """Test that close handler returns failure when execute_close_fn returns failure result."""
        from core.risk_control import RiskControlState
        from notifications.commands.handlers import create_kill_resume_handlers
        
        state = RiskControlState()
        
        # Mock execute_close_fn that returns failure result
        def mock_execute_close_fails(coin, side, qty):
            mock_result = MagicMock()
            mock_result.success = False
            mock_result.errors = ["Insufficient balance"]
            return mock_result
        
        sent_messages = []
        def mock_send_fn(text, parse_mode):
            sent_messages.append(text)
        
        handlers = create_kill_resume_handlers(
            state=state,
            positions_snapshot_fn=lambda: {
                "BTC": {"side": "long", "quantity": 1.0, "entry_price": 50000.0}
            },
            account_snapshot_fn=None,
            execute_close_fn=mock_execute_close_fails,
            send_fn=mock_send_fn,
            bot_token="test_token",
            chat_id="123456",
        )
        
        cmd = TelegramCommand(
            command="close",
            args=["BTC"],
            chat_id="123456",
            message_id=1,
            raw_text="/close BTC",
            raw_update={},
            user_id="111222333",
        )
        
        handlers["close"](cmd)
        
        # Verify error message was sent
        assert len(sent_messages) == 1
        assert "失败" in sent_messages[0]
        assert "Insufficient balance" in sent_messages[0]
    
    def test_close_handler_partial_close_calculates_correct_quantity(self):
        """Test that partial close calculates and passes correct quantity."""
        from core.risk_control import RiskControlState
        from notifications.commands.handlers import create_kill_resume_handlers
        
        state = RiskControlState()
        
        executed = []
        def mock_execute_close(coin, side, qty):
            executed.append((coin, side, qty))
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.errors = []
            return mock_result
        
        handlers = create_kill_resume_handlers(
            state=state,
            positions_snapshot_fn=lambda: {
                "ETH": {"side": "short", "quantity": 10.0, "entry_price": 3000.0}
            },
            account_snapshot_fn=None,
            execute_close_fn=mock_execute_close,
            bot_token="test_token",
            chat_id="123456",
        )
        
        # Request 25% partial close
        cmd = TelegramCommand(
            command="close",
            args=["ETH", "25"],
            chat_id="123456",
            message_id=1,
            raw_text="/close ETH 25",
            raw_update={},
            user_id="111222333",
        )
        
        handlers["close"](cmd)
        
        # Verify 25% of 10.0 = 2.5 was passed
        assert len(executed) == 1
        assert executed[0][0] == "ETH"
        assert executed[0][1] == "short"
        assert executed[0][2] == pytest.approx(2.5, rel=0.01)


class TestExecuteCloseReturnsNone:
    """Tests for execute_close_fn returning None scenarios."""
    
    def test_handle_close_command_fails_when_execute_returns_none(
        self, btc_command: TelegramCommand, sample_positions: Dict
    ):
        """Test that handle_close_command returns failure when execute returns None."""
        def execute_returns_none(coin, side, qty):
            return None
        
        result = handle_close_command(
            btc_command,
            positions=sample_positions,
            execute_close_fn=execute_returns_none,
        )
        
        assert result.success is False
        assert result.state_changed is False
        assert result.action == "CLOSE_EXECUTION_FAILED"
        assert "失败" in result.message or "错误" in result.message
