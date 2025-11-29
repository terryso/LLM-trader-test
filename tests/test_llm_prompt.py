"""Tests for llm/prompt.py module."""
import pytest

from llm.prompt import build_trading_prompt


class TestBuildTradingPrompt:
    """Tests for build_trading_prompt function."""

    @pytest.fixture
    def base_context(self):
        """Base context for prompt building."""
        return {
            "minutes_running": 60,
            "now_iso": "2024-01-15T10:30:00Z",
            "invocation_count": 10,
            "interval": "5m",
            "market_snapshots": {
                "BTC": {
                    "symbol": "BTCUSDT",
                    "coin": "BTC",
                    "price": 50000.0,
                    "execution": {
                        "ema20": 49500.0,
                        "rsi14": 55.0,
                        "macd": 100.0,
                        "macd_signal": 80.0,
                        "series": {
                            "mid_prices": [49800, 49900, 50000],
                            "ema20": [49400, 49450, 49500],
                            "macd": [90, 95, 100],
                            "rsi14": [52, 54, 55],
                        },
                    },
                    "structure": {
                        "ema20": 49000.0,
                        "ema50": 48500.0,
                        "rsi14": 58.0,
                        "macd": 200.0,
                        "macd_signal": 180.0,
                        "swing_high": 51000.0,
                        "swing_low": 48000.0,
                        "volume_ratio": 1.2,
                        "series": {
                            "close": [49500, 49800, 50000],
                            "ema20": [48800, 48900, 49000],
                            "ema50": [48300, 48400, 48500],
                            "rsi14": [56, 57, 58],
                            "macd": [180, 190, 200],
                            "swing_high": [50800, 50900, 51000],
                            "swing_low": [47800, 47900, 48000],
                        },
                    },
                    "trend": {
                        "ema20": 48000.0,
                        "ema50": 47000.0,
                        "ema200": 45000.0,
                        "rsi14": 60.0,
                        "macd": 500.0,
                        "macd_signal": 450.0,
                        "macd_histogram": 50.0,
                        "atr": 1000.0,
                        "current_volume": 10000.0,
                        "average_volume": 8000.0,
                        "series": {
                            "close": [49000, 49500, 50000],
                            "ema20": [47500, 47750, 48000],
                            "ema50": [46500, 46750, 47000],
                            "macd": [450, 475, 500],
                            "rsi14": [58, 59, 60],
                        },
                    },
                    "funding_rate": 0.0001,
                    "funding_rates": [0.0001, 0.00015, 0.0001],
                    "open_interest": {
                        "latest": 1000000.0,
                        "average": 950000.0,
                    },
                },
            },
            "account": {
                "balance": 10000.0,
                "total_margin": 500.0,
                "net_unrealized_total": 50.0,
                "total_equity": 10550.0,
                "total_return": 5.5,
            },
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "coin": "BTC",
                    "side": "long",
                    "quantity": 0.01,
                    "entry_price": 49000.0,
                    "profit_target": 52000.0,
                    "stop_loss": 48000.0,
                    "leverage": 10,
                    "margin": 500.0,
                    "unrealized_pnl": 100.0,
                    "net_unrealized_pnl": 95.0,
                    "entry_justification": "Bullish breakout",
                },
            ],
        }

    def test_returns_string(self, base_context):
        """Should return a string."""
        result = build_trading_prompt(base_context)
        assert isinstance(result, str)

    def test_contains_time_info(self, base_context):
        """Should contain time information."""
        result = build_trading_prompt(base_context)
        assert "60 minutes" in result
        assert "2024-01-15" in result
        assert "10 times" in result

    def test_contains_market_data(self, base_context):
        """Should contain market data."""
        result = build_trading_prompt(base_context)
        assert "BTC" in result
        assert "50000" in result  # price

    def test_contains_account_info(self, base_context):
        """Should contain account information."""
        result = build_trading_prompt(base_context)
        assert "10000" in result  # balance
        assert "10550" in result  # equity

    def test_contains_position_info(self, base_context):
        """Should contain position information."""
        result = build_trading_prompt(base_context)
        assert "long" in result.lower()
        assert "49000" in result  # entry price

    def test_handles_no_positions(self, base_context):
        """Should handle empty positions."""
        base_context["positions"] = []
        result = build_trading_prompt(base_context)
        assert isinstance(result, str)
        # Should still contain account info even without positions
        assert "10000" in result or "balance" in result.lower()

    def test_handles_multiple_coins(self, base_context):
        """Should handle multiple coins in market snapshots."""
        base_context["market_snapshots"]["ETH"] = {
            "symbol": "ETHUSDT",
            "coin": "ETH",
            "price": 3000.0,
            "execution": {
                "ema20": 2950.0,
                "rsi14": 50.0,
                "macd": 10.0,
                "macd_signal": 8.0,
                "series": {"mid_prices": [], "ema20": [], "macd": [], "rsi14": []},
            },
            "structure": {
                "ema20": 2900.0,
                "ema50": 2850.0,
                "rsi14": 52.0,
                "macd": 20.0,
                "macd_signal": 18.0,
                "swing_high": 3100.0,
                "swing_low": 2800.0,
                "volume_ratio": 1.1,
                "series": {"close": [], "ema20": [], "ema50": [], "rsi14": [], "macd": [], "swing_high": [], "swing_low": []},
            },
            "trend": {
                "ema20": 2800.0,
                "ema50": 2700.0,
                "ema200": 2500.0,
                "rsi14": 55.0,
                "macd": 50.0,
                "macd_signal": 45.0,
                "macd_histogram": 5.0,
                "atr": 100.0,
                "current_volume": 5000.0,
                "average_volume": 4000.0,
                "series": {"close": [], "ema20": [], "ema50": [], "macd": [], "rsi14": []},
            },
            "funding_rate": 0.0002,
            "funding_rates": [0.0002],
            "open_interest": {"latest": 500000.0, "average": 480000.0},
        }
        
        result = build_trading_prompt(base_context)
        assert "BTC" in result
        assert "ETH" in result

    def test_formats_indicators(self, base_context):
        """Should format indicator values."""
        result = build_trading_prompt(base_context)
        # Should contain RSI, EMA, MACD references
        assert "rsi" in result.lower() or "RSI" in result
        assert "ema" in result.lower() or "EMA" in result

    def test_includes_funding_rate(self, base_context):
        """Should include funding rate information."""
        result = build_trading_prompt(base_context)
        # Funding rate should be mentioned somewhere
        assert "funding" in result.lower() or "0.0001" in result

    def test_handles_none_values(self, base_context):
        """Should handle None values gracefully."""
        base_context["market_snapshots"]["BTC"]["open_interest"]["latest"] = None
        base_context["market_snapshots"]["BTC"]["open_interest"]["average"] = None
        
        result = build_trading_prompt(base_context)
        assert isinstance(result, str)
        # Should show N/A or similar for None values
        assert "N/A" in result or result  # At least should not crash
