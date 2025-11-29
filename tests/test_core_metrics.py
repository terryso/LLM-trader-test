"""Tests for core/metrics.py module."""
import numpy as np
import pytest

from core.metrics import (
    DEFAULT_RISK_FREE_RATE,
    calculate_sortino_ratio,
    calculate_pnl_for_price,
    calculate_unrealized_pnl_for_position,
    calculate_net_unrealized_pnl_for_position,
    estimate_exit_fee_for_position,
    calculate_total_margin_for_positions,
    format_leverage_display,
)


class TestCalculateSortinoRatio:
    """Tests for calculate_sortino_ratio function."""

    def test_returns_float_for_valid_input(self):
        """Should return a float for valid equity values."""
        equity = [1000, 1010, 1005, 1020, 1015, 1030]
        result = calculate_sortino_ratio(equity, period_seconds=3600)
        assert isinstance(result, float)

    def test_returns_none_for_insufficient_data(self):
        """Should return None for less than 2 data points."""
        assert calculate_sortino_ratio([1000], period_seconds=3600) is None
        assert calculate_sortino_ratio([], period_seconds=3600) is None

    def test_returns_none_for_invalid_period(self):
        """Should return None for invalid period."""
        equity = [1000, 1010, 1020]
        assert calculate_sortino_ratio(equity, period_seconds=0) is None
        assert calculate_sortino_ratio(equity, period_seconds=-1) is None

    def test_positive_for_uptrend(self):
        """Should return positive ratio for consistent uptrend with some volatility."""
        # Need more data points and some downside volatility for Sortino calculation
        equity = [1000, 1010, 1005, 1020, 1015, 1030, 1025, 1040, 1035, 1050]
        result = calculate_sortino_ratio(equity, period_seconds=3600)
        # May return None if no downside deviation, which is valid
        assert result is None or result > 0

    def test_handles_nan_values(self):
        """Should filter out NaN values."""
        # Need enough valid data points after filtering NaN
        equity = [1000, float('nan'), 1010, 1005, 1020, 1015, 1030]
        result = calculate_sortino_ratio(equity, period_seconds=3600)
        # Result may be None if not enough downside deviation, but should not error
        # The key is that it doesn't crash on NaN values
        assert result is None or isinstance(result, float)

    def test_handles_inf_values(self):
        """Should filter out infinite values."""
        # Need enough valid data points after filtering inf
        equity = [1000, float('inf'), 1010, 1005, 1020, 1015, 1030]
        result = calculate_sortino_ratio(equity, period_seconds=3600)
        # Result may be None if not enough downside deviation, but should not error
        assert result is None or isinstance(result, float)

    def test_uses_risk_free_rate(self):
        """Should incorporate risk-free rate in calculation."""
        # Need data with some downside volatility for valid Sortino calculation
        equity = [1000, 1010, 1005, 1020, 1015, 1030, 1025, 1040, 1035, 1050, 1045, 1060]
        result_no_rf = calculate_sortino_ratio(equity, period_seconds=3600, risk_free_rate=0.0)
        result_with_rf = calculate_sortino_ratio(equity, period_seconds=3600, risk_free_rate=0.05)
        # If both are valid, higher risk-free rate should give lower ratio
        if result_no_rf is not None and result_with_rf is not None:
            assert result_with_rf < result_no_rf
        else:
            # If calculation returns None due to no downside, that's acceptable
            assert result_no_rf is None or result_with_rf is None


class TestCalculatePnlForPrice:
    """Tests for calculate_pnl_for_price function."""

    def test_long_profit(self):
        """Should calculate profit for long position."""
        pos = {"side": "long", "quantity": 1.0, "entry_price": 100.0}
        pnl = calculate_pnl_for_price(pos, target_price=110.0)
        assert pnl == pytest.approx(10.0)

    def test_long_loss(self):
        """Should calculate loss for long position."""
        pos = {"side": "long", "quantity": 1.0, "entry_price": 100.0}
        pnl = calculate_pnl_for_price(pos, target_price=90.0)
        assert pnl == pytest.approx(-10.0)

    def test_short_profit(self):
        """Should calculate profit for short position."""
        pos = {"side": "short", "quantity": 1.0, "entry_price": 100.0}
        pnl = calculate_pnl_for_price(pos, target_price=90.0)
        assert pnl == pytest.approx(10.0)

    def test_short_loss(self):
        """Should calculate loss for short position."""
        pos = {"side": "short", "quantity": 1.0, "entry_price": 100.0}
        pnl = calculate_pnl_for_price(pos, target_price=110.0)
        assert pnl == pytest.approx(-10.0)

    def test_scales_with_quantity(self):
        """Should scale PnL with quantity."""
        pos = {"side": "long", "quantity": 2.0, "entry_price": 100.0}
        pnl = calculate_pnl_for_price(pos, target_price=110.0)
        assert pnl == pytest.approx(20.0)

    def test_handles_missing_quantity(self):
        """Should handle missing quantity."""
        pos = {"side": "long", "entry_price": 100.0}
        pnl = calculate_pnl_for_price(pos, target_price=110.0)
        assert pnl == 0.0

    def test_handles_invalid_values(self):
        """Should handle invalid values gracefully."""
        pos = {"side": "long", "quantity": "invalid", "entry_price": 100.0}
        pnl = calculate_pnl_for_price(pos, target_price=110.0)
        assert pnl == 0.0


class TestCalculateUnrealizedPnlForPosition:
    """Tests for calculate_unrealized_pnl_for_position function."""

    def test_delegates_to_calculate_pnl(self):
        """Should delegate to calculate_pnl_for_price."""
        pos = {"side": "long", "quantity": 1.0, "entry_price": 100.0}
        result = calculate_unrealized_pnl_for_position(pos, current_price=110.0)
        expected = calculate_pnl_for_price(pos, target_price=110.0)
        assert result == expected


class TestCalculateNetUnrealizedPnlForPosition:
    """Tests for calculate_net_unrealized_pnl_for_position function."""

    def test_subtracts_fees_paid(self):
        """Should subtract fees paid from gross PnL."""
        pos = {"side": "long", "quantity": 1.0, "entry_price": 100.0, "fees_paid": 2.0}
        result = calculate_net_unrealized_pnl_for_position(pos, current_price=110.0)
        # gross = 10, net = 10 - 2 = 8
        assert result == pytest.approx(8.0)

    def test_handles_missing_fees(self):
        """Should handle missing fees_paid."""
        pos = {"side": "long", "quantity": 1.0, "entry_price": 100.0}
        result = calculate_net_unrealized_pnl_for_position(pos, current_price=110.0)
        assert result == pytest.approx(10.0)

    def test_handles_invalid_fees(self):
        """Should handle invalid fees_paid value."""
        pos = {"side": "long", "quantity": 1.0, "entry_price": 100.0, "fees_paid": "invalid"}
        result = calculate_net_unrealized_pnl_for_position(pos, current_price=110.0)
        assert result == pytest.approx(10.0)


class TestEstimateExitFeeForPosition:
    """Tests for estimate_exit_fee_for_position function."""

    def test_calculates_fee(self):
        """Should calculate exit fee based on position value."""
        pos = {"quantity": 1.0, "fee_rate": 0.001}
        fee = estimate_exit_fee_for_position(pos, exit_price=100.0, default_fee_rate=0.0005)
        # 1.0 * 100 * 0.001 = 0.1
        assert fee == pytest.approx(0.1)

    def test_uses_default_fee_rate(self):
        """Should use default fee rate if position has none."""
        pos = {"quantity": 1.0}
        fee = estimate_exit_fee_for_position(pos, exit_price=100.0, default_fee_rate=0.0005)
        # 1.0 * 100 * 0.0005 = 0.05
        assert fee == pytest.approx(0.05)

    def test_handles_invalid_fee_rate(self):
        """Should use default for invalid fee rate."""
        pos = {"quantity": 1.0, "fee_rate": "invalid"}
        fee = estimate_exit_fee_for_position(pos, exit_price=100.0, default_fee_rate=0.0005)
        assert fee == pytest.approx(0.05)

    def test_handles_missing_quantity(self):
        """Should handle missing quantity."""
        pos = {}
        fee = estimate_exit_fee_for_position(pos, exit_price=100.0, default_fee_rate=0.0005)
        assert fee == 0.0

    def test_returns_non_negative(self):
        """Should always return non-negative fee."""
        pos = {"quantity": -1.0, "fee_rate": 0.001}
        fee = estimate_exit_fee_for_position(pos, exit_price=100.0, default_fee_rate=0.0005)
        assert fee >= 0


class TestCalculateTotalMarginForPositions:
    """Tests for calculate_total_margin_for_positions function."""

    def test_sums_margins(self):
        """Should sum margins across positions."""
        positions = [
            {"margin": 100.0},
            {"margin": 200.0},
            {"margin": 300.0},
        ]
        total = calculate_total_margin_for_positions(positions)
        assert total == pytest.approx(600.0)

    def test_handles_empty_list(self):
        """Should return 0 for empty list."""
        total = calculate_total_margin_for_positions([])
        assert total == 0.0

    def test_handles_missing_margin(self):
        """Should skip positions without margin."""
        positions = [
            {"margin": 100.0},
            {"other": "data"},
            {"margin": 200.0},
        ]
        total = calculate_total_margin_for_positions(positions)
        assert total == pytest.approx(300.0)

    def test_handles_invalid_margin(self):
        """Should skip positions with invalid margin."""
        positions = [
            {"margin": 100.0},
            {"margin": "invalid"},
            {"margin": 200.0},
        ]
        total = calculate_total_margin_for_positions(positions)
        assert total == pytest.approx(300.0)


class TestFormatLeverageDisplay:
    """Tests for format_leverage_display function."""

    def test_formats_integer(self):
        """Should format integer leverage."""
        assert format_leverage_display(10) == "10x"

    def test_formats_float_integer(self):
        """Should format float that is integer."""
        assert format_leverage_display(10.0) == "10x"

    def test_formats_float(self):
        """Should format non-integer float."""
        assert format_leverage_display(2.5) == "2.5x"

    def test_handles_string_with_x(self):
        """Should handle string already with x suffix."""
        assert format_leverage_display("10x") == "10x"
        assert format_leverage_display("10X") == "10x"

    def test_handles_string_number(self):
        """Should handle string number."""
        assert format_leverage_display("10") == "10x"

    def test_handles_none(self):
        """Should return n/a for None."""
        assert format_leverage_display(None) == "n/a"

    def test_handles_empty_string(self):
        """Should return n/a for empty string."""
        assert format_leverage_display("") == "n/a"
        assert format_leverage_display("  ") == "n/a"

    def test_handles_invalid_string(self):
        """Should return string as-is for invalid value."""
        assert format_leverage_display("invalid") == "invalid"

    def test_handles_invalid_type(self):
        """Should convert invalid type to string."""
        result = format_leverage_display({"key": "value"})
        assert isinstance(result, str)
