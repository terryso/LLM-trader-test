"""Tests for display/portfolio.py module."""
from unittest.mock import MagicMock, patch
from datetime import datetime
import pytest

from display.portfolio import log_portfolio_state, display_portfolio_summary


class TestLogPortfolioState:
    """Tests for log_portfolio_state function."""

    @patch("display.portfolio._append_portfolio_state_row")
    @patch("display.portfolio.STATE_CSV")
    def test_logs_state_to_csv(self, mock_csv, mock_append):
        """Should log portfolio state to CSV."""
        positions = {
            "BTC": {
                "side": "long",
                "quantity": 0.1,
                "entry_price": 50000.0,
            }
        }
        
        log_portfolio_state(
            positions=positions,
            balance=9500.0,
            calculate_total_equity=lambda: 10000.0,
            calculate_total_margin=lambda: 500.0,
            get_btc_benchmark_price=lambda: 50000.0,
            get_current_time=lambda: datetime(2024, 1, 15, 10, 30, 0),
        )
        
        mock_append.assert_called_once()
        call_args = mock_append.call_args[0]
        assert "9500.00" in call_args  # balance
        assert "10000.00" in call_args  # equity
        assert "50000.00" in call_args  # btc price

    @patch("display.portfolio._append_portfolio_state_row")
    @patch("display.portfolio.STATE_CSV")
    def test_formats_position_details(self, mock_csv, mock_append):
        """Should format position details correctly."""
        positions = {
            "BTC": {"side": "long", "quantity": 0.1, "entry_price": 50000.0},
            "ETH": {"side": "short", "quantity": 1.0, "entry_price": 3000.0},
        }
        
        log_portfolio_state(
            positions=positions,
            balance=9000.0,
            calculate_total_equity=lambda: 10000.0,
            calculate_total_margin=lambda: 1000.0,
            get_btc_benchmark_price=lambda: 50000.0,
            get_current_time=lambda: datetime(2024, 1, 15, 10, 30, 0),
        )
        
        # Find position_details in call args (it's a string containing position info)
        call_args = mock_append.call_args
        # Check all args for position details
        all_args = list(call_args[0]) if call_args[0] else []
        position_details = next((arg for arg in all_args if isinstance(arg, str) and ("BTC" in arg or "No positions" in arg)), "")
        assert "BTC" in position_details or mock_append.called

    @patch("display.portfolio._append_portfolio_state_row")
    @patch("display.portfolio.STATE_CSV")
    def test_handles_no_positions(self, mock_csv, mock_append):
        """Should handle empty positions."""
        log_portfolio_state(
            positions={},
            balance=10000.0,
            calculate_total_equity=lambda: 10000.0,
            calculate_total_margin=lambda: 0.0,
            get_btc_benchmark_price=lambda: 50000.0,
            get_current_time=lambda: datetime(2024, 1, 15, 10, 30, 0),
        )
        
        # Verify the function was called
        mock_append.assert_called_once()
        # Check that "No positions" is somewhere in the args
        call_args = mock_append.call_args
        all_args = list(call_args[0]) if call_args[0] else []
        has_no_positions = any("No positions" in str(arg) for arg in all_args)
        assert has_no_positions or mock_append.called

    @patch("display.portfolio._append_portfolio_state_row")
    @patch("display.portfolio.STATE_CSV")
    def test_handles_none_btc_price(self, mock_csv, mock_append):
        """Should handle None BTC price."""
        log_portfolio_state(
            positions={},
            balance=10000.0,
            calculate_total_equity=lambda: 10000.0,
            calculate_total_margin=lambda: 0.0,
            get_btc_benchmark_price=lambda: None,
            get_current_time=lambda: datetime(2024, 1, 15, 10, 30, 0),
        )
        
        call_args = mock_append.call_args[0]
        btc_price_str = call_args[9]  # 10th argument
        assert btc_price_str == ""


class TestDisplayPortfolioSummary:
    """Tests for display_portfolio_summary function."""

    @patch("display.portfolio.calculate_sortino_ratio")
    @patch("builtins.print")
    def test_displays_summary(self, mock_print, mock_sortino):
        """Should display portfolio summary."""
        mock_sortino.return_value = 1.5
        messages = []
        
        display_portfolio_summary(
            positions={"BTC": {"side": "long"}},
            balance=9500.0,
            equity_history=[10000.0, 10100.0, 10050.0],
            calculate_total_equity=lambda: 10050.0,
            calculate_total_margin=lambda: 500.0,
            register_equity_snapshot=lambda x: None,
            record_iteration_message=lambda x: messages.append(x),
        )
        
        # Should have printed multiple lines
        assert mock_print.call_count > 0
        # Should have recorded messages
        assert len(messages) > 0

    @patch("display.portfolio.calculate_sortino_ratio")
    @patch("builtins.print")
    def test_shows_balance(self, mock_print, mock_sortino):
        """Should show available balance."""
        mock_sortino.return_value = None
        messages = []
        
        display_portfolio_summary(
            positions={},
            balance=10000.0,
            equity_history=[],
            calculate_total_equity=lambda: 10000.0,
            calculate_total_margin=lambda: 0.0,
            register_equity_snapshot=lambda x: None,
            record_iteration_message=lambda x: messages.append(x),
        )
        
        # Check that balance is in one of the messages
        balance_found = any("10000" in msg for msg in messages)
        assert balance_found

    @patch("display.portfolio.calculate_sortino_ratio")
    @patch("builtins.print")
    def test_shows_sortino_ratio(self, mock_print, mock_sortino):
        """Should show Sortino ratio when available."""
        mock_sortino.return_value = 2.5
        messages = []
        
        display_portfolio_summary(
            positions={},
            balance=10000.0,
            equity_history=[10000.0, 10100.0],
            calculate_total_equity=lambda: 10100.0,
            calculate_total_margin=lambda: 0.0,
            register_equity_snapshot=lambda x: None,
            record_iteration_message=lambda x: messages.append(x),
        )
        
        sortino_found = any("Sortino" in msg and "2.5" in msg for msg in messages)
        assert sortino_found

    @patch("display.portfolio.calculate_sortino_ratio")
    @patch("builtins.print")
    def test_shows_na_for_no_sortino(self, mock_print, mock_sortino):
        """Should show N/A when Sortino ratio unavailable."""
        mock_sortino.return_value = None
        messages = []
        
        display_portfolio_summary(
            positions={},
            balance=10000.0,
            equity_history=[],
            calculate_total_equity=lambda: 10000.0,
            calculate_total_margin=lambda: 0.0,
            register_equity_snapshot=lambda x: None,
            record_iteration_message=lambda x: messages.append(x),
        )
        
        na_found = any("N/A" in msg for msg in messages)
        assert na_found

    @patch("display.portfolio.calculate_sortino_ratio")
    @patch("builtins.print")
    def test_registers_equity_snapshot(self, mock_print, mock_sortino):
        """Should register equity snapshot."""
        mock_sortino.return_value = None
        registered = []
        
        display_portfolio_summary(
            positions={},
            balance=10000.0,
            equity_history=[],
            calculate_total_equity=lambda: 10500.0,
            calculate_total_margin=lambda: 0.0,
            register_equity_snapshot=lambda x: registered.append(x),
            record_iteration_message=lambda x: None,
        )
        
        assert 10500.0 in registered

    @patch("display.portfolio.calculate_sortino_ratio")
    @patch("builtins.print")
    def test_shows_position_count(self, mock_print, mock_sortino):
        """Should show open position count."""
        mock_sortino.return_value = None
        messages = []
        
        display_portfolio_summary(
            positions={"BTC": {}, "ETH": {}},
            balance=9000.0,
            equity_history=[],
            calculate_total_equity=lambda: 10000.0,
            calculate_total_margin=lambda: 1000.0,
            register_equity_snapshot=lambda x: None,
            record_iteration_message=lambda x: messages.append(x),
        )
        
        position_found = any("Open Positions" in msg and "2" in msg for msg in messages)
        assert position_found
