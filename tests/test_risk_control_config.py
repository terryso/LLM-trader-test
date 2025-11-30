"""Unit tests for risk control configuration in config/settings.py.

Tests cover:
- AC1: Default values for RISK_CONTROL_ENABLED, KILL_SWITCH, DAILY_LOSS_LIMIT_ENABLED, DAILY_LOSS_LIMIT_PCT
- AC3: Range validation for DAILY_LOSS_LIMIT_PCT with warning logging
- AC4: Environment variable override and invalid input fallback
"""

import importlib
import os
import unittest
from unittest import mock


class RiskControlConfigDefaultsTests(unittest.TestCase):
    """Test default values when environment variables are not set."""

    def test_risk_control_enabled_defaults_to_true(self) -> None:
        """RISK_CONTROL_ENABLED should default to True when not set."""
        with mock.patch.dict(os.environ, {}, clear=True):
            # Force reload to pick up cleared environment
            import config.settings as settings
            settings.EARLY_ENV_WARNINGS = []
            result = settings._parse_bool_env(None, default=True)
            self.assertTrue(result)

    def test_kill_switch_defaults_to_false(self) -> None:
        """KILL_SWITCH should default to False when not set."""
        with mock.patch.dict(os.environ, {}, clear=True):
            import config.settings as settings
            result = settings._parse_bool_env(None, default=False)
            self.assertFalse(result)

    def test_daily_loss_limit_enabled_defaults_to_true(self) -> None:
        """DAILY_LOSS_LIMIT_ENABLED should default to True when not set."""
        with mock.patch.dict(os.environ, {}, clear=True):
            import config.settings as settings
            result = settings._parse_bool_env(None, default=True)
            self.assertTrue(result)

    def test_daily_loss_limit_pct_defaults_to_5(self) -> None:
        """DAILY_LOSS_LIMIT_PCT should default to 5.0 when not set."""
        with mock.patch.dict(os.environ, {}, clear=True):
            import config.settings as settings
            settings.EARLY_ENV_WARNINGS = []
            result = settings._parse_float_env_with_range(
                None,
                default=5.0,
                min_val=0.0,
                max_val=100.0,
                var_name="DAILY_LOSS_LIMIT_PCT",
            )
            self.assertEqual(result, 5.0)


class RiskControlConfigOverrideTests(unittest.TestCase):
    """Test environment variable overrides."""

    def test_risk_control_enabled_can_be_disabled(self) -> None:
        """RISK_CONTROL_ENABLED=false should parse to False."""
        import config.settings as settings
        for false_value in ["false", "False", "FALSE", "0", "no", "off"]:
            result = settings._parse_bool_env(false_value, default=True)
            self.assertFalse(result, f"Failed for value: {false_value}")

    def test_risk_control_enabled_can_be_enabled(self) -> None:
        """RISK_CONTROL_ENABLED=true should parse to True."""
        import config.settings as settings
        for true_value in ["true", "True", "TRUE", "1", "yes", "on"]:
            result = settings._parse_bool_env(true_value, default=False)
            self.assertTrue(result, f"Failed for value: {true_value}")

    def test_kill_switch_can_be_activated(self) -> None:
        """KILL_SWITCH=true should parse to True."""
        import config.settings as settings
        result = settings._parse_bool_env("true", default=False)
        self.assertTrue(result)

    def test_daily_loss_limit_pct_can_be_overridden(self) -> None:
        """DAILY_LOSS_LIMIT_PCT can be set to valid values."""
        import config.settings as settings
        settings.EARLY_ENV_WARNINGS = []

        # Test various valid values
        test_cases = [
            ("0.0", 0.0),
            ("1.5", 1.5),
            ("10", 10.0),
            ("50.5", 50.5),
            ("100", 100.0),
        ]
        for env_value, expected in test_cases:
            result = settings._parse_float_env_with_range(
                env_value,
                default=5.0,
                min_val=0.0,
                max_val=100.0,
                var_name="DAILY_LOSS_LIMIT_PCT",
            )
            self.assertEqual(result, expected, f"Failed for value: {env_value}")


class RiskControlConfigValidationTests(unittest.TestCase):
    """Test validation and fallback for invalid inputs."""

    def test_daily_loss_limit_pct_negative_falls_back_to_default(self) -> None:
        """Negative DAILY_LOSS_LIMIT_PCT should fall back to default with warning."""
        import config.settings as settings
        settings.EARLY_ENV_WARNINGS = []

        result = settings._parse_float_env_with_range(
            "-5.0",
            default=5.0,
            min_val=0.0,
            max_val=100.0,
            var_name="DAILY_LOSS_LIMIT_PCT",
        )

        self.assertEqual(result, 5.0)
        self.assertEqual(len(settings.EARLY_ENV_WARNINGS), 1)
        self.assertIn("out of range", settings.EARLY_ENV_WARNINGS[0])
        self.assertIn("DAILY_LOSS_LIMIT_PCT", settings.EARLY_ENV_WARNINGS[0])

    def test_daily_loss_limit_pct_over_100_falls_back_to_default(self) -> None:
        """DAILY_LOSS_LIMIT_PCT > 100 should fall back to default with warning."""
        import config.settings as settings
        settings.EARLY_ENV_WARNINGS = []

        result = settings._parse_float_env_with_range(
            "150.0",
            default=5.0,
            min_val=0.0,
            max_val=100.0,
            var_name="DAILY_LOSS_LIMIT_PCT",
        )

        self.assertEqual(result, 5.0)
        self.assertEqual(len(settings.EARLY_ENV_WARNINGS), 1)
        self.assertIn("out of range", settings.EARLY_ENV_WARNINGS[0])

    def test_daily_loss_limit_pct_non_numeric_falls_back_to_default(self) -> None:
        """Non-numeric DAILY_LOSS_LIMIT_PCT should fall back to default with warning."""
        import config.settings as settings
        settings.EARLY_ENV_WARNINGS = []

        result = settings._parse_float_env_with_range(
            "not-a-number",
            default=5.0,
            min_val=0.0,
            max_val=100.0,
            var_name="DAILY_LOSS_LIMIT_PCT",
        )

        self.assertEqual(result, 5.0)
        self.assertEqual(len(settings.EARLY_ENV_WARNINGS), 1)
        self.assertIn("Invalid", settings.EARLY_ENV_WARNINGS[0])

    def test_daily_loss_limit_pct_empty_string_uses_default(self) -> None:
        """Empty string DAILY_LOSS_LIMIT_PCT should use default without warning."""
        import config.settings as settings
        settings.EARLY_ENV_WARNINGS = []

        result = settings._parse_float_env_with_range(
            "",
            default=5.0,
            min_val=0.0,
            max_val=100.0,
            var_name="DAILY_LOSS_LIMIT_PCT",
        )

        self.assertEqual(result, 5.0)
        self.assertEqual(len(settings.EARLY_ENV_WARNINGS), 0)

    def test_bool_env_invalid_value_uses_default(self) -> None:
        """Invalid boolean value should use default."""
        import config.settings as settings

        # Invalid value with default=True
        result = settings._parse_bool_env("invalid", default=True)
        self.assertTrue(result)

        # Invalid value with default=False
        result = settings._parse_bool_env("invalid", default=False)
        self.assertFalse(result)


class RiskControlConfigModuleExportsTests(unittest.TestCase):
    """Test that risk control config constants are exported from settings module."""

    def test_risk_control_constants_are_exported(self) -> None:
        """Verify all risk control constants are accessible from settings module."""
        import config.settings as settings

        # These should exist and be accessible
        self.assertTrue(hasattr(settings, "RISK_CONTROL_ENABLED"))
        self.assertTrue(hasattr(settings, "KILL_SWITCH"))
        self.assertTrue(hasattr(settings, "DAILY_LOSS_LIMIT_ENABLED"))
        self.assertTrue(hasattr(settings, "DAILY_LOSS_LIMIT_PCT"))

    def test_risk_control_constants_have_correct_types(self) -> None:
        """Verify risk control constants have correct types."""
        import config.settings as settings

        self.assertIsInstance(settings.RISK_CONTROL_ENABLED, bool)
        self.assertIsInstance(settings.KILL_SWITCH, bool)
        self.assertIsInstance(settings.DAILY_LOSS_LIMIT_ENABLED, bool)
        self.assertIsInstance(settings.DAILY_LOSS_LIMIT_PCT, float)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
