import copy
import unittest
from unittest import mock

import bot
import core.state as core_state


class CheckStopLossTakeProfitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_positions = copy.deepcopy(bot.positions)
        self._orig_hyperliquid_trader = bot.hyperliquid_trader

        class _DummyTrader:
            def __init__(self) -> None:
                self.is_live = False

        self._dummy_trader = _DummyTrader()
        bot.hyperliquid_trader = self._dummy_trader

        self._p_fetch_market_data = mock.patch("bot.fetch_market_data")
        self._p_execute_close = mock.patch("bot.execute_close")
        self._p_record_iter_msg = mock.patch("bot.record_iteration_message")

        self.mock_fetch_market_data = self._p_fetch_market_data.start()
        self.mock_execute_close = self._p_execute_close.start()
        self._p_record_iter_msg.start()

    def tearDown(self) -> None:
        bot.positions = copy.deepcopy(self._orig_positions)
        bot.hyperliquid_trader = self._orig_hyperliquid_trader

        for patcher in (
            self._p_fetch_market_data,
            self._p_execute_close,
            self._p_record_iter_msg,
        ):
            patcher.stop()

    def test_does_nothing_when_hyperliquid_live(self) -> None:
        self._dummy_trader.is_live = True
        bot.positions = {
            "ETH": {
                "side": "long",
                "entry_price": 100.0,
                "stop_loss": 90.0,
                "profit_target": 120.0,
            }
        }

        bot.check_stop_loss_take_profit()

        self.mock_fetch_market_data.assert_not_called()
        self.mock_execute_close.assert_not_called()

    def test_long_stop_loss_hit_triggers_close(self) -> None:
        self._dummy_trader.is_live = False
        bot.positions = {
            "ETH": {
                "side": "long",
                "entry_price": 100.0,
                "stop_loss": 90.0,
                "profit_target": 120.0,
            }
        }
        # Low 与 stop_loss 之下，先触发止损
        self.mock_fetch_market_data.return_value = {
            "price": 100.0,
            "low": 85.0,
            "high": 110.0,
        }

        bot.check_stop_loss_take_profit()

        self.mock_fetch_market_data.assert_called_once_with("ETHUSDT")
        self.mock_execute_close.assert_called_once_with(
            "ETH",
            {"justification": "Stop loss hit"},
            90.0,
        )

    def test_long_take_profit_hit_when_stop_not_hit(self) -> None:
        self._dummy_trader.is_live = False
        bot.positions = {
            "ETH": {
                "side": "long",
                "entry_price": 100.0,
                "stop_loss": 90.0,
                "profit_target": 120.0,
            }
        }
        # Low 在 stop_loss 之上，High 突破 profit_target → 止盈
        self.mock_fetch_market_data.return_value = {
            "price": 115.0,
            "low": 95.0,
            "high": 125.0,
        }

        bot.check_stop_loss_take_profit()

        self.mock_execute_close.assert_called_once_with(
            "ETH",
            {"justification": "Take profit hit"},
            120.0,
        )

    def test_short_stop_loss_hit_triggers_close(self) -> None:
        self._dummy_trader.is_live = False
        bot.positions = {
            "ETH": {
                "side": "short",
                "entry_price": 100.0,
                "stop_loss": 110.0,
                "profit_target": 80.0,
            }
        }
        # Short 仓位：High 触及 stop_loss → 止损
        self.mock_fetch_market_data.return_value = {
            "price": 105.0,
            "low": 90.0,
            "high": 115.0,
        }

        bot.check_stop_loss_take_profit()

        self.mock_execute_close.assert_called_once_with(
            "ETH",
            {"justification": "Stop loss hit"},
            110.0,
        )

    def test_short_take_profit_hit_when_stop_not_hit(self) -> None:
        self._dummy_trader.is_live = False
        bot.positions = {
            "ETH": {
                "side": "short",
                "entry_price": 100.0,
                "stop_loss": 110.0,
                "profit_target": 80.0,
            }
        }
        # High 未触及 stop_loss，Low 跌破 profit_target → 止盈
        self.mock_fetch_market_data.return_value = {
            "price": 90.0,
            "low": 75.0,
            "high": 105.0,
        }

        bot.check_stop_loss_take_profit()

        self.mock_execute_close.assert_called_once_with(
            "ETH",
            {"justification": "Take profit hit"},
            80.0,
        )

    def test_no_exit_when_neither_stop_nor_target_hit(self) -> None:
        self._dummy_trader.is_live = False
        bot.positions = {
            "ETH": {
                "side": "long",
                "entry_price": 100.0,
                "stop_loss": 90.0,
                "profit_target": 120.0,
            }
        }
        # High/Low 都在区间内，不触发任何退出
        self.mock_fetch_market_data.return_value = {
            "price": 100.0,
            "low": 95.0,
            "high": 110.0,
        }

        bot.check_stop_loss_take_profit()

        self.mock_execute_close.assert_not_called()

    def test_kill_switch_active_does_not_block_sl_tp_in_paper_mode(self) -> None:
        self._dummy_trader.is_live = False
        bot.positions = {
            "ETH": {
                "side": "long",
                "entry_price": 100.0,
                "stop_loss": 90.0,
                "profit_target": 120.0,
            }
        }
        self.mock_fetch_market_data.return_value = {
            "price": 100.0,
            "low": 85.0,
            "high": 110.0,
        }

        original_kill_switch = core_state.risk_control_state.kill_switch_active
        try:
            core_state.risk_control_state.kill_switch_active = True
            bot.check_stop_loss_take_profit()
        finally:
            core_state.risk_control_state.kill_switch_active = original_kill_switch

        self.mock_execute_close.assert_called_once_with(
            "ETH",
            {"justification": "Stop loss hit"},
            90.0,
        )

    def test_kill_switch_active_does_not_change_hyperliquid_live_noop(self) -> None:
        self._dummy_trader.is_live = True
        bot.positions = {
            "ETH": {
                "side": "long",
                "entry_price": 100.0,
                "stop_loss": 90.0,
                "profit_target": 120.0,
            }
        }

        original_kill_switch = core_state.risk_control_state.kill_switch_active
        try:
            core_state.risk_control_state.kill_switch_active = True
            bot.check_stop_loss_take_profit()
        finally:
            core_state.risk_control_state.kill_switch_active = original_kill_switch

        self.mock_fetch_market_data.assert_not_called()
        self.mock_execute_close.assert_not_called()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
