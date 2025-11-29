"""Tests for llm/client.py module."""
from unittest.mock import MagicMock, patch
import pytest

from llm.client import (
    _recover_partial_decisions,
    _log_llm_decisions,
    call_deepseek_api,
)


class TestRecoverPartialDecisions:
    """Tests for _recover_partial_decisions function."""

    @patch("llm.client.SYMBOL_TO_COIN", {"BTCUSDT": "BTC", "ETHUSDT": "ETH"})
    def test_recovers_decisions(self):
        """Should recover decisions for configured coins."""
        json_str = '{"BTC": {"signal": "entry", "side": "long"}, "ETH": {"signal": "hold"}}'
        result = _recover_partial_decisions(json_str)
        
        assert result is not None
        decisions, missing = result
        assert "BTC" in decisions
        assert "ETH" in decisions

    @patch("llm.client.SYMBOL_TO_COIN", {"BTCUSDT": "BTC"})
    def test_returns_none_on_failure(self):
        """Should return None when recovery fails."""
        json_str = "completely invalid"
        result = _recover_partial_decisions(json_str)
        
        assert result is None


class TestLogLlmDecisions:
    """Tests for _log_llm_decisions function."""

    @patch("llm.client.logging")
    def test_logs_entry_decision(self, mock_logging):
        """Should log entry decisions."""
        decisions = {
            "BTC": {
                "signal": "entry",
                "side": "long",
                "quantity": 0.1,
                "profit_target": 52000,
                "stop_loss": 49000,
                "confidence": 0.85,
            }
        }
        
        _log_llm_decisions(decisions)
        
        mock_logging.info.assert_called_once()
        call_args = mock_logging.info.call_args[0]
        assert "BTC" in call_args[1]
        assert "ENTRY" in call_args[1]
        assert "long" in call_args[1]

    @patch("llm.client.logging")
    def test_logs_close_decision(self, mock_logging):
        """Should log close decisions."""
        decisions = {
            "BTC": {"signal": "close", "side": "long"}
        }
        
        _log_llm_decisions(decisions)
        
        call_args = mock_logging.info.call_args[0]
        assert "CLOSE" in call_args[1]

    @patch("llm.client.logging")
    def test_logs_hold_decision(self, mock_logging):
        """Should log hold decisions."""
        decisions = {
            "BTC": {"signal": "hold"}
        }
        
        _log_llm_decisions(decisions)
        
        call_args = mock_logging.info.call_args[0]
        assert "HOLD" in call_args[1]

    @patch("llm.client.logging")
    def test_handles_multiple_coins(self, mock_logging):
        """Should log multiple coin decisions."""
        decisions = {
            "BTC": {"signal": "entry", "side": "long"},
            "ETH": {"signal": "hold"},
        }
        
        _log_llm_decisions(decisions)
        
        call_args = mock_logging.info.call_args[0]
        assert "BTC" in call_args[1]
        assert "ETH" in call_args[1]

    @patch("llm.client.logging")
    def test_handles_invalid_decision(self, mock_logging):
        """Should handle invalid decision format."""
        decisions = {
            "BTC": "not a dict"
        }
        
        # Should not raise
        _log_llm_decisions(decisions)


class TestCallDeepseekApi:
    """Tests for call_deepseek_api function."""

    @patch("llm.client.LLM_API_KEY", "")
    def test_returns_none_without_api_key(self):
        """Should return None if no API key configured."""
        result = call_deepseek_api(
            prompt="test",
            log_ai_message_fn=MagicMock(),
            notify_error_fn=MagicMock(),
        )
        
        assert result is None

    @patch("llm.client.requests.post")
    @patch("llm.client.LLM_API_KEY", "test_key")
    @patch("llm.client.LLM_API_BASE_URL", "https://api.test.com")
    @patch("llm.client.LLM_MODEL_NAME", "test-model")
    @patch("llm.client.TRADING_RULES_PROMPT", "You are a trading bot.")
    def test_calls_api(self, mock_post):
        """Should call the LLM API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "test-123",
            "choices": [
                {
                    "message": {"content": '{"BTC": {"signal": "hold"}}'},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"total_tokens": 100},
        }
        mock_post.return_value = mock_response
        
        log_fn = MagicMock()
        notify_fn = MagicMock()
        
        result = call_deepseek_api(
            prompt="Analyze BTC",
            log_ai_message_fn=log_fn,
            notify_error_fn=notify_fn,
        )
        
        mock_post.assert_called_once()
        assert result is not None
        assert "BTC" in result

    @patch("llm.client.requests.post")
    @patch("llm.client.LLM_API_KEY", "test_key")
    @patch("llm.client.LLM_API_BASE_URL", "https://api.test.com")
    @patch("llm.client.LLM_MODEL_NAME", "test-model")
    @patch("llm.client.TRADING_RULES_PROMPT", "You are a trading bot.")
    def test_handles_api_error(self, mock_post):
        """Should handle API error response."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        notify_fn = MagicMock()
        
        result = call_deepseek_api(
            prompt="test",
            log_ai_message_fn=MagicMock(),
            notify_error_fn=notify_fn,
        )
        
        assert result is None
        notify_fn.assert_called()

    @patch("llm.client.requests.post")
    @patch("llm.client.LLM_API_KEY", "test_key")
    @patch("llm.client.LLM_API_BASE_URL", "https://api.test.com")
    @patch("llm.client.LLM_MODEL_NAME", "test-model")
    @patch("llm.client.TRADING_RULES_PROMPT", "You are a trading bot.")
    def test_handles_no_choices(self, mock_post):
        """Should handle response with no choices."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "test", "choices": []}
        mock_response.text = "{}"
        mock_post.return_value = mock_response
        
        notify_fn = MagicMock()
        
        result = call_deepseek_api(
            prompt="test",
            log_ai_message_fn=MagicMock(),
            notify_error_fn=notify_fn,
        )
        
        assert result is None
        notify_fn.assert_called()

    @patch("llm.client.requests.post")
    @patch("llm.client.LLM_API_KEY", "test_key")
    @patch("llm.client.LLM_API_BASE_URL", "https://api.test.com")
    @patch("llm.client.LLM_MODEL_NAME", "test-model")
    @patch("llm.client.TRADING_RULES_PROMPT", "You are a trading bot.")
    def test_logs_messages(self, mock_post):
        """Should log sent and received messages."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "test-123",
            "choices": [
                {
                    "message": {"content": '{"BTC": {"signal": "hold"}}'},
                    "finish_reason": "stop",
                }
            ],
        }
        mock_post.return_value = mock_response
        
        log_fn = MagicMock()
        
        call_deepseek_api(
            prompt="Analyze BTC",
            log_ai_message_fn=log_fn,
            notify_error_fn=MagicMock(),
        )
        
        # Should log system message, user message, and assistant response
        assert log_fn.call_count >= 3

    @patch("llm.client.requests.post")
    @patch("llm.client.LLM_API_KEY", "test_key")
    @patch("llm.client.LLM_API_BASE_URL", "https://api.test.com")
    @patch("llm.client.LLM_MODEL_NAME", "test-model")
    @patch("llm.client.TRADING_RULES_PROMPT", "You are a trading bot.")
    def test_handles_exception(self, mock_post):
        """Should handle exceptions during API call."""
        mock_post.side_effect = Exception("Network error")
        
        notify_fn = MagicMock()
        
        result = call_deepseek_api(
            prompt="test",
            log_ai_message_fn=MagicMock(),
            notify_error_fn=notify_fn,
        )
        
        assert result is None
        notify_fn.assert_called()
