"""Tests for strategy/indicators.py module."""
import numpy as np
import pandas as pd
import pytest

from strategy.indicators import (
    calculate_rsi_series,
    add_indicator_columns,
    calculate_atr_series,
    calculate_indicators,
    round_series,
)


class TestCalculateRsiSeries:
    """Tests for calculate_rsi_series function."""

    def test_rsi_basic_calculation(self):
        """Should calculate RSI values correctly."""
        # Create a simple price series
        close = pd.Series([44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08])
        rsi = calculate_rsi_series(close, period=14)
        
        # RSI should be between 0 and 100
        assert rsi.dropna().between(0, 100).all()

    def test_rsi_returns_series(self):
        """Should return a pandas Series."""
        close = pd.Series([100, 101, 102, 101, 100, 99, 100, 101])
        rsi = calculate_rsi_series(close, period=5)
        assert isinstance(rsi, pd.Series)

    def test_rsi_length_matches_input(self):
        """RSI series should have same length as input."""
        close = pd.Series([100, 101, 102, 103, 104, 105])
        rsi = calculate_rsi_series(close, period=3)
        assert len(rsi) == len(close)

    def test_rsi_uptrend_high_value(self):
        """RSI should be high in uptrend with minor pullbacks."""
        # Need some minor pullbacks for RSI to have valid values (loss > 0)
        close = pd.Series([100, 102, 101, 104, 103, 106, 105, 108, 107, 110, 109, 112, 111, 114, 113, 116])
        rsi = calculate_rsi_series(close, period=5)
        # Last RSI value should be high (above 60) in uptrend with minor pullbacks
        last_valid_rsi = rsi.dropna().iloc[-1] if not rsi.dropna().empty else 50
        assert last_valid_rsi > 60

    def test_rsi_downtrend_low_value(self):
        """RSI should be low in strong downtrend."""
        close = pd.Series([100, 98, 96, 94, 92, 90, 88, 86, 84, 82])
        rsi = calculate_rsi_series(close, period=5)
        # Last RSI value should be low (below 30) in downtrend
        assert rsi.iloc[-1] < 30


class TestAddIndicatorColumns:
    """Tests for add_indicator_columns function."""

    @pytest.fixture
    def sample_df(self):
        """Create sample OHLCV dataframe."""
        np.random.seed(42)
        n = 100
        close = 100 + np.cumsum(np.random.randn(n) * 0.5)
        return pd.DataFrame({
            "open": close - np.random.rand(n) * 0.5,
            "high": close + np.random.rand(n) * 1.0,
            "low": close - np.random.rand(n) * 1.0,
            "close": close,
            "volume": np.random.randint(1000, 10000, n),
        })

    def test_adds_ema_columns(self, sample_df):
        """Should add EMA columns."""
        result = add_indicator_columns(sample_df, ema_lengths=(10, 20))
        assert "ema10" in result.columns
        assert "ema20" in result.columns

    def test_adds_rsi_columns(self, sample_df):
        """Should add RSI columns."""
        result = add_indicator_columns(sample_df, rsi_periods=(7, 14))
        assert "rsi7" in result.columns
        assert "rsi14" in result.columns

    def test_adds_macd_columns(self, sample_df):
        """Should add MACD columns."""
        result = add_indicator_columns(sample_df, macd_params=(12, 26, 9))
        assert "macd" in result.columns
        assert "macd_signal" in result.columns

    def test_returns_copy(self, sample_df):
        """Should return a copy, not modify original."""
        original_cols = list(sample_df.columns)
        result = add_indicator_columns(sample_df)
        assert list(sample_df.columns) == original_cols
        assert len(result.columns) > len(original_cols)

    def test_handles_duplicate_periods(self, sample_df):
        """Should handle duplicate periods gracefully."""
        result = add_indicator_columns(sample_df, ema_lengths=(20, 20, 20))
        # Should only have one ema20 column
        ema20_cols = [c for c in result.columns if c == "ema20"]
        assert len(ema20_cols) == 1

    def test_default_parameters(self, sample_df):
        """Should work with default parameters."""
        result = add_indicator_columns(sample_df)
        assert "ema20" in result.columns
        assert "rsi14" in result.columns
        assert "macd" in result.columns


class TestCalculateAtrSeries:
    """Tests for calculate_atr_series function."""

    @pytest.fixture
    def sample_ohlc(self):
        """Create sample OHLC dataframe."""
        return pd.DataFrame({
            "high": [110, 112, 115, 113, 116, 118, 117, 120, 119, 121],
            "low": [105, 108, 110, 108, 111, 113, 112, 115, 114, 116],
            "close": [108, 111, 113, 110, 114, 116, 115, 118, 117, 119],
        })

    def test_atr_returns_series(self, sample_ohlc):
        """Should return a pandas Series."""
        atr = calculate_atr_series(sample_ohlc, period=5)
        assert isinstance(atr, pd.Series)

    def test_atr_positive_values(self, sample_ohlc):
        """ATR should always be positive."""
        atr = calculate_atr_series(sample_ohlc, period=5)
        assert (atr.dropna() >= 0).all()

    def test_atr_length_matches_input(self, sample_ohlc):
        """ATR series should have same length as input."""
        atr = calculate_atr_series(sample_ohlc, period=5)
        assert len(atr) == len(sample_ohlc)

    def test_atr_reflects_volatility(self):
        """ATR should be higher for more volatile data."""
        # Low volatility
        low_vol = pd.DataFrame({
            "high": [101, 101, 101, 101, 101],
            "low": [99, 99, 99, 99, 99],
            "close": [100, 100, 100, 100, 100],
        })
        # High volatility
        high_vol = pd.DataFrame({
            "high": [110, 110, 110, 110, 110],
            "low": [90, 90, 90, 90, 90],
            "close": [100, 100, 100, 100, 100],
        })
        
        atr_low = calculate_atr_series(low_vol, period=3).iloc[-1]
        atr_high = calculate_atr_series(high_vol, period=3).iloc[-1]
        
        assert atr_high > atr_low


class TestCalculateIndicators:
    """Tests for calculate_indicators function."""

    @pytest.fixture
    def sample_df(self):
        """Create sample OHLCV dataframe."""
        np.random.seed(42)
        n = 50
        close = 100 + np.cumsum(np.random.randn(n) * 0.5)
        return pd.DataFrame({
            "open": close - np.random.rand(n) * 0.5,
            "high": close + np.random.rand(n) * 1.0,
            "low": close - np.random.rand(n) * 1.0,
            "close": close,
            "volume": np.random.randint(1000, 10000, n),
        })

    def test_returns_series(self, sample_df):
        """Should return a pandas Series."""
        result = calculate_indicators(
            sample_df,
            ema_len=20,
            rsi_len=14,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
        )
        assert isinstance(result, pd.Series)

    def test_returns_latest_row(self, sample_df):
        """Should return the latest row of indicators."""
        result = calculate_indicators(
            sample_df,
            ema_len=20,
            rsi_len=14,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
        )
        # Should have indicator values
        assert "ema20" in result.index
        assert "rsi" in result.index
        assert "macd" in result.index

    def test_rsi_alias_created(self, sample_df):
        """Should create 'rsi' alias for the specified RSI period."""
        result = calculate_indicators(
            sample_df,
            ema_len=20,
            rsi_len=7,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
        )
        assert "rsi" in result.index
        assert "rsi7" in result.index
        assert result["rsi"] == result["rsi7"]


class TestRoundSeries:
    """Tests for round_series function."""

    def test_rounds_to_precision(self):
        """Should round values to specified precision."""
        values = [1.23456, 2.34567, 3.45678]
        result = round_series(values, 2)
        assert result == [1.23, 2.35, 3.46]

    def test_skips_nan_values(self):
        """Should skip NaN values."""
        values = [1.5, float("nan"), 2.5]
        result = round_series(values, 1)
        assert result == [1.5, 2.5]

    def test_handles_empty_list(self):
        """Should handle empty list."""
        result = round_series([], 2)
        assert result == []

    def test_handles_pandas_series(self):
        """Should handle pandas Series."""
        values = pd.Series([1.234, 2.345, 3.456])
        result = round_series(values, 2)
        assert result == [1.23, 2.35, 3.46]

    def test_skips_non_numeric(self):
        """Should skip non-numeric values."""
        values = [1.5, "text", 2.5, None]
        result = round_series(values, 1)
        assert result == [1.5, 2.5]

    def test_handles_integers(self):
        """Should handle integer values."""
        values = [1, 2, 3]
        result = round_series(values, 2)
        assert result == [1.0, 2.0, 3.0]

    def test_precision_zero(self):
        """Should handle precision of zero."""
        values = [1.6, 2.4, 3.5]
        result = round_series(values, 0)
        assert result == [2.0, 2.0, 4.0]

    def test_handles_numpy_nan(self):
        """Should handle numpy NaN values."""
        values = [1.5, np.nan, 2.5]
        result = round_series(values, 1)
        assert result == [1.5, 2.5]
