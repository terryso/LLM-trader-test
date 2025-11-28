import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import bot
import backtest


class ProcessAiDecisionsTests(unittest.TestCase):
    def setUp(self) -> None:
        # Snapshot global state
        self._orig_positions = copy.deepcopy(bot.positions)

        # Patch side-effecting helpers so tests stay pure
        self._p_log_ai_decision = mock.patch("bot.log_ai_decision")
        self._p_fetch_market_data = mock.patch("bot.fetch_market_data")
        self._p_execute_entry = mock.patch("bot.execute_entry")
        self._p_execute_close = mock.patch("bot.execute_close")
        self._p_calc_unrealized = mock.patch("bot.calculate_unrealized_pnl")
        self._p_estimate_exit_fee = mock.patch("bot.estimate_exit_fee")
        self._p_calc_pnl_for_price = mock.patch("bot.calculate_pnl_for_price")
        self._p_record_iter_msg = mock.patch("bot.record_iteration_message")

        self.mock_log_ai_decision = self._p_log_ai_decision.start()
        self.mock_fetch_market_data = self._p_fetch_market_data.start()
        self.mock_execute_entry = self._p_execute_entry.start()
        self.mock_execute_close = self._p_execute_close.start()
        self.mock_calculate_unrealized_pnl = self._p_calc_unrealized.start()
        self.mock_estimate_exit_fee = self._p_estimate_exit_fee.start()
        self.mock_calculate_pnl_for_price = self._p_calc_pnl_for_price.start()
        self._p_record_iter_msg.start()

        # Default safe return values
        self.mock_fetch_market_data.return_value = {"price": 100.0}
        self.mock_calculate_unrealized_pnl.return_value = 0.0
        self.mock_estimate_exit_fee.return_value = 0.0
        self.mock_calculate_pnl_for_price.return_value = 0.0

    def tearDown(self) -> None:
        bot.positions = copy.deepcopy(self._orig_positions)

        for patcher in (
            self._p_log_ai_decision,
            self._p_fetch_market_data,
            self._p_execute_entry,
            self._p_execute_close,
            self._p_calc_unrealized,
            self._p_estimate_exit_fee,
            self._p_calc_pnl_for_price,
            self._p_record_iter_msg,
        ):
            patcher.stop()

    def test_entry_signal_calls_execute_entry_with_current_price(self) -> None:
        decisions = {
            "ETH": {
                "signal": "entry",
                "justification": "Buy the dip",
                "confidence": 0.9,
            }
        }
        self.mock_fetch_market_data.return_value = {"price": 123.45}

        bot.process_ai_decisions(decisions)

        self.mock_log_ai_decision.assert_any_call(
            "ETH", "entry", "Buy the dip", 0.9
        )
        self.mock_execute_entry.assert_called_once_with(
            "ETH", decisions["ETH"], 123.45
        )

    def test_close_signal_calls_execute_close_with_current_price(self) -> None:
        decisions = {
            "ETH": {
                "signal": "close",
                "justification": "Exit position",
                "confidence": 0.5,
            }
        }
        self.mock_fetch_market_data.return_value = {"price": 200.0}

        bot.process_ai_decisions(decisions)

        self.mock_log_ai_decision.assert_any_call(
            "ETH", "close", "Exit position", 0.5
        )
        self.mock_execute_close.assert_called_once_with(
            "ETH", decisions["ETH"], 200.0
        )

    def test_hold_updates_last_justification_when_provided(self) -> None:
        bot.positions = {
            "ETH": {
                "side": "long",
                "quantity": 1.0,
                "entry_price": 100.0,
                "last_justification": "old reason",
            }
        }
        decisions = {
            "ETH": {
                "signal": "hold",
                "justification": "   New   reason   with   spaces  ",
            }
        }
        self.mock_fetch_market_data.return_value = {"price": 110.0}

        bot.process_ai_decisions(decisions)

        self.assertEqual(
            bot.positions["ETH"]["last_justification"],
            "New reason with spaces",
        )

    def test_hold_sets_default_reason_when_missing_and_empty_existing(self) -> None:
        bot.positions = {
            "ETH": {
                "side": "long",
                "quantity": 1.0,
                "entry_price": 100.0,
                "last_justification": "",
            }
        }
        decisions = {"ETH": {"signal": "hold"}}
        self.mock_fetch_market_data.return_value = {"price": 100.0}

        bot.process_ai_decisions(decisions)

        self.assertEqual(
            bot.positions["ETH"]["last_justification"],
            "No justification provided.",
        )

    def test_hold_without_position_does_not_call_pnl_functions(self) -> None:
        bot.positions = {}
        decisions = {
            "ETH": {
                "signal": "hold",
                "justification": "Still watching",
            }
        }
        self.mock_fetch_market_data.return_value = {"price": 100.0}

        bot.process_ai_decisions(decisions)

        self.mock_calculate_unrealized_pnl.assert_not_called()
        self.mock_estimate_exit_fee.assert_not_called()
        self.mock_calculate_pnl_for_price.assert_not_called()


class BacktestHelpersTests(unittest.TestCase):
    def test_compute_max_drawdown_requires_enough_points(self) -> None:
        self.assertIsNone(backtest.compute_max_drawdown([]))
        self.assertIsNone(backtest.compute_max_drawdown([100.0]))

    def test_compute_max_drawdown_basic_scenario(self) -> None:
        # Equity path with a clear maximum drawdown from 150 → 80
        equity_values = [100.0, 120.0, 90.0, 150.0, 80.0]
        result = backtest.compute_max_drawdown(equity_values)
        expected = (150.0 - 80.0) / 150.0
        self.assertAlmostEqual(result, expected, places=6)

    def test_summarize_trades_empty_and_basic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Non-existent file → empty stats
            missing_stats = backtest.summarize_trades(tmp_path / "missing.csv")
            self.assertEqual(missing_stats["total_trades"], 0)
            self.assertEqual(missing_stats["closed_trades"], 0)
            self.assertEqual(missing_stats["net_realized_pnl"], 0.0)

            # Create a simple trade history with one entry and two closes
            trades_csv = tmp_path / "trades.csv"
            trades_csv.write_text(
                "timestamp,coin,action,pnl\n"
                "2024-01-01T00:00:00Z,BTC,ENTRY,\n"
                "2024-01-01T01:00:00Z,BTC,CLOSE,10\n"
                "2024-01-01T02:00:00Z,ETH,CLOSE,-5\n",
                encoding="utf-8",
            )

            stats = backtest.summarize_trades(trades_csv)
            self.assertEqual(stats["total_trades"], 1)
            self.assertEqual(stats["closed_trades"], 2)
            self.assertEqual(stats["winning_trades"], 1)
            self.assertEqual(stats["losing_trades"], 1)
            self.assertAlmostEqual(stats["win_rate_pct"], 50.0, places=6)
            self.assertAlmostEqual(stats["net_realized_pnl"], 5.0, places=6)


class BacktestCacheTests(unittest.TestCase):
    def _make_cfg(self, base_dir: Path, start: datetime, end: datetime, interval: str) -> backtest.BacktestConfig:
        return backtest.BacktestConfig(
            start=start,
            end=end,
            interval=interval,
            base_dir=base_dir,
            run_dir=base_dir / "run-1",
            cache_dir=base_dir / "cache",
            run_id="run-1",
            model=None,
            temperature=None,
            max_tokens=None,
            thinking=None,
            system_prompt=None,
            system_prompt_file=None,
            start_capital=None,
            disable_telegram=True,
        )

    def test_ensure_cached_klines_downloads_then_uses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            interval = "1h"
            start = datetime(2024, 1, 1, tzinfo=timezone.utc)
            end = start + timedelta(hours=3)
            cfg = self._make_cfg(base_dir, start, end, interval)
            # BacktestConfig.from_environment() normally creates these directories;
            # in tests we construct it manually, so ensure the cache dir exists.
            cfg.cache_dir.mkdir(parents=True, exist_ok=True)

            # Minimal klines: 3 rows matching KLINE_COLUMNS
            ts0 = int(start.timestamp() * 1000)
            ts1 = int((start + timedelta(hours=1)).timestamp() * 1000)
            ts2 = int((start + timedelta(hours=2)).timestamp() * 1000)
            row0 = [ts0, 100, 110, 90, 105, 1, ts0 + 1, 2, 3, 4, 5, 0]
            row1 = [ts1, 106, 112, 101, 110, 2, ts1 + 1, 3, 4, 5, 6, 0]
            row2 = [ts2, 111, 120, 108, 118, 3, ts2 + 1, 4, 5, 6, 7, 0]
            all_rows = [row0, row1, row2]

            class _StubClient:
                def __init__(self, rows):
                    self.rows = rows
                    self.calls = []

                def get_historical_klines(self, symbol, interval_arg, start_ms, end_ms):
                    self.calls.append((symbol, interval_arg, start_ms, end_ms))
                    return self.rows

            client = _StubClient(all_rows)

            # First call should hit the client and create cache file.
            df_first = backtest.ensure_cached_klines(client, cfg, "BTCUSDT", interval)
            self.assertEqual(len(client.calls), 1)
            cache_path = cfg.cache_dir / "BTCUSDT_1h.csv"
            self.assertTrue(cache_path.exists())
            self.assertEqual(len(df_first), 3)

    def test_ensure_cached_klines_uses_existing_cache_when_coverage_sufficient(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            interval = "1h"
            start = datetime(2024, 1, 1, tzinfo=timezone.utc)
            end = start + timedelta(hours=2)
            cfg = self._make_cfg(base_dir, start, end, interval)
            cfg.cache_dir.mkdir(parents=True, exist_ok=True)

            # Force warmup=0 for this interval so that coverage check only considers
            # [start, end] instead of a much earlier buffered window.
            with mock.patch.object(backtest, "WARMUP_BARS", {interval: 0}):
                ts_start = int(start.timestamp() * 1000)
                ts_end = int(end.timestamp() * 1000)

                import pandas as pd

                cached_df = pd.DataFrame(
                    [
                        [ts_start, 100, 110, 90, 105, 1, ts_start + 1, 2, 3, 4, 5, 0],
                        [ts_end, 106, 112, 101, 110, 2, ts_end + 1, 3, 4, 5, 6, 0],
                    ],
                    columns=backtest.KLINE_COLUMNS,
                )
                cache_path = cfg.cache_dir / "BTCUSDT_1h.csv"
                cached_df.to_csv(cache_path, index=False)

                class _StubClientNoCall:
                    def __init__(self):
                        self.calls = []

                    def get_historical_klines(self, *args, **kwargs):  # pragma: no cover - should not be called
                        self.calls.append((args, kwargs))
                        raise AssertionError("Client should not be called when cache coverage is sufficient")

                client = _StubClientNoCall()

                df = backtest.ensure_cached_klines(client, cfg, "BTCUSDT", interval)
                # All rows come from cache, and client was never called.
                self.assertEqual(len(df), 2)
                self.assertEqual(len(client.calls), 0)

    def test_historical_binance_client_get_klines_windowing(self) -> None:
        # Build a simple frame with 5 timestamps and verify window selection.
        timestamps = [1000, 2000, 3000, 4000, 5000]
        rows = []
        for i, ts in enumerate(timestamps):
            rows.append([
                ts,
                1 + i,
                2 + i,
                0.5 + i,
                1.5 + i,
                10 + i,
                ts + 1,
                20 + i,
                1,
                2,
                3,
                0,
            ])

        import pandas as pd

        df = pd.DataFrame(rows, columns=backtest.KLINE_COLUMNS)
        frames = {"BTCUSDT": {"1h": df}}
        client = backtest.HistoricalBinanceClient(frames)

        # Set current timestamp between 3000 and 4000 → index 2
        client.set_current_timestamp(3500)

        # limit=2 should return rows for timestamps [2000, 3000]
        klines = client.get_klines("BTCUSDT", "1h", limit=2)
        self.assertEqual(len(klines), 2)
        self.assertEqual(klines[0][0], 2000)
        self.assertEqual(klines[1][0], 3000)

        # limit larger than history should return from the first row up to current.
        klines_all = client.get_klines("BTCUSDT", "1h", limit=10)
        self.assertEqual(len(klines_all), 3)
        self.assertEqual(klines_all[0][0], 1000)
        self.assertEqual(klines_all[-1][0], 3000)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
