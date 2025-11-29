"""Tests for execution/routing.py module."""
import pytest

from execution.routing import (
    EntryPlan,
    ClosePlan,
    compute_entry_plan,
    compute_close_plan,
)


class TestComputeEntryPlan:
    """Tests for compute_entry_plan function."""

    @pytest.fixture
    def base_params(self):
        """Base parameters for entry plan computation."""
        return {
            "coin": "BTC",
            "decision": {
                "side": "long",
                "leverage": 10,
                "risk_usd": 100,
                "stop_loss": 49000,
                "profit_target": 52000,
                "liquidity": "taker",
                "justification": "Bullish momentum",
            },
            "current_price": 50000,
            "balance": 10000,
            "is_live_backend": False,
            "live_max_leverage": 20,
            "live_max_risk_usd": 500,
            "live_max_margin_usd": 1000,
            "maker_fee_rate": 0.0002,
            "taker_fee_rate": 0.0005,
        }

    def test_returns_entry_plan(self, base_params):
        """Should return an EntryPlan object."""
        result = compute_entry_plan(**base_params)
        assert isinstance(result, EntryPlan)

    def test_calculates_quantity_from_risk(self, base_params):
        """Should calculate quantity based on risk and stop distance."""
        result = compute_entry_plan(**base_params)
        # risk_usd = 100, stop_distance = 50000 - 49000 = 1000
        # quantity = 100 / 1000 = 0.1
        assert result.quantity == pytest.approx(0.1)

    def test_calculates_margin_required(self, base_params):
        """Should calculate margin required based on leverage."""
        result = compute_entry_plan(**base_params)
        # quantity = 0.1, price = 50000, position_value = 5000
        # margin = 5000 / 10 = 500
        assert result.margin_required == pytest.approx(500)

    def test_calculates_entry_fee(self, base_params):
        """Should calculate entry fee."""
        result = compute_entry_plan(**base_params)
        # position_value = 5000, taker_fee = 0.0005
        # entry_fee = 5000 * 0.0005 = 2.5
        assert result.entry_fee == pytest.approx(2.5)

    def test_uses_maker_fee_for_maker_liquidity(self, base_params):
        """Should use maker fee rate for maker liquidity."""
        base_params["decision"]["liquidity"] = "maker"
        result = compute_entry_plan(**base_params)
        # position_value = 5000, maker_fee = 0.0002
        # entry_fee = 5000 * 0.0002 = 1.0
        assert result.entry_fee == pytest.approx(1.0)

    def test_returns_none_for_invalid_stop_loss_long(self, base_params):
        """Should return None if stop loss above current price for long."""
        base_params["decision"]["stop_loss"] = 51000  # Above current price
        result = compute_entry_plan(**base_params)
        assert result is None

    def test_returns_none_for_invalid_profit_target_long(self, base_params):
        """Should return None if profit target below current price for long."""
        base_params["decision"]["profit_target"] = 49000  # Below current price
        result = compute_entry_plan(**base_params)
        assert result is None

    def test_returns_none_for_invalid_stop_loss_short(self, base_params):
        """Should return None if stop loss below current price for short."""
        base_params["decision"]["side"] = "short"
        base_params["decision"]["stop_loss"] = 49000  # Below current price
        base_params["decision"]["profit_target"] = 48000
        result = compute_entry_plan(**base_params)
        assert result is None

    def test_returns_none_for_invalid_profit_target_short(self, base_params):
        """Should return None if profit target above current price for short."""
        base_params["decision"]["side"] = "short"
        base_params["decision"]["stop_loss"] = 51000
        base_params["decision"]["profit_target"] = 51000  # Above current price
        result = compute_entry_plan(**base_params)
        assert result is None

    def test_returns_none_for_insufficient_balance(self, base_params):
        """Should return None if balance insufficient for margin + fees."""
        base_params["balance"] = 100  # Not enough for margin
        result = compute_entry_plan(**base_params)
        assert result is None

    def test_caps_leverage_for_live_backend(self, base_params):
        """Should cap leverage for live backend."""
        base_params["is_live_backend"] = True
        base_params["decision"]["leverage"] = 50
        base_params["live_max_leverage"] = 20
        result = compute_entry_plan(**base_params)
        assert result.leverage == 20

    def test_caps_risk_for_live_backend(self, base_params):
        """Should cap risk_usd for live backend."""
        base_params["is_live_backend"] = True
        base_params["decision"]["risk_usd"] = 1000
        base_params["live_max_risk_usd"] = 500
        result = compute_entry_plan(**base_params)
        assert result.risk_usd <= 500

    def test_scales_down_for_margin_cap(self, base_params):
        """Should scale position down if margin exceeds cap."""
        base_params["is_live_backend"] = True
        base_params["decision"]["risk_usd"] = 1000
        base_params["live_max_margin_usd"] = 100
        result = compute_entry_plan(**base_params)
        assert result.margin_required <= 100

    def test_returns_none_for_contradictory_justification(self, base_params):
        """Should return None if justification contradicts entry signal."""
        base_params["decision"]["justification"] = "No entry recommended at this time"
        result = compute_entry_plan(**base_params)
        assert result is None

    def test_handles_missing_leverage(self, base_params):
        """Should handle missing leverage with default."""
        del base_params["decision"]["leverage"]
        result = compute_entry_plan(**base_params)
        assert result is not None

    def test_handles_invalid_leverage(self, base_params):
        """Should handle invalid leverage value."""
        base_params["decision"]["leverage"] = "invalid"
        result = compute_entry_plan(**base_params)
        assert result is not None
        assert result.leverage == 1.0

    def test_handles_zero_leverage(self, base_params):
        """Should handle zero leverage."""
        base_params["decision"]["leverage"] = 0
        result = compute_entry_plan(**base_params)
        assert result is not None
        assert result.leverage == 1.0

    def test_returns_none_for_zero_stop_distance(self, base_params):
        """Should return None if stop loss equals current price."""
        base_params["decision"]["stop_loss"] = 50000  # Same as current price
        result = compute_entry_plan(**base_params)
        assert result is None

    def test_stores_raw_reason(self, base_params):
        """Should store the raw justification."""
        result = compute_entry_plan(**base_params)
        assert result.raw_reason == "Bullish momentum"


class TestComputeClosePlan:
    """Tests for compute_close_plan function."""

    @pytest.fixture
    def base_params(self):
        """Base parameters for close plan computation."""
        return {
            "coin": "BTC",
            "decision": {
                "justification": "Take profit reached",
            },
            "current_price": 52000,
            "position": {
                "entry_price": 50000,
                "quantity": 0.1,
                "side": "long",
                "fee_rate": 0.0005,
                "fees_paid": 2.5,
                "last_justification": "Previous reason",
            },
            "pnl": 200,  # (52000 - 50000) * 0.1
            "default_fee_rate": 0.0005,
        }

    def test_returns_close_plan(self, base_params):
        """Should return a ClosePlan object."""
        result = compute_close_plan(**base_params)
        assert isinstance(result, ClosePlan)

    def test_calculates_exit_fee(self, base_params):
        """Should calculate exit fee."""
        result = compute_close_plan(**base_params)
        # quantity = 0.1, price = 52000, fee_rate = 0.0005
        # exit_fee = 0.1 * 52000 * 0.0005 = 2.6
        assert result.exit_fee == pytest.approx(2.6)

    def test_calculates_total_fees(self, base_params):
        """Should calculate total fees including entry fee."""
        result = compute_close_plan(**base_params)
        # fees_paid = 2.5, exit_fee = 2.6
        # total_fees = 5.1
        assert result.total_fees == pytest.approx(5.1)

    def test_calculates_net_pnl(self, base_params):
        """Should calculate net PnL after fees."""
        result = compute_close_plan(**base_params)
        # pnl = 200, total_fees = 5.1
        # net_pnl = 200 - 5.1 = 194.9
        assert result.net_pnl == pytest.approx(194.9)

    def test_uses_decision_justification(self, base_params):
        """Should use justification from decision."""
        result = compute_close_plan(**base_params)
        assert "Take profit reached" in result.reason_text

    def test_falls_back_to_position_justification(self, base_params):
        """Should fall back to position's last justification."""
        base_params["decision"]["justification"] = ""
        result = compute_close_plan(**base_params)
        assert "Previous reason" in result.reason_text

    def test_falls_back_to_default_reason(self, base_params):
        """Should fall back to default reason if no justification."""
        base_params["decision"]["justification"] = ""
        base_params["position"]["last_justification"] = ""
        result = compute_close_plan(**base_params)
        assert "AI close signal" in result.reason_text

    def test_uses_default_fee_rate(self, base_params):
        """Should use default fee rate if position has none."""
        del base_params["position"]["fee_rate"]
        result = compute_close_plan(**base_params)
        assert result.fee_rate == 0.0005

    def test_handles_missing_fees_paid(self, base_params):
        """Should handle missing fees_paid in position."""
        del base_params["position"]["fees_paid"]
        result = compute_close_plan(**base_params)
        # total_fees should just be exit_fee
        assert result.total_fees == pytest.approx(result.exit_fee)

    def test_stores_raw_reason(self, base_params):
        """Should store the raw justification."""
        result = compute_close_plan(**base_params)
        assert result.raw_reason == "Take profit reached"

    def test_normalizes_reason_text(self, base_params):
        """Should normalize whitespace in reason text."""
        base_params["decision"]["justification"] = "Multiple   spaces\n\nand newlines"
        result = compute_close_plan(**base_params)
        assert "  " not in result.reason_text
        assert "\n" not in result.reason_text
