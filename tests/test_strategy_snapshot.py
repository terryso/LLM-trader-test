"""Tests for strategy/snapshot.py module."""
import numpy as np
import pandas as pd
import pytest

from strategy.snapshot import build_market_snapshot


class TestBuildMarketSnapshot:
    """Tests for build_market_snapshot function."""

    @pytest.fixture
    def sample_execution_df(self):
        """Create sample execution timeframe dataframe."""
        n = 20
        return pd.DataFrame({
            "close": [100 + i * 0.5 for i in range(n)],
            "mid_price": [100 + i * 0.5 for i in range(n)],
            "ema20": [99 + i * 0.4 for i in range(n)],
            "rsi14": [50 + i * 0.5 for i in range(n)],
            "macd": [0.1 * i for i in range(n)],
            "macd_signal": [0.08 * i for i in range(n)],
        })

    @pytest.fixture
    def sample_structure_df(self):
        """Create sample structure timeframe dataframe."""
        n = 20
        return pd.DataFrame({
            "close": [100 + i * 1.0 for i in range(n)],
            "ema20": [99 + i * 0.9 for i in range(n)],
            "ema50": [98 + i * 0.8 for i in range(n)],
            "rsi14": [45 + i * 0.3 for i in range(n)],
            "macd": [0.2 * i for i in range(n)],
            "macd_signal": [0.15 * i for i in range(n)],
            "swing_high": [105 + i * 1.0 for i in range(n)],
            "swing_low": [95 + i * 1.0 for i in range(n)],
            "volume_ratio": [1.0 + i * 0.05 for i in range(n)],
        })

    @pytest.fixture
    def sample_trend_df(self):
        """Create sample trend timeframe dataframe."""
        n = 20
        return pd.DataFrame({
            "close": [100 + i * 2.0 for i in range(n)],
            "ema20": [99 + i * 1.8 for i in range(n)],
            "ema50": [98 + i * 1.6 for i in range(n)],
            "ema200": [95 + i * 1.0 for i in range(n)],
            "rsi14": [55 + i * 0.2 for i in range(n)],
            "macd": [0.3 * i for i in range(n)],
            "macd_signal": [0.25 * i for i in range(n)],
            "macd_histogram": [0.05 * i for i in range(n)],
            "atr": [2.0 + i * 0.1 for i in range(n)],
            "volume": [10000 + i * 100 for i in range(n)],
        })

    def test_returns_dict(self, sample_execution_df, sample_structure_df, sample_trend_df):
        """Should return a dictionary."""
        result = build_market_snapshot(
            symbol="BTCUSDT",
            coin="BTC",
            df_execution=sample_execution_df,
            df_structure=sample_structure_df,
            df_trend=sample_trend_df,
            open_interest_values=[1000, 1100, 1200],
            funding_rates=[0.0001, 0.0002, 0.0003],
        )
        assert isinstance(result, dict)

    def test_contains_symbol_and_coin(self, sample_execution_df, sample_structure_df, sample_trend_df):
        """Should contain symbol and coin fields."""
        result = build_market_snapshot(
            symbol="BTCUSDT",
            coin="BTC",
            df_execution=sample_execution_df,
            df_structure=sample_structure_df,
            df_trend=sample_trend_df,
            open_interest_values=[],
            funding_rates=[],
        )
        assert result["symbol"] == "BTCUSDT"
        assert result["coin"] == "BTC"

    def test_contains_price(self, sample_execution_df, sample_structure_df, sample_trend_df):
        """Should contain current price from execution df."""
        result = build_market_snapshot(
            symbol="BTCUSDT",
            coin="BTC",
            df_execution=sample_execution_df,
            df_structure=sample_structure_df,
            df_trend=sample_trend_df,
            open_interest_values=[],
            funding_rates=[],
        )
        expected_price = float(sample_execution_df["close"].iloc[-1])
        assert result["price"] == expected_price

    def test_contains_execution_data(self, sample_execution_df, sample_structure_df, sample_trend_df):
        """Should contain execution timeframe data."""
        result = build_market_snapshot(
            symbol="BTCUSDT",
            coin="BTC",
            df_execution=sample_execution_df,
            df_structure=sample_structure_df,
            df_trend=sample_trend_df,
            open_interest_values=[],
            funding_rates=[],
        )
        assert "execution" in result
        assert "ema20" in result["execution"]
        assert "rsi14" in result["execution"]
        assert "macd" in result["execution"]
        assert "series" in result["execution"]

    def test_contains_structure_data(self, sample_execution_df, sample_structure_df, sample_trend_df):
        """Should contain structure timeframe data."""
        result = build_market_snapshot(
            symbol="BTCUSDT",
            coin="BTC",
            df_execution=sample_execution_df,
            df_structure=sample_structure_df,
            df_trend=sample_trend_df,
            open_interest_values=[],
            funding_rates=[],
        )
        assert "structure" in result
        assert "ema20" in result["structure"]
        assert "ema50" in result["structure"]
        assert "swing_high" in result["structure"]
        assert "swing_low" in result["structure"]

    def test_contains_trend_data(self, sample_execution_df, sample_structure_df, sample_trend_df):
        """Should contain trend timeframe data."""
        result = build_market_snapshot(
            symbol="BTCUSDT",
            coin="BTC",
            df_execution=sample_execution_df,
            df_structure=sample_structure_df,
            df_trend=sample_trend_df,
            open_interest_values=[],
            funding_rates=[],
        )
        assert "trend" in result
        assert "ema200" in result["trend"]
        assert "atr" in result["trend"]
        assert "current_volume" in result["trend"]
        assert "average_volume" in result["trend"]

    def test_funding_rate_latest(self, sample_execution_df, sample_structure_df, sample_trend_df):
        """Should use latest funding rate."""
        result = build_market_snapshot(
            symbol="BTCUSDT",
            coin="BTC",
            df_execution=sample_execution_df,
            df_structure=sample_structure_df,
            df_trend=sample_trend_df,
            open_interest_values=[],
            funding_rates=[0.0001, 0.0002, 0.0003],
        )
        assert result["funding_rate"] == 0.0003

    def test_funding_rate_empty(self, sample_execution_df, sample_structure_df, sample_trend_df):
        """Should default to 0.0 when funding rates empty."""
        result = build_market_snapshot(
            symbol="BTCUSDT",
            coin="BTC",
            df_execution=sample_execution_df,
            df_structure=sample_structure_df,
            df_trend=sample_trend_df,
            open_interest_values=[],
            funding_rates=[],
        )
        assert result["funding_rate"] == 0.0

    def test_open_interest_values(self, sample_execution_df, sample_structure_df, sample_trend_df):
        """Should calculate open interest latest and average."""
        result = build_market_snapshot(
            symbol="BTCUSDT",
            coin="BTC",
            df_execution=sample_execution_df,
            df_structure=sample_structure_df,
            df_trend=sample_trend_df,
            open_interest_values=[1000, 1100, 1200],
            funding_rates=[],
        )
        assert result["open_interest"]["latest"] == 1200
        assert result["open_interest"]["average"] == pytest.approx(1100.0)

    def test_open_interest_empty(self, sample_execution_df, sample_structure_df, sample_trend_df):
        """Should handle empty open interest values."""
        result = build_market_snapshot(
            symbol="BTCUSDT",
            coin="BTC",
            df_execution=sample_execution_df,
            df_structure=sample_structure_df,
            df_trend=sample_trend_df,
            open_interest_values=[],
            funding_rates=[],
        )
        assert result["open_interest"]["latest"] is None
        assert result["open_interest"]["average"] is None

    def test_series_data_rounded(self, sample_execution_df, sample_structure_df, sample_trend_df):
        """Should contain rounded series data."""
        result = build_market_snapshot(
            symbol="BTCUSDT",
            coin="BTC",
            df_execution=sample_execution_df,
            df_structure=sample_structure_df,
            df_trend=sample_trend_df,
            open_interest_values=[],
            funding_rates=[],
        )
        # Series should be lists of floats
        assert isinstance(result["execution"]["series"]["mid_prices"], list)
        assert isinstance(result["structure"]["series"]["close"], list)
        assert isinstance(result["trend"]["series"]["close"], list)

    def test_series_length_max_10(self, sample_execution_df, sample_structure_df, sample_trend_df):
        """Series should contain at most 10 values (tail)."""
        result = build_market_snapshot(
            symbol="BTCUSDT",
            coin="BTC",
            df_execution=sample_execution_df,
            df_structure=sample_structure_df,
            df_trend=sample_trend_df,
            open_interest_values=[],
            funding_rates=[],
        )
        # Series should be from tail(10)
        assert len(result["execution"]["series"]["mid_prices"]) <= 10
        assert len(result["structure"]["series"]["close"]) <= 10
        assert len(result["trend"]["series"]["close"]) <= 10
