import json
import importlib
import os
import unittest
from unittest import mock

from config.runtime_overrides import set_runtime_override, reset_runtime_overrides

import bot


class RecoverPartialDecisionsTests(unittest.TestCase):
    def test_recover_partial_decisions_recovers_existing_and_defaults_missing(self) -> None:
        # Build a JSON-like string that只包含 ETH 的完整对象，以及被截断的 SOL
        partial = {
            "ETH": {
                "signal": "entry",
                "side": "long",
                "quantity": 1.0,
                "profit_target": 1200.0,
                "stop_loss": 1100.0,
                "confidence": 0.9,
                "justification": "Buy the dip",
            },
        }
        json_str = json.dumps(partial, ensure_ascii=False)

        # 直接调用内部 helper
        recovery = bot._recover_partial_decisions(json_str)
        self.assertIsNotNone(recovery)
        assert recovery is not None
        decisions, missing = recovery

        # ETH 应该是原样恢复
        self.assertIn("ETH", decisions)
        self.assertEqual(decisions["ETH"]["signal"], "entry")
        self.assertEqual(decisions["ETH"]["side"], "long")

        # 所有 SYMBOL_TO_COIN 中的 coin 都应该在 decisions 里
        for coin in bot.SYMBOL_TO_COIN.values():
            self.assertIn(coin, decisions)

        # 不在 partial 里的币（例如 SOL、BTC 等）应该被默认填充为 HOLD
        for coin in missing:
            dec = decisions[coin]
            self.assertEqual(dec.get("signal"), "hold")
            self.assertIn("Missing data from truncated AI response", dec.get("justification", ""))
            self.assertEqual(dec.get("confidence"), 0.0)

    def test_recover_partial_decisions_returns_none_when_nothing_parsed(self) -> None:
        # 完全没有 coin key 的字符串
        json_str = "{\"foo\": 1}"
        self.assertIsNone(bot._recover_partial_decisions(json_str))


class CallDeepseekApiRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        # 确保有一个假 LLM_API_KEY，避免函数一开始就返回 None
        self._orig_env = os.environ.get("LLM_API_KEY")
        os.environ["LLM_API_KEY"] = "test-key"
        importlib.reload(bot)

    def tearDown(self) -> None:
        if self._orig_env is None:
            os.environ.pop("LLM_API_KEY", None)
        else:
            os.environ["LLM_API_KEY"] = self._orig_env
        importlib.reload(bot)
        reset_runtime_overrides()

    def test_call_deepseek_api_uses_recovery_on_json_decode_error(self) -> None:
        # 构造一个 choices[0].message.content，其中 JSON 格式有问题，触发 JSONDecodeError
        bad_json_content = "LLM explanation... {\"ETH\": {\"signal\": \"entry\",}} trailing text"

        # 通过 patch _recover_partial_decisions，验证它被调用并且结果被返回
        recovered_decisions = {"ETH": {"signal": "hold", "confidence": 0.0}}
        recovered_missing = ["BTC"]

        class _DummyResponse:
            status_code = 200

            def json(self_inner):
                return {
                    "id": "resp-1",
                    "usage": {},
                    "choices": [
                        {
                            "message": {"content": bad_json_content},
                            "finish_reason": "stop",
                        }
                    ],
                }

        with mock.patch("bot.requests.post", return_value=_DummyResponse()):
            with mock.patch("bot._recover_partial_decisions", return_value=(recovered_decisions, recovered_missing)) as mock_recover:
                with mock.patch("bot.notify_error") as mock_notify:
                    with mock.patch("bot.log_ai_message"):
                        with mock.patch("bot._log_llm_decisions") as mock_log_decisions:
                            decisions = bot.call_deepseek_api("prompt-text")

        # 确认触发了恢复逻辑
        mock_recover.assert_called_once()
        self.assertIsNotNone(decisions)
        assert decisions is not None
        self.assertEqual(decisions, recovered_decisions)

        # 应该记录 warning/notify，但这里我们只检查 notify_error 被调用
        self.assertTrue(mock_notify.called)
        mock_log_decisions.assert_called_once_with(recovered_decisions)

    def test_call_deepseek_api_uses_effective_temperature_override(self) -> None:
        # 设置 runtime override 的温度，并验证请求 payload 中的 temperature
        reset_runtime_overrides()
        set_runtime_override("TRADEBOT_LLM_TEMPERATURE", "1.5")

        class _DummyResponse:
            status_code = 200

            def json(self_inner):
                return {
                    "id": "resp-1",
                    "usage": {},
                    "choices": [
                        {
                            "message": {"content": '{"ETH": {"signal": "hold"}}'},
                            "finish_reason": "stop",
                        }
                    ],
                }

        with mock.patch("bot.requests.post", return_value=_DummyResponse()) as mock_post:
            with mock.patch("bot.notify_error") as mock_notify:
                with mock.patch("bot._log_llm_decisions"):
                    with mock.patch("bot.log_ai_message"):
                        decisions = bot.call_deepseek_api("prompt-text")

        # 不应该触发错误通知
        self.assertFalse(mock_notify.called)
        # 返回结果不为空（解析成功）
        self.assertIsNotNone(decisions)
        assert decisions is not None

        # 验证请求 payload 中的 temperature 已使用 override 值（1.5）
        payload = mock_post.call_args.kwargs["json"]
        self.assertIn("temperature", payload)
        self.assertEqual(payload["temperature"], 1.5)


class MarketDataBackendSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        # Snapshot current backend selection and cached client so tests stay isolated.
        self._orig_backend = bot.MARKET_DATA_BACKEND
        self._orig_client = bot._market_data_client

    def tearDown(self) -> None:
        bot.MARKET_DATA_BACKEND = self._orig_backend
        bot._market_data_client = self._orig_client

    def test_get_market_data_client_uses_binance_when_backend_binance(self) -> None:
        bot.MARKET_DATA_BACKEND = "binance"
        bot._market_data_client = None

        with mock.patch.object(bot, "get_binance_client") as mock_get_client:
            dummy_client = object()
            mock_get_client.return_value = dummy_client

            client = bot.get_market_data_client()

        self.assertIsNotNone(client)
        self.assertIsInstance(client, bot.BinanceMarketDataClient)

    def test_get_market_data_client_uses_backpack_when_backend_backpack(self) -> None:
        bot.MARKET_DATA_BACKEND = "backpack"
        bot._market_data_client = None

        client = bot.get_market_data_client()

        self.assertIsNotNone(client)
        self.assertIsInstance(client, bot.BackpackMarketDataClient)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
