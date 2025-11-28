import copy
import unittest
from unittest import mock

import bot


class EntryAndCloseTests(unittest.TestCase):
    def setUp(self) -> None:
        """Snapshot and normalise global trading state for tests."""
        self._orig_positions = copy.deepcopy(bot.positions)
        self._orig_balance = bot.balance
        self._orig_backend = bot.TRADING_BACKEND
        self._orig_binance_live = bot.BINANCE_FUTURES_LIVE
        self._orig_hyperliquid_trader = bot.hyperliquid_trader

        # Force tests into pure paper mode (no live trading, no external IO).
        bot.TRADING_BACKEND = "paper"
        bot.BINANCE_FUTURES_LIVE = False

        class _DummyTrader:
            is_live = False

        bot.hyperliquid_trader = _DummyTrader()

        self._patchers = [
            mock.patch("bot.log_trade"),
            mock.patch("bot.save_state"),
            mock.patch("bot.send_telegram_message"),
            mock.patch("bot.record_iteration_message"),
        ]
        for patcher in self._patchers:
            patcher.start()

    def tearDown(self) -> None:
        """Restore global state and stop all patches."""
        bot.positions = copy.deepcopy(self._orig_positions)
        bot.balance = self._orig_balance
        bot.TRADING_BACKEND = self._orig_backend
        bot.BINANCE_FUTURES_LIVE = self._orig_binance_live
        bot.hyperliquid_trader = self._orig_hyperliquid_trader

        for patcher in reversed(self._patchers):
            patcher.stop()

    def test_execute_entry_skips_when_position_already_open(self) -> None:
        bot.balance = 1000.0
        bot.positions = {
            "BTC": {"side": "long", "quantity": 1.0, "entry_price": 100.0}
        }
        decision = {
            "side": "long",
            "stop_loss": 90.0,
            "profit_target": 110.0,
            "risk_usd": 10.0,
        }

        bot.execute_entry("BTC", decision, current_price=100.0)

        self.assertIn("BTC", bot.positions)
        self.assertEqual(bot.positions["BTC"]["quantity"], 1.0)
        self.assertEqual(bot.balance, 1000.0)

    def test_execute_entry_skips_when_justification_contradicts_signal(self) -> None:
        bot.balance = 1000.0
        bot.positions = {}
        decision = {
            "side": "long",
            "justification": "No entry due to conditions",
        }

        bot.execute_entry("BTC", decision, current_price=100.0)

        self.assertNotIn("BTC", bot.positions)
        self.assertEqual(bot.balance, 1000.0)

    def test_execute_entry_skips_on_non_positive_stop_or_target(self) -> None:
        bot.balance = 1000.0
        bot.positions = {}
        decision = {
            "side": "long",
            "stop_loss": 0.0,
            "profit_target": 110.0,
        }

        bot.execute_entry("BTC", decision, current_price=100.0)

        self.assertNotIn("BTC", bot.positions)
        self.assertEqual(bot.balance, 1000.0)

    def test_execute_entry_validates_price_geometry_for_long(self) -> None:
        bot.balance = 1000.0
        bot.positions = {}
        decision = {
            "side": "long",
            "stop_loss": 105.0,  # not below current price
            "profit_target": 110.0,
        }

        bot.execute_entry("BTC", decision, current_price=100.0)

        self.assertNotIn("BTC", bot.positions)
        self.assertEqual(bot.balance, 1000.0)

    def test_execute_entry_opens_position_and_debits_balance_in_paper_mode(self) -> None:
        bot.balance = 1000.0
        bot.positions = {}
        decision = {
            "side": "long",
            "stop_loss": 90.0,
            "profit_target": 110.0,
            "risk_usd": 20.0,
            "confidence": 0.7,
        }

        bot.execute_entry("BTC", decision, current_price=100.0)

        self.assertIn("BTC", bot.positions)
        pos = bot.positions["BTC"]
        self.assertEqual(pos["side"], "long")
        self.assertAlmostEqual(pos["entry_price"], 100.0)
        self.assertAlmostEqual(pos["quantity"], 2.0, places=6)
        self.assertAlmostEqual(pos["margin"], 20.0, places=6)
        self.assertAlmostEqual(pos["risk_usd"], 20.0, places=6)

        expected_entry_fee = pos["entry_price"] * pos["quantity"] * pos["fee_rate"]
        self.assertAlmostEqual(pos["fees_paid"], expected_entry_fee, places=6)

        expected_balance = 1000.0 - (pos["margin"] + pos["fees_paid"])
        self.assertAlmostEqual(bot.balance, expected_balance, places=6)

    def test_execute_close_no_position_does_nothing(self) -> None:
        bot.balance = 1000.0
        bot.positions = {}
        decision = {"justification": "close"}

        bot.execute_close("BTC", decision, current_price=120.0)

        self.assertEqual(bot.balance, 1000.0)
        self.assertEqual(bot.positions, {})

    def test_execute_close_returns_margin_and_net_pnl_in_paper_mode(self) -> None:
        bot.balance = 1000.0
        bot.positions = {
            "BTC": {
                "side": "long",
                "quantity": 1.0,
                "entry_price": 100.0,
                "margin": 50.0,
                "fees_paid": 1.0,
                "fee_rate": 0.001,
                "leverage": 2.0,
            }
        }

        current_price = 120.0

        bot.execute_close("BTC", {"justification": "AI close"}, current_price=current_price)

        # After close, position should be removed
        self.assertNotIn("BTC", bot.positions)

        # Manual expected balance calculation
        pnl = (current_price - 100.0) * 1.0
        exit_fee = 1.0 * current_price * 0.001
        total_fees = 1.0 + exit_fee
        net_pnl = pnl - total_fees
        expected_balance = 1000.0 + 50.0 + net_pnl

        self.assertAlmostEqual(bot.balance, expected_balance, places=6)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
