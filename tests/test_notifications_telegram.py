"""Tests for notifications/telegram.py module."""
from unittest.mock import MagicMock, patch
import pytest

from notifications.telegram import (
    strip_ansi_codes,
    escape_markdown,
    send_telegram_message,
    send_entry_signal_to_telegram,
    send_close_signal_to_telegram,
)


class TestStripAnsiCodes:
    """Tests for strip_ansi_codes function."""

    def test_removes_color_codes(self):
        """Should remove ANSI color codes."""
        colored = "\x1b[31mRed\x1b[0m"
        assert strip_ansi_codes(colored) == "Red"

    def test_handles_plain_text(self):
        """Should return plain text unchanged."""
        assert strip_ansi_codes("plain text") == "plain text"

    def test_handles_empty_string(self):
        """Should handle empty string."""
        assert strip_ansi_codes("") == ""


class TestEscapeMarkdown:
    """Tests for escape_markdown function."""

    def test_escapes_special_chars(self):
        """Should escape Markdown special characters."""
        assert escape_markdown("*bold*") == r"\*bold\*"
        assert escape_markdown("_italic_") == r"\_italic\_"

    def test_handles_empty_string(self):
        """Should return empty string unchanged."""
        assert escape_markdown("") == ""

    def test_handles_none(self):
        """Should return None unchanged."""
        assert escape_markdown(None) is None


class TestSendTelegramMessage:
    """Tests for send_telegram_message function."""

    @patch("notifications.telegram.requests.post")
    def test_sends_message(self, mock_post):
        """Should send message to Telegram API."""
        mock_post.return_value.status_code = 200
        
        send_telegram_message(
            bot_token="test_token",
            default_chat_id="123456",
            text="Hello World",
        )
        
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        # Check URL contains token (first positional arg or url keyword)
        url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
        assert "test_token" in url
        assert call_args[1]["json"]["text"] == "Hello World"
        assert call_args[1]["json"]["chat_id"] == "123456"

    @patch("notifications.telegram.requests.post")
    def test_uses_custom_chat_id(self, mock_post):
        """Should use custom chat_id when provided."""
        mock_post.return_value.status_code = 200
        
        send_telegram_message(
            bot_token="test_token",
            default_chat_id="123456",
            text="Hello",
            chat_id="789012",
        )
        
        assert mock_post.call_args[1]["json"]["chat_id"] == "789012"

    def test_skips_without_token(self):
        """Should skip sending if no bot token."""
        # Should not raise
        send_telegram_message(
            bot_token="",
            default_chat_id="123456",
            text="Hello",
        )

    def test_skips_without_chat_id(self):
        """Should skip sending if no chat ID."""
        # Should not raise
        send_telegram_message(
            bot_token="test_token",
            default_chat_id="",
            text="Hello",
        )

    @patch("notifications.telegram.requests.post")
    def test_includes_parse_mode(self, mock_post):
        """Should include parse_mode in request."""
        mock_post.return_value.status_code = 200
        
        send_telegram_message(
            bot_token="test_token",
            default_chat_id="123456",
            text="*bold*",
            parse_mode="Markdown",
        )
        
        assert mock_post.call_args[1]["json"]["parse_mode"] == "Markdown"

    @patch("notifications.telegram.requests.post")
    def test_fallback_on_parse_error(self, mock_post):
        """Should retry without parse_mode on parse error."""
        # First call fails with parse error
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 400
        mock_response_fail.text = "can't parse entities"
        
        # Second call succeeds
        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        
        mock_post.side_effect = [mock_response_fail, mock_response_success]
        
        send_telegram_message(
            bot_token="test_token",
            default_chat_id="123456",
            text="*broken markdown",
            parse_mode="Markdown",
        )
        
        assert mock_post.call_count == 2
        # Second call should not have parse_mode
        second_call = mock_post.call_args_list[1]
        assert "parse_mode" not in second_call[1]["json"]


class TestSendEntrySignalToTelegram:
    """Tests for send_entry_signal_to_telegram function."""

    def test_calls_send_fn(self):
        """Should call send function with formatted message."""
        mock_send = MagicMock()
        
        send_entry_signal_to_telegram(
            coin="BTC",
            side="long",
            leverage_display="10x",
            entry_price=50000.0,
            quantity=0.1,
            margin_required=500.0,
            risk_usd=50.0,
            profit_target_price=52000.0,
            stop_loss_price=49000.0,
            gross_at_target=200.0,
            gross_at_stop=-100.0,
            rr_display="2:1",
            entry_fee=2.5,
            confidence=0.85,
            reason_text_for_signal="Bullish momentum",
            liquidity="taker",
            timestamp="2024-01-15 10:30:00",
            send_fn=mock_send,
            signals_chat_id="123456",
        )
        
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        assert "BTC" in call_args[0]
        assert "ENTRY" in call_args[0]
        assert call_args[1] == "123456"
        assert call_args[2] == "Markdown"

    def test_message_contains_details(self):
        """Should include trade details in message."""
        captured_message = None
        def capture_send(text, chat_id, parse_mode):
            nonlocal captured_message
            captured_message = text
        
        send_entry_signal_to_telegram(
            coin="ETH",
            side="short",
            leverage_display="5x",
            entry_price=3000.0,
            quantity=1.0,
            margin_required=600.0,
            risk_usd=30.0,
            profit_target_price=2800.0,
            stop_loss_price=3100.0,
            gross_at_target=200.0,
            gross_at_stop=-100.0,
            rr_display="2:1",
            entry_fee=1.5,
            confidence=0.75,
            reason_text_for_signal="Bearish divergence",
            liquidity="maker",
            timestamp="2024-01-15 10:30:00",
            send_fn=capture_send,
            signals_chat_id=None,
        )
        
        assert "ETH" in captured_message
        assert "SHORT" in captured_message
        assert "3000" in captured_message


class TestSendCloseSignalToTelegram:
    """Tests for send_close_signal_to_telegram function."""

    def test_calls_send_fn(self):
        """Should call send function with formatted message."""
        mock_send = MagicMock()
        
        send_close_signal_to_telegram(
            coin="BTC",
            side="long",
            quantity=0.1,
            entry_price=50000.0,
            current_price=52000.0,
            pnl=200.0,
            total_fees=5.0,
            net_pnl=195.0,
            margin=500.0,
            balance=10195.0,
            reason_text_for_signal="Take profit reached",
            timestamp="2024-01-15 12:30:00",
            send_fn=mock_send,
            signals_chat_id="123456",
        )
        
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        assert "BTC" in call_args[0]
        assert "CLOSE" in call_args[0]

    def test_message_contains_pnl(self):
        """Should include PnL details in message."""
        captured_message = None
        def capture_send(text, chat_id, parse_mode):
            nonlocal captured_message
            captured_message = text
        
        send_close_signal_to_telegram(
            coin="BTC",
            side="long",
            quantity=0.1,
            entry_price=50000.0,
            current_price=52000.0,
            pnl=200.0,
            total_fees=5.0,
            net_pnl=195.0,
            margin=500.0,
            balance=10195.0,
            reason_text_for_signal="Take profit",
            timestamp="2024-01-15 12:30:00",
            send_fn=capture_send,
            signals_chat_id=None,
        )
        
        assert "195" in captured_message  # net_pnl
        assert "PROFIT" in captured_message
