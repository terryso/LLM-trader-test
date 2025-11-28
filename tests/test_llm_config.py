import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import bot


class LlmConfigurationRefreshTests(unittest.TestCase):
    def setUp(self) -> None:
        # Snapshot mutable globals that refresh_llm_configuration_from_env mutates.
        self._orig_globals = {
            "LLM_MODEL_NAME": bot.LLM_MODEL_NAME,
            "LLM_TEMPERATURE": bot.LLM_TEMPERATURE,
            "LLM_MAX_TOKENS": bot.LLM_MAX_TOKENS,
            "LLM_THINKING_PARAM": bot.LLM_THINKING_PARAM,
            "TRADING_RULES_PROMPT": bot.TRADING_RULES_PROMPT,
            "LLM_API_BASE_URL": bot.LLM_API_BASE_URL,
            "LLM_API_KEY": bot.LLM_API_KEY,
            "LLM_API_TYPE": bot.LLM_API_TYPE,
            "OPENROUTER_API_KEY": bot.OPENROUTER_API_KEY,
            "SYSTEM_PROMPT_SOURCE": dict(bot.SYSTEM_PROMPT_SOURCE),
        }

    def tearDown(self) -> None:
        # Restore globals to avoid leaking state across tests.
        bot.LLM_MODEL_NAME = self._orig_globals["LLM_MODEL_NAME"]
        bot.LLM_TEMPERATURE = self._orig_globals["LLM_TEMPERATURE"]
        bot.LLM_MAX_TOKENS = self._orig_globals["LLM_MAX_TOKENS"]
        bot.LLM_THINKING_PARAM = self._orig_globals["LLM_THINKING_PARAM"]
        bot.TRADING_RULES_PROMPT = self._orig_globals["TRADING_RULES_PROMPT"]
        bot.LLM_API_BASE_URL = self._orig_globals["LLM_API_BASE_URL"]
        bot.LLM_API_KEY = self._orig_globals["LLM_API_KEY"]
        bot.LLM_API_TYPE = self._orig_globals["LLM_API_TYPE"]
        bot.OPENROUTER_API_KEY = self._orig_globals["OPENROUTER_API_KEY"]
        bot.SYSTEM_PROMPT_SOURCE = dict(self._orig_globals["SYSTEM_PROMPT_SOURCE"])

    def test_refresh_uses_env_for_core_llm_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt_file = Path(tmpdir) / "ignored_prompt.txt"
            prompt_file.write_text("Should be ignored", encoding="utf-8")

            env = {
                "TRADEBOT_LLM_MODEL": "  my-provider/my-model  ",
                "TRADEBOT_LLM_TEMPERATURE": "0.25",
                "TRADEBOT_LLM_MAX_TOKENS": "2048",
                # thinking parameter as JSON to exercise parsing
                "TRADEBOT_LLM_THINKING": "{\"max_thoughts\": 5}",
                # System prompt text (file var also set but should be ignored in this test)
                "TRADEBOT_SYSTEM_PROMPT": "Inline system prompt",
                # This file is present but we will not set TRADEBOT_SYSTEM_PROMPT_FILE here
                # so text prompt takes precedence.
                "LLM_API_BASE_URL": "https://llm.example.com/v1",
                "LLM_API_KEY": "llm-key-123",
                "LLM_API_TYPE": "AZURE",
            }

            with mock.patch.dict(os.environ, env, clear=True):
                bot.refresh_llm_configuration_from_env()

            self.assertEqual(bot.LLM_MODEL_NAME, "my-provider/my-model")
            self.assertAlmostEqual(bot.LLM_TEMPERATURE, 0.25, places=6)
            self.assertEqual(bot.LLM_MAX_TOKENS, 2048)
            self.assertEqual(bot.LLM_THINKING_PARAM, {"max_thoughts": 5})

            self.assertEqual(bot.TRADING_RULES_PROMPT, "Inline system prompt")

            self.assertEqual(bot.LLM_API_BASE_URL, "https://llm.example.com/v1")
            self.assertEqual(bot.LLM_API_KEY, "llm-key-123")
            self.assertEqual(bot.LLM_API_TYPE, "azure")

    def test_refresh_prefers_system_prompt_file_over_env_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt_path = Path(tmpdir) / "prompt.txt"
            prompt_content = "File-based system prompt"
            prompt_path.write_text(prompt_content, encoding="utf-8")

            env = {
                "TRADEBOT_SYSTEM_PROMPT_FILE": str(prompt_path),
                "TRADEBOT_SYSTEM_PROMPT": "Inline that should not be used",
            }

            with mock.patch.dict(os.environ, env, clear=True):
                bot.refresh_llm_configuration_from_env()

            self.assertEqual(bot.TRADING_RULES_PROMPT, prompt_content)
            description = bot.describe_system_prompt_source()
            self.assertTrue(description.startswith("file:"))

    def test_refresh_uses_defaults_and_openrouter_key_when_env_missing(self) -> None:
        # Ensure OPENROUTER_API_KEY fallback is exercised.
        bot.OPENROUTER_API_KEY = "openrouter-fallback-key"

        with mock.patch.dict(os.environ, {}, clear=True):
            bot.refresh_llm_configuration_from_env()

        self.assertEqual(bot.LLM_MODEL_NAME, bot.DEFAULT_LLM_MODEL)
        self.assertAlmostEqual(bot.LLM_TEMPERATURE, 0.7, places=6)
        self.assertEqual(bot.LLM_MAX_TOKENS, 4000)
        self.assertIsNone(bot.LLM_THINKING_PARAM)

        self.assertEqual(bot.TRADING_RULES_PROMPT, bot.DEFAULT_TRADING_RULES_PROMPT)

        self.assertEqual(
            bot.LLM_API_BASE_URL,
            "https://openrouter.ai/api/v1/chat/completions",
        )
        self.assertEqual(bot.LLM_API_KEY, "openrouter-fallback-key")
        self.assertEqual(bot.LLM_API_TYPE, "openrouter")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
