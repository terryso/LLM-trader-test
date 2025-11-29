"""Tests for display/formatters.py module."""
import pytest

from display.formatters import build_entry_signal_message, build_close_signal_message


class TestBuildEntrySignalMessage:
    """Tests for build_entry_signal_message function."""

    @pytest.fixture
    def entry_params(self):
        """Default parameters for entry signal message."""
        return {
            "coin": "BTC",
            "side": "long",
            "leverage_display": "10x",
            "entry_price": 50000.0,
            "quantity": 0.1,
            "margin_required": 500.0,
            "risk_usd": 50.0,
            "profit_target_price": 52000.0,
            "stop_loss_price": 49000.0,
            "gross_at_target": 200.0,
            "gross_at_stop": -100.0,
            "rr_display": "2:1",
            "entry_fee": 2.5,
            "confidence": 0.85,
            "reason_text_for_signal": "Strong bullish momentum",
            "liquidity": "taker",
            "timestamp": "2024-01-15 10:30:00 UTC",
        }

    def test_returns_string(self, entry_params):
        """Should return a string."""
        result = build_entry_signal_message(**entry_params)
        assert isinstance(result, str)

    def test_contains_coin(self, entry_params):
        """Should contain the coin symbol."""
        result = build_entry_signal_message(**entry_params)
        assert "BTC" in result

    def test_contains_entry_signal_header(self, entry_params):
        """Should contain ENTRY SIGNAL header."""
        result = build_entry_signal_message(**entry_params)
        assert "ENTRY SIGNAL" in result

    def test_contains_direction(self, entry_params):
        """Should contain trade direction."""
        result = build_entry_signal_message(**entry_params)
        assert "LONG" in result

    def test_contains_entry_price(self, entry_params):
        """Should contain entry price."""
        result = build_entry_signal_message(**entry_params)
        assert "50000" in result

    def test_contains_quantity(self, entry_params):
        """Should contain position quantity."""
        result = build_entry_signal_message(**entry_params)
        assert "0.1" in result

    def test_contains_margin(self, entry_params):
        """Should contain margin required."""
        result = build_entry_signal_message(**entry_params)
        assert "500" in result

    def test_contains_risk(self, entry_params):
        """Should contain risk amount."""
        result = build_entry_signal_message(**entry_params)
        assert "50" in result

    def test_contains_targets(self, entry_params):
        """Should contain profit target and stop loss."""
        result = build_entry_signal_message(**entry_params)
        assert "52000" in result
        assert "49000" in result

    def test_contains_rr_ratio(self, entry_params):
        """Should contain risk/reward ratio."""
        result = build_entry_signal_message(**entry_params)
        assert "2:1" in result

    def test_contains_confidence(self, entry_params):
        """Should contain confidence percentage."""
        result = build_entry_signal_message(**entry_params)
        assert "85%" in result

    def test_contains_reasoning(self, entry_params):
        """Should contain reasoning text."""
        result = build_entry_signal_message(**entry_params)
        assert "Strong bullish momentum" in result

    def test_contains_timestamp(self, entry_params):
        """Should contain timestamp."""
        result = build_entry_signal_message(**entry_params)
        assert "2024-01-15" in result

    def test_long_emoji_green(self, entry_params):
        """Should use green emoji for long."""
        entry_params["side"] = "long"
        result = build_entry_signal_message(**entry_params)
        assert "🟢" in result

    def test_short_emoji_red(self, entry_params):
        """Should use red emoji for short."""
        entry_params["side"] = "short"
        result = build_entry_signal_message(**entry_params)
        assert "🔴" in result

    def test_contains_liquidity(self, entry_params):
        """Should contain liquidity type."""
        result = build_entry_signal_message(**entry_params)
        assert "taker" in result

    def test_contains_leverage(self, entry_params):
        """Should contain leverage display."""
        result = build_entry_signal_message(**entry_params)
        assert "10x" in result


class TestBuildCloseSignalMessage:
    """Tests for build_close_signal_message function."""

    @pytest.fixture
    def close_params(self):
        """Default parameters for close signal message."""
        return {
            "coin": "BTC",
            "side": "long",
            "quantity": 0.1,
            "entry_price": 50000.0,
            "current_price": 52000.0,
            "pnl": 200.0,
            "total_fees": 5.0,
            "net_pnl": 195.0,
            "margin": 500.0,
            "balance": 10195.0,
            "reason_text_for_signal": "Take profit target reached",
            "timestamp": "2024-01-15 12:30:00 UTC",
        }

    def test_returns_string(self, close_params):
        """Should return a string."""
        result = build_close_signal_message(**close_params)
        assert isinstance(result, str)

    def test_contains_coin(self, close_params):
        """Should contain the coin symbol."""
        result = build_close_signal_message(**close_params)
        assert "BTC" in result

    def test_contains_close_signal_header(self, close_params):
        """Should contain CLOSE SIGNAL header."""
        result = build_close_signal_message(**close_params)
        assert "CLOSE SIGNAL" in result

    def test_profit_emoji_checkmark(self, close_params):
        """Should use checkmark emoji for profit."""
        close_params["net_pnl"] = 100.0
        result = build_close_signal_message(**close_params)
        assert "✅" in result
        assert "PROFIT" in result

    def test_loss_emoji_x(self, close_params):
        """Should use X emoji for loss."""
        close_params["net_pnl"] = -100.0
        result = build_close_signal_message(**close_params)
        assert "❌" in result
        assert "LOSS" in result

    def test_breakeven_emoji_dash(self, close_params):
        """Should use dash emoji for breakeven."""
        close_params["net_pnl"] = 0.0
        result = build_close_signal_message(**close_params)
        assert "➖" in result
        assert "BREAKEVEN" in result

    def test_contains_entry_price(self, close_params):
        """Should contain entry price."""
        result = build_close_signal_message(**close_params)
        assert "50000" in result

    def test_contains_exit_price(self, close_params):
        """Should contain exit price."""
        result = build_close_signal_message(**close_params)
        assert "52000" in result

    def test_contains_pnl_values(self, close_params):
        """Should contain PnL values."""
        result = build_close_signal_message(**close_params)
        assert "200" in result  # gross pnl
        assert "195" in result  # net pnl

    def test_contains_fees(self, close_params):
        """Should contain fees paid."""
        result = build_close_signal_message(**close_params)
        assert "5.00" in result

    def test_contains_balance(self, close_params):
        """Should contain new balance."""
        result = build_close_signal_message(**close_params)
        assert "10195" in result

    def test_contains_reasoning(self, close_params):
        """Should contain exit reasoning."""
        result = build_close_signal_message(**close_params)
        assert "Take profit target reached" in result

    def test_contains_timestamp(self, close_params):
        """Should contain timestamp."""
        result = build_close_signal_message(**close_params)
        assert "2024-01-15" in result

    def test_contains_roi(self, close_params):
        """Should contain ROI percentage."""
        result = build_close_signal_message(**close_params)
        assert "ROI" in result

    def test_contains_price_change_percent(self, close_params):
        """Should contain price change percentage."""
        result = build_close_signal_message(**close_params)
        # 52000 - 50000 = 2000, 2000/50000 = 4%
        assert "4.00%" in result

    def test_direction_displayed(self, close_params):
        """Should display trade direction."""
        result = build_close_signal_message(**close_params)
        assert "LONG" in result

    def test_quantity_displayed(self, close_params):
        """Should display position quantity."""
        result = build_close_signal_message(**close_params)
        assert "0.1" in result
