import copy
import tempfile
import unittest
from pathlib import Path

from unittest import mock

import numpy as np
import pandas as pd

import bot


class PnlAndEquityTests(unittest.TestCase):
    def setUp(self) -> None:
        """Preserve original global state in bot before each test."""
        self._orig_positions = copy.deepcopy(bot.positions)
        self._orig_balance = bot.balance
        self._orig_equity_history = list(bot.equity_history)

    def tearDown(self) -> None:
        """Restore original global state after each test."""
        bot.positions = copy.deepcopy(self._orig_positions)
        bot.balance = self._orig_balance
        bot.equity_history = list(self._orig_equity_history)

    def test_calculate_unrealized_pnl_long_and_short(self) -> None:
        bot.positions = {
            "BTC": {"side": "long", "entry_price": 100.0, "quantity": 2.0},
            "ETH": {"side": "short", "entry_price": 100.0, "quantity": 2.0},
        }

        # Long position: price up = profit, price down = loss
        self.assertEqual(bot.calculate_unrealized_pnl("BTC", 110.0), 20.0)
        self.assertEqual(bot.calculate_unrealized_pnl("BTC", 90.0), -20.0)

        # Short position: price down = profit, price up = loss
        self.assertEqual(bot.calculate_unrealized_pnl("ETH", 90.0), 20.0)
        self.assertEqual(bot.calculate_unrealized_pnl("ETH", 110.0), -20.0)

        # No position: PnL should be zero
        self.assertEqual(bot.calculate_unrealized_pnl("DOGE", 100.0), 0.0)

    def test_calculate_net_unrealized_pnl_subtracts_fees(self) -> None:
        bot.positions = {
            "BTC": {
                "side": "long",
                "entry_price": 100.0,
                "quantity": 1.0,
                "fees_paid": 1.5,
            }
        }

        # Gross PnL = (110 - 100) * 1 = 10, net = 10 - 1.5 = 8.5
        result = bot.calculate_net_unrealized_pnl("BTC", 110.0)
        self.assertEqual(result, 8.5)

        # Coin without a position should still return 0
        self.assertEqual(bot.calculate_net_unrealized_pnl("ETH", 110.0), 0.0)

    def test_calculate_pnl_for_price_long_and_short(self) -> None:
        long_pos = {"side": "long", "entry_price": 100.0, "quantity": 2.0}
        short_pos = {"side": "short", "entry_price": 100.0, "quantity": 2.0}

        # Long: target above entry = profit, below entry = loss
        self.assertEqual(bot.calculate_pnl_for_price(long_pos, 110.0), 20.0)
        self.assertEqual(bot.calculate_pnl_for_price(long_pos, 90.0), -20.0)

        # Short: target below entry = profit, above entry = loss
        self.assertEqual(bot.calculate_pnl_for_price(short_pos, 90.0), 20.0)
        self.assertEqual(bot.calculate_pnl_for_price(short_pos, 110.0), -20.0)

    def test_calculate_pnl_for_price_invalid_inputs_returns_zero(self) -> None:
        # Quantity that cannot be converted to float should be treated defensively as 0.0
        bad_pos = {"side": "long", "entry_price": 100.0, "quantity": "not-a-number"}
        self.assertEqual(bot.calculate_pnl_for_price(bad_pos, 110.0), 0.0)

    def test_estimate_exit_fee_uses_explicit_fee_rate(self) -> None:
        pos = {"quantity": 2.0, "fee_rate": 0.001}
        fee = bot.estimate_exit_fee(pos, 100.0)
        self.assertAlmostEqual(fee, 0.2)

    def test_estimate_exit_fee_defaults_to_taker_fee_rate(self) -> None:
        pos = {"quantity": 2.0}
        fee = bot.estimate_exit_fee(pos, 100.0)
        expected = 2.0 * 100.0 * bot.TAKER_FEE_RATE
        self.assertAlmostEqual(fee, expected)

    def test_estimate_exit_fee_never_negative(self) -> None:
        pos = {"quantity": 1.0, "fee_rate": 0.001}
        fee = bot.estimate_exit_fee(pos, -100.0)
        self.assertEqual(fee, 0.0)

    def test_calculate_total_margin_sums_position_margins(self) -> None:
        bot.positions = {
            "BTC": {"margin": 10.5},
            "ETH": {"margin": 20.0},
            # Missing margin should be treated as 0.0
            "DOGE": {},
        }

        total_margin = bot.calculate_total_margin()
        self.assertAlmostEqual(total_margin, 30.5)

    def test_register_equity_snapshot_appends_only_finite_values(self) -> None:
        bot.equity_history.clear()

        # Valid finite value should be appended
        bot.register_equity_snapshot(100.0)
        # None and non-finite values should be ignored
        bot.register_equity_snapshot(None)  # type: ignore[arg-type]
        bot.register_equity_snapshot(float("inf"))
        bot.register_equity_snapshot(float("nan"))

        self.assertEqual(bot.equity_history, [100.0])

    def test_load_equity_history_handles_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = Path(tmpdir) / "state_missing.csv"

            with mock.patch.object(bot, "STATE_CSV", missing_path):
                bot.equity_history = [1.0, 2.0]
                bot.load_equity_history()

            # When state CSV is missing, history should be cleared and remain empty
            self.assertEqual(bot.equity_history, [])

    def test_load_equity_history_populates_from_total_equity_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "portfolio_state.csv"
            # Include one invalid row that should be dropped by to_numeric(..., errors="coerce").
            state_path.write_text(
                "total_equity\n"
                "100\n"
                "110.5\n"
                "not-a-number\n"
                "90\n",
                encoding="utf-8",
            )

            with mock.patch.object(bot, "STATE_CSV", state_path):
                bot.equity_history = [999.0]
                bot.load_equity_history()

            self.assertEqual(bot.equity_history, [100.0, 110.5, 90.0])

    @mock.patch("bot.fetch_market_data")
    def test_calculate_total_equity_uses_balance_margin_and_unrealized_pnl(self, mock_fetch) -> None:
        # Set up a controlled portfolio state
        bot.balance = 1000.0
        bot.positions = {
            "BTC": {
                "side": "long",
                "entry_price": 90.0,
                "quantity": 1.0,
                "margin": 100.0,
            },
            # Coin without symbol mapping should be ignored by calculate_total_equity
            "FOO": {
                "side": "long",
                "entry_price": 50.0,
                "quantity": 1.0,
                "margin": 50.0,
            },
        }

        # BTC should map to BTCUSDT, and we feed a deterministic price
        mock_fetch.return_value = {"price": 100.0}

        total_equity = bot.calculate_total_equity()

        mock_fetch.assert_called_once_with("BTCUSDT")

        # Base = balance + total_margin = 1000 + (100 + 50) = 1150
        # Unrealized PnL for BTC = (100 - 90) * 1 = 10 → total = 1160
        self.assertAlmostEqual(total_equity, 1160.0)

    def test_calculate_sortino_ratio_requires_enough_data(self) -> None:
        self.assertIsNone(bot.calculate_sortino_ratio([], 60.0))
        self.assertIsNone(bot.calculate_sortino_ratio([100.0], 60.0))

    def test_calculate_sortino_ratio_positive_with_mixed_returns(self) -> None:
        # Include at least one negative return so downside deviation is non-zero
        equity_values = [100.0, 110.0, 90.0, 120.0]
        result = bot.calculate_sortino_ratio(equity_values, 60.0)

        self.assertIsInstance(result, float)
        self.assertGreater(result, 0.0)


class IndicatorTests(unittest.TestCase):
    def test_calculate_rsi_series_basic_properties(self) -> None:
        close = pd.Series([100, 101, 102, 103, 104], dtype=float)
        period = 3

        rsi = bot.calculate_rsi_series(close, period)

        self.assertEqual(len(rsi), len(close))
        # All finite values (if any) should lie within [0, 100]. For very short
        # series the implementation may legitimately return all-NaN.
        finite_mask = np.isfinite(rsi.to_numpy())
        if finite_mask.any():
            finite_values = rsi.to_numpy()[finite_mask]
            self.assertTrue(((finite_values >= 0) & (finite_values <= 100)).all())

    def test_add_indicator_columns_adds_expected_columns(self) -> None:
        close = pd.Series([100 + i for i in range(10)], dtype=float)
        df = pd.DataFrame({"close": close})

        # Use duplicate lengths to exercise de-duplication logic.
        result = bot.add_indicator_columns(
            df,
            ema_lengths=(3, 3, 5),
            rsi_periods=(2, 2, 4),
            macd_params=(bot.MACD_FAST, bot.MACD_SLOW, bot.MACD_SIGNAL),
        )

        for col in ("ema3", "ema5", "rsi2", "rsi4", "macd", "macd_signal"):
            self.assertIn(col, result.columns)
            self.assertEqual(len(result[col]), len(df))

        # macd should equal EMA_fast - EMA_slow computed with same parameters.
        ema_fast = close.ewm(span=bot.MACD_FAST, adjust=False).mean()
        ema_slow = close.ewm(span=bot.MACD_SLOW, adjust=False).mean()
        expected_macd = ema_fast - ema_slow

        np.testing.assert_allclose(
            result["macd"].to_numpy(),
            expected_macd.to_numpy(),
            rtol=1e-6,
            atol=1e-6,
        )

    def test_calculate_atr_series_matches_true_range_first_value(self) -> None:
        # Construct a tiny OHLC series where we can calculate TR manually.
        data = {
            "high": [10.0, 12.0, 11.0],
            "low": [8.0, 9.0, 10.0],
            "close": [9.0, 11.0, 10.5],
        }
        df = pd.DataFrame(data)
        period = 2

        atr = bot.calculate_atr_series(df, period)

        self.assertEqual(len(atr), len(df))
        # First TR is simply high-low for the first bar.
        first_tr = data["high"][0] - data["low"][0]
        self.assertAlmostEqual(atr.iloc[0], first_tr, places=6)

    def test_calculate_indicators_returns_latest_row_with_rsi_alias(self) -> None:
        # Simple price series to feed into calculate_indicators.
        df = pd.DataFrame(
            {
                "high": [10, 11, 12, 13, 14],
                "low": [9, 10, 11, 12, 13],
                "close": [9.5, 10.5, 11.5, 12.5, 13.5],
            },
            dtype=float,
        )

        latest = bot.calculate_indicators(df)

        # Should return a Series representing the last row with indicator columns.
        for col in (
            f"ema{bot.EMA_LEN}",
            f"rsi{bot.RSI_LEN}",
            "macd",
            "macd_signal",
            "rsi",
        ):
            self.assertIn(col, latest.index)

        # Convenience alias 'rsi' must match the period-specific RSI column,
        # accounting for the possibility that both are NaN for short histories.
        rsi_alias = latest["rsi"]
        rsi_periodic = latest[f"rsi{bot.RSI_LEN}"]
        if np.isnan(rsi_alias) and np.isnan(rsi_periodic):
            # Both NaN → considered equal
            return
        self.assertAlmostEqual(rsi_alias, rsi_periodic)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

