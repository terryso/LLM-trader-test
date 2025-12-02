import unittest
from unittest import mock

from config.runtime_overrides import set_runtime_override, reset_runtime_overrides

import bot


class BackpackMarketDataClientTests(unittest.TestCase):
    def test_normalize_symbol_maps_binance_to_backpack(self) -> None:
        normalize = bot.BackpackMarketDataClient._normalize_symbol

        self.assertEqual(normalize("BTCUSDT"), "BTC_USDC_PERP")
        self.assertEqual(normalize(" btcusdt "), "BTC_USDC_PERP")
        # Already Backpack style should be returned unchanged
        self.assertEqual(normalize("BTC_USDC_PERP"), "BTC_USDC_PERP")
        # Non-USDT symbols are passed through
        self.assertEqual(normalize("ABCUSD"), "ABCUSD")
        # Empty input stays empty
        self.assertEqual(normalize(""), "")

    def test_get_klines_builds_params_and_maps_fields(self) -> None:
        client = bot.BackpackMarketDataClient(base_url="https://api.backpack.exchange")
        client._session = mock.Mock()

        fixed_now = 1_700_000_000
        interval = "15m"
        limit = 3
        seconds_per_bar = bot._INTERVAL_TO_SECONDS[interval]
        expected_start = fixed_now - seconds_per_bar * limit

        rows_json = [
            {
                "start": 1000,
                "end": 2000,
                "open": "1.0",
                "high": "2.0",
                "low": "0.5",
                "close": "1.5",
                "volume": "10",
                "quoteVolume": "20",
                "trades": 5,
            }
        ]

        mock_resp = mock.Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = rows_json
        client._session.get.return_value = mock_resp

        with mock.patch("bot.time.time", return_value=fixed_now):
            klines = client.get_klines("BTCUSDT", interval=interval, limit=limit)

        client._session.get.assert_called_once()
        _, kwargs = client._session.get.call_args
        params = kwargs["params"]
        self.assertEqual(params["symbol"], "BTC_USDC_PERP")
        self.assertEqual(params["interval"], interval)
        self.assertEqual(params["startTime"], expected_start)

        self.assertEqual(len(klines), 1)
        row = klines[0]
        # Verify basic field mapping order
        self.assertEqual(row[0], 1000)  # timestamp / start
        self.assertEqual(row[1], "1.0")  # open
        self.assertEqual(row[2], "2.0")  # high
        self.assertEqual(row[3], "0.5")  # low
        self.assertEqual(row[4], "1.5")  # close
        self.assertEqual(row[5], "10")  # volume
        self.assertEqual(row[6], 2000)  # end / close_time
        self.assertEqual(row[7], "20")  # quoteVolume
        self.assertEqual(row[8], 5)  # trades

    def test_get_klines_returns_empty_on_http_error(self) -> None:
        client = bot.BackpackMarketDataClient(base_url="https://api.backpack.exchange")
        client._session = mock.Mock()

        mock_resp = mock.Mock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"code": 400, "message": "Bad Request"}
        client._session.get.return_value = mock_resp

        with mock.patch("bot.time.time", return_value=1_700_000_000):
            klines = client.get_klines("BTCUSDT", interval="15m", limit=10)

        self.assertEqual(klines, [])

    def test_get_klines_returns_empty_on_exception(self) -> None:
        client = bot.BackpackMarketDataClient(base_url="https://api.backpack.exchange")
        client._session = mock.Mock()
        client._session.get.side_effect = RuntimeError("network error")

        with mock.patch("bot.time.time", return_value=1_700_000_000):
            klines = client.get_klines("BTCUSDT", interval="15m", limit=10)

        self.assertEqual(klines, [])

    def test_get_funding_rate_history_parses_single_value(self) -> None:
        client = bot.BackpackMarketDataClient(base_url="https://api.backpack.exchange")

        client._get_mark_price_entry = lambda symbol: {"fundingRate": "0.001"}

        result = client.get_funding_rate_history("BTCUSDT", limit=10)
        self.assertEqual(result, [0.001])

    def test_get_funding_rate_history_handles_missing_or_invalid(self) -> None:
        client = bot.BackpackMarketDataClient(base_url="https://api.backpack.exchange")

        client._get_mark_price_entry = lambda symbol: None
        self.assertEqual(client.get_funding_rate_history("BTCUSDT", limit=10), [])

        client._get_mark_price_entry = lambda symbol: {"fundingRate": "not-a-number"}
        self.assertEqual(client.get_funding_rate_history("BTCUSDT", limit=10), [])

    def test_get_open_interest_history_uses_latest_value(self) -> None:
        client = bot.BackpackMarketDataClient(base_url="https://api.backpack.exchange")
        client._session = mock.Mock()

        mock_resp = mock.Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"openInterest": "1.0"},
            {"openInterest": "2.5"},
        ]
        client._session.get.return_value = mock_resp

        values = client.get_open_interest_history("BTCUSDT", limit=10)
        self.assertEqual(values, [2.5])

    def test_get_open_interest_history_handles_invalid_payload(self) -> None:
        client = bot.BackpackMarketDataClient(base_url="https://api.backpack.exchange")
        client._session = mock.Mock()

        # Non-dict payload
        mock_resp = mock.Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = "not-json-list"
        client._session.get.return_value = mock_resp

        values = client.get_open_interest_history("BTCUSDT", limit=10)
        self.assertEqual(values, [])


class FetchMarketDataTests(unittest.TestCase):
    def test_fetch_market_data_returns_none_when_client_unavailable(self) -> None:
        with mock.patch("bot.get_market_data_client", return_value=None):
            result = bot.fetch_market_data("BTCUSDT")
        self.assertIsNone(result)

    def test_fetch_market_data_returns_none_when_no_klines(self) -> None:
        class _StubClient:
            def get_klines(self, symbol, interval, limit):
                return []

            def get_funding_rate_history(self, symbol, limit):
                return []

        with mock.patch("bot.get_market_data_client", return_value=_StubClient()):
            result = bot.fetch_market_data("BTCUSDT")
        self.assertIsNone(result)

    def test_fetch_market_data_happy_path_uses_latest_close_and_funding(self) -> None:
        # Minimal but structurally valid klines (timestamp, open, high, low, close, volume, ...)
        base_row = [
            1000,
            "1.0",
            "2.0",
            "0.5",
            "1.5",
            "10.0",
            2000,
            "20.0",
            5,
            None,
            None,
            None,
        ]
        klines = [list(base_row) for _ in range(30)]

        class _StubClient:
            def get_klines(self, symbol, interval, limit):
                return klines

            def get_funding_rate_history(self, symbol, limit):
                return [0.001]

        with mock.patch("bot.get_market_data_client", return_value=_StubClient()):
            result = bot.fetch_market_data("BTCUSDT")

        self.assertIsNotNone(result)
        assert result is not None  # for type checkers
        self.assertEqual(result["symbol"], "BTCUSDT")
        self.assertAlmostEqual(result["price"], 1.5)
        self.assertAlmostEqual(result["high"], 2.0)
        self.assertAlmostEqual(result["low"], 0.5)
        self.assertAlmostEqual(result["funding_rate"], 0.001)


class CollectPromptMarketDataTests(unittest.TestCase):
    def _make_kline_rows(self, n: int) -> list[list[object]]:
        rows = []
        for i in range(n):
            rows.append(
                [
                    1000 + i,
                    "1.0",
                    "2.0",
                    "0.5",
                    "1.5",
                    "10.0",
                    2000 + i,
                    "20.0",
                    5,
                    None,
                    None,
                    None,
                ]
            )
        return rows

    def test_collect_prompt_market_data_returns_none_when_execution_klines_empty(self) -> None:
        class _StubClient:
            def get_klines(self, symbol, interval, limit):
                # Execution timeframe uses bot.INTERVAL
                if interval == bot.INTERVAL:
                    return []
                return self._make_kline_rows(5)

            def get_open_interest_history(self, symbol, limit):
                return []

            def get_funding_rate_history(self, symbol, limit):
                return []

            def _make_kline_rows(self_inner, n):
                return CollectPromptMarketDataTests()._make_kline_rows(n)

        with mock.patch("bot.get_market_data_client", return_value=_StubClient()):
            result = bot.collect_prompt_market_data("BTCUSDT")
        self.assertIsNone(result)

    def test_collect_prompt_market_data_returns_none_when_structure_klines_empty(self) -> None:
        class _StubClient:
            def get_klines(self, symbol, interval, limit):
                if interval == "1h":
                    return []
                return CollectPromptMarketDataTests()._make_kline_rows(5)

            def get_open_interest_history(self, symbol, limit):
                return []

            def get_funding_rate_history(self, symbol, limit):
                return []

        with mock.patch("bot.get_market_data_client", return_value=_StubClient()):
            result = bot.collect_prompt_market_data("BTCUSDT")
        self.assertIsNone(result)

    def test_collect_prompt_market_data_returns_none_when_trend_klines_empty(self) -> None:
        class _StubClient:
            def get_klines(self, symbol, interval, limit):
                if interval == "4h":
                    return []
                return CollectPromptMarketDataTests()._make_kline_rows(5)

            def get_open_interest_history(self, symbol, limit):
                return []

            def get_funding_rate_history(self, symbol, limit):
                return []

        with mock.patch("bot.get_market_data_client", return_value=_StubClient()):
            result = bot.collect_prompt_market_data("BTCUSDT")
        self.assertIsNone(result)


class RuntimeIntervalIntegrationTests(unittest.TestCase):
    def tearDown(self) -> None:
        """Reset runtime overrides after each test to avoid side effects."""
        reset_runtime_overrides()

    def test_fetch_market_data_uses_effective_interval_override(self) -> None:
        """bot.fetch_market_data 应该使用 get_effective_interval 派生的 interval。"""
        # 设置 runtime override，将 TRADEBOT_INTERVAL 改为 1h
        reset_runtime_overrides()
        set_runtime_override("TRADEBOT_INTERVAL", "1h")

        captured: dict[str, str] = {}

        class _StubClient:
            def get_klines(self, symbol, interval, limit):
                captured["interval"] = interval
                # 返回一行最小但结构合法的 kline 数据
                return [
                    [
                        1000,
                        "1.0",
                        "2.0",
                        "0.5",
                        "1.5",
                        "10.0",
                        2000,
                        "20.0",
                        5,
                        None,
                        None,
                        None,
                    ]
                ]

            def get_funding_rate_history(self, symbol, limit):
                return [0.0]

        with mock.patch("bot.get_market_data_client", return_value=_StubClient()):
            result = bot.fetch_market_data("BTCUSDT")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(captured.get("interval"), "1h")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
