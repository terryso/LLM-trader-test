import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import backtest


class BacktestConfigFromEnvironmentTests(unittest.TestCase):
    def test_from_environment_parses_full_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "BACKTEST_START": "2024-01-01T00:00:00Z",
                "BACKTEST_END": "2024-01-08T00:00:00Z",
                "BACKTEST_INTERVAL": "1h",
                "BACKTEST_DATA_DIR": tmpdir,
                "BACKTEST_RUN_ID": "test-run-123",
                "BACKTEST_LLM_MODEL": "gpt-4-backtest",
                "BACKTEST_TEMPERATURE": "0.5",
                "BACKTEST_MAX_TOKENS": "1024",
                "BACKTEST_LLM_THINKING": "detailed",
                "BACKTEST_SYSTEM_PROMPT": "Custom prompt",
                "BACKTEST_START_CAPITAL": "12345.67",
                "BACKTEST_DISABLE_TELEGRAM": "false",
            }

            with mock.patch.dict(os.environ, env, clear=True):
                cfg = backtest.BacktestConfig.from_environment()

                expected_start = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
                expected_end = datetime(2024, 1, 8, 0, 0, tzinfo=timezone.utc)

                self.assertEqual(cfg.start, expected_start)
                self.assertEqual(cfg.end, expected_end)
                self.assertEqual(cfg.end - cfg.start, expected_end - expected_start)

                self.assertEqual(cfg.interval, "1h")
                self.assertEqual(cfg.base_dir, Path(tmpdir))
                self.assertEqual(cfg.run_dir, Path(tmpdir) / "test-run-123")
                self.assertEqual(cfg.run_id, "test-run-123")

                self.assertEqual(cfg.model, "gpt-4-backtest")
                self.assertEqual(cfg.temperature, 0.5)
                self.assertEqual(cfg.max_tokens, 1024)
                self.assertEqual(cfg.thinking, "detailed")
                self.assertEqual(cfg.system_prompt, "Custom prompt")
                self.assertIsNone(cfg.system_prompt_file)
                self.assertEqual(cfg.start_capital, 12345.67)
                self.assertFalse(cfg.disable_telegram)

    def test_from_environment_invalid_interval_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "BACKTEST_INTERVAL": "weird-interval",
                "BACKTEST_DATA_DIR": tmpdir,
            }

            with mock.patch.dict(os.environ, env, clear=True):
                cfg = backtest.BacktestConfig.from_environment()

                self.assertEqual(cfg.interval, backtest.DEFAULT_INTERVAL)
                self.assertEqual(cfg.base_dir, Path(tmpdir))

    def test_from_environment_invalid_numeric_values_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "BACKTEST_DATA_DIR": tmpdir,
                "BACKTEST_TEMPERATURE": "not-a-float",
                "BACKTEST_MAX_TOKENS": "NaN",
                "BACKTEST_START_CAPITAL": "abc",
            }

            with mock.patch.dict(os.environ, env, clear=True):
                cfg = backtest.BacktestConfig.from_environment()

                self.assertIsNone(cfg.temperature)
                self.assertIsNone(cfg.max_tokens)
                self.assertIsNone(cfg.start_capital)

    def test_from_environment_resolves_relative_data_dir_against_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_project_root:
            rel_dir = "bt-data"
            env = {"BACKTEST_DATA_DIR": rel_dir}

            with mock.patch.object(backtest, "PROJECT_ROOT", Path(tmp_project_root)):
                with mock.patch.dict(os.environ, env, clear=True):
                    cfg = backtest.BacktestConfig.from_environment()

            expected_base = Path(tmp_project_root) / rel_dir
            # On macOS temporary directories may resolve via a /private/var symlink,
            # so compare resolved paths instead of raw strings.
            self.assertEqual(cfg.base_dir.resolve(), expected_base.resolve())
            self.assertTrue(cfg.base_dir.is_dir())


class ConfigureEnvironmentTests(unittest.TestCase):
    def _make_cfg(self, **overrides):
        base_dir = Path("/tmp/backtest-base")
        run_dir = base_dir / "run-1"
        cache_dir = base_dir / "cache"

        defaults = {
            "start": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "end": datetime(2024, 1, 8, tzinfo=timezone.utc),
            "interval": backtest.DEFAULT_INTERVAL,
            "base_dir": base_dir,
            "run_dir": run_dir,
            "cache_dir": cache_dir,
            "run_id": "run-1",
            "model": "gpt-4-backtest",
            "temperature": 0.5,
            "max_tokens": 1024,
            "thinking": "detailed",
            "system_prompt": "Inline prompt",
            "system_prompt_file": None,
            "start_capital": 10000.0,
            "disable_telegram": True,
        }
        defaults.update(overrides)
        return backtest.BacktestConfig(**defaults)

    def test_configure_environment_sets_core_and_llm_env_vars(self) -> None:
        cfg = self._make_cfg()

        env = {
            "BACKTEST_LLM_API_BASE_URL": "https://example.com/v1",
            "BACKTEST_LLM_API_KEY": "test-key",
            "BACKTEST_LLM_API_TYPE": "openai",
        }

        with mock.patch.dict(os.environ, env, clear=True):
            backtest.configure_environment(cfg)

            self.assertEqual(os.environ["TRADEBOT_DATA_DIR"], str(cfg.run_dir))
            self.assertEqual(os.environ["HYPERLIQUID_LIVE_TRADING"], "false")
            self.assertEqual(os.environ["PAPER_START_CAPITAL"], str(cfg.start_capital))

            self.assertEqual(os.environ["TRADEBOT_LLM_MODEL"], cfg.model)
            self.assertEqual(os.environ["TRADEBOT_LLM_TEMPERATURE"], str(cfg.temperature))
            self.assertEqual(os.environ["TRADEBOT_LLM_MAX_TOKENS"], str(cfg.max_tokens))
            self.assertEqual(os.environ["TRADEBOT_LLM_THINKING"], cfg.thinking)

            self.assertEqual(os.environ["TELEGRAM_BOT_TOKEN"], "")
            self.assertEqual(os.environ["TELEGRAM_CHAT_ID"], "")

            self.assertEqual(os.environ["LLM_API_BASE_URL"], "https://example.com/v1")
            self.assertEqual(os.environ["LLM_API_KEY"], "test-key")
            self.assertEqual(os.environ["LLM_API_TYPE"], "openai")

    def test_configure_environment_uses_system_prompt_file_and_clears_prompt_text(self) -> None:
        cfg = self._make_cfg(system_prompt_file="/tmp/prompt.txt", system_prompt=None)

        with mock.patch.dict(os.environ, {"TRADEBOT_SYSTEM_PROMPT": "old"}, clear=True):
            backtest.configure_environment(cfg)

            self.assertEqual(os.environ["TRADEBOT_SYSTEM_PROMPT_FILE"], "/tmp/prompt.txt")
            self.assertNotIn("TRADEBOT_SYSTEM_PROMPT", os.environ)

    def test_configure_environment_uses_system_prompt_text_and_clears_prompt_file(self) -> None:
        cfg = self._make_cfg(system_prompt="Inline", system_prompt_file=None)

        with mock.patch.dict(os.environ, {"TRADEBOT_SYSTEM_PROMPT_FILE": "/old/path"}, clear=True):
            backtest.configure_environment(cfg)

            self.assertEqual(os.environ["TRADEBOT_SYSTEM_PROMPT"], "Inline")
            self.assertNotIn("TRADEBOT_SYSTEM_PROMPT_FILE", os.environ)

    def test_configure_environment_leaves_telegram_when_not_disabled(self) -> None:
        cfg = self._make_cfg(disable_telegram=False)

        env = {
            "TELEGRAM_BOT_TOKEN": "token-123",
            "TELEGRAM_CHAT_ID": "chat-456",
        }

        with mock.patch.dict(os.environ, env, clear=True):
            backtest.configure_environment(cfg)

            self.assertEqual(os.environ["TELEGRAM_BOT_TOKEN"], "token-123")
            self.assertEqual(os.environ["TELEGRAM_CHAT_ID"], "chat-456")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
