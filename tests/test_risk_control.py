"""Tests for core/risk_control.py module."""
import json
import logging
from datetime import datetime, timezone
from unittest import mock

import pytest

from core.risk_control import (
    RiskControlState,
    check_risk_limits,
    activate_kill_switch,
    deactivate_kill_switch,
    apply_kill_switch_env_override,
    update_daily_baseline,
    calculate_daily_loss_pct,
    check_daily_loss_limit,
)


class TestRiskControlStateDefaultValues:
    """Tests for RiskControlState default value initialization."""

    def test_default_values(self):
        """Should initialize with correct default values."""
        state = RiskControlState()

        assert state.kill_switch_active is False
        assert state.kill_switch_reason is None
        assert state.kill_switch_triggered_at is None
        assert state.daily_start_equity is None
        assert state.daily_start_date is None
        assert state.daily_loss_pct == 0.0
        assert state.daily_loss_triggered is False

    def test_custom_values(self):
        """Should accept custom values for all fields."""
        state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="Manual trigger",
            kill_switch_triggered_at="2025-11-30T12:00:00+00:00",
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
            daily_loss_pct=-3.5,
            daily_loss_triggered=False,
        )

        assert state.kill_switch_active is True
        assert state.kill_switch_reason == "Manual trigger"
        assert state.kill_switch_triggered_at == "2025-11-30T12:00:00+00:00"
        assert state.daily_start_equity == 10000.0
        assert state.daily_start_date == "2025-11-30"
        assert state.daily_loss_pct == -3.5
        assert state.daily_loss_triggered is False


class TestRiskControlStateToDict:
    """Tests for RiskControlState.to_dict() method."""

    def test_to_dict_default_values(self):
        """Should serialize default state to dictionary."""
        state = RiskControlState()
        result = state.to_dict()

        assert result == {
            "kill_switch_active": False,
            "kill_switch_reason": None,
            "kill_switch_triggered_at": None,
            "daily_start_equity": None,
            "daily_start_date": None,
            "daily_loss_pct": 0.0,
            "daily_loss_triggered": False,
        }

    def test_to_dict_custom_values(self):
        """Should serialize custom state to dictionary."""
        state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="Daily loss limit",
            kill_switch_triggered_at="2025-11-30T08:30:00+00:00",
            daily_start_equity=5000.0,
            daily_start_date="2025-11-30",
            daily_loss_pct=-5.2,
            daily_loss_triggered=True,
        )
        result = state.to_dict()

        assert result == {
            "kill_switch_active": True,
            "kill_switch_reason": "Daily loss limit",
            "kill_switch_triggered_at": "2025-11-30T08:30:00+00:00",
            "daily_start_equity": 5000.0,
            "daily_start_date": "2025-11-30",
            "daily_loss_pct": -5.2,
            "daily_loss_triggered": True,
        }

    def test_to_dict_json_serializable(self):
        """Should return a dictionary that can be serialized with json.dumps()."""
        state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="Test reason",
            daily_start_equity=1234.56,
        )
        result = state.to_dict()

        # Should not raise any exception
        json_str = json.dumps(result)
        assert isinstance(json_str, str)

        # Should be able to parse back
        parsed = json.loads(json_str)
        assert parsed == result


class TestRiskControlStateFromDict:
    """Tests for RiskControlState.from_dict() method."""

    def test_from_dict_complete(self):
        """Should deserialize from complete dictionary."""
        data = {
            "kill_switch_active": True,
            "kill_switch_reason": "API error",
            "kill_switch_triggered_at": "2025-11-30T10:00:00+00:00",
            "daily_start_equity": 8000.0,
            "daily_start_date": "2025-11-30",
            "daily_loss_pct": -2.5,
            "daily_loss_triggered": False,
        }
        state = RiskControlState.from_dict(data)

        assert state.kill_switch_active is True
        assert state.kill_switch_reason == "API error"
        assert state.kill_switch_triggered_at == "2025-11-30T10:00:00+00:00"
        assert state.daily_start_equity == 8000.0
        assert state.daily_start_date == "2025-11-30"
        assert state.daily_loss_pct == -2.5
        assert state.daily_loss_triggered is False

    def test_from_dict_missing_fields(self):
        """Should use default values for missing fields."""
        data = {
            "kill_switch_active": True,
            "kill_switch_reason": "Partial data",
        }
        state = RiskControlState.from_dict(data)

        # Provided fields
        assert state.kill_switch_active is True
        assert state.kill_switch_reason == "Partial data"

        # Missing fields should use defaults
        assert state.kill_switch_triggered_at is None
        assert state.daily_start_equity is None
        assert state.daily_start_date is None
        assert state.daily_loss_pct == 0.0
        assert state.daily_loss_triggered is False

    def test_from_dict_empty_dict(self):
        """Should handle empty dictionary gracefully."""
        state = RiskControlState.from_dict({})

        assert state.kill_switch_active is False
        assert state.kill_switch_reason is None
        assert state.kill_switch_triggered_at is None
        assert state.daily_start_equity is None
        assert state.daily_start_date is None
        assert state.daily_loss_pct == 0.0
        assert state.daily_loss_triggered is False

    def test_from_dict_extra_fields_ignored(self):
        """Should ignore extra fields not in the dataclass."""
        data = {
            "kill_switch_active": True,
            "unknown_field": "should be ignored",
            "another_extra": 12345,
        }
        state = RiskControlState.from_dict(data)

        assert state.kill_switch_active is True
        assert not hasattr(state, "unknown_field")
        assert not hasattr(state, "another_extra")


class TestRiskControlStateRoundtrip:
    """Tests for serialization/deserialization roundtrip."""

    def test_roundtrip_default_state(self):
        """Should preserve default state through roundtrip."""
        original = RiskControlState()
        serialized = original.to_dict()
        restored = RiskControlState.from_dict(serialized)

        assert restored.kill_switch_active == original.kill_switch_active
        assert restored.kill_switch_reason == original.kill_switch_reason
        assert restored.kill_switch_triggered_at == original.kill_switch_triggered_at
        assert restored.daily_start_equity == original.daily_start_equity
        assert restored.daily_start_date == original.daily_start_date
        assert restored.daily_loss_pct == original.daily_loss_pct
        assert restored.daily_loss_triggered == original.daily_loss_triggered

    def test_roundtrip_custom_state(self):
        """Should preserve custom state through roundtrip."""
        original = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="Daily loss limit reached: -5.50%",
            kill_switch_triggered_at="2025-11-30T14:30:00+00:00",
            daily_start_equity=12500.0,
            daily_start_date="2025-11-30",
            daily_loss_pct=-5.5,
            daily_loss_triggered=True,
        )
        serialized = original.to_dict()
        restored = RiskControlState.from_dict(serialized)

        assert restored.kill_switch_active == original.kill_switch_active
        assert restored.kill_switch_reason == original.kill_switch_reason
        assert restored.kill_switch_triggered_at == original.kill_switch_triggered_at
        assert restored.daily_start_equity == original.daily_start_equity
        assert restored.daily_start_date == original.daily_start_date
        assert restored.daily_loss_pct == original.daily_loss_pct
        assert restored.daily_loss_triggered == original.daily_loss_triggered

    def test_roundtrip_through_json(self):
        """Should preserve state through JSON serialization roundtrip."""
        original = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="Test JSON roundtrip",
            daily_start_equity=9999.99,
            daily_loss_pct=-1.23,
        )

        # Serialize to JSON string
        json_str = json.dumps(original.to_dict())

        # Deserialize from JSON string
        parsed = json.loads(json_str)
        restored = RiskControlState.from_dict(parsed)

        assert restored.kill_switch_active == original.kill_switch_active
        assert restored.kill_switch_reason == original.kill_switch_reason
        assert restored.daily_start_equity == original.daily_start_equity
        assert restored.daily_loss_pct == original.daily_loss_pct


class TestRiskControlStateImport:
    """Tests for module import and availability."""

    def test_import_from_core_module(self):
        """Should be importable from core module."""
        from core import RiskControlState as ImportedState

        state = ImportedState()
        assert state.kill_switch_active is False

    def test_import_from_risk_control_module(self):
        """Should be importable from core.risk_control module."""
        from core.risk_control import RiskControlState as DirectImport

        state = DirectImport()
        assert state.kill_switch_active is False


class TestActivateKillSwitch:
    """Tests for activate_kill_switch function."""

    def test_activate_from_inactive_state(self):
        """Should activate Kill-Switch and set reason and timestamp."""
        state = RiskControlState()
        triggered_at = datetime(2025, 11, 30, 12, 0, 0, tzinfo=timezone.utc)

        new_state = activate_kill_switch(state, reason="test:manual", triggered_at=triggered_at)

        assert new_state.kill_switch_active is True
        assert new_state.kill_switch_reason == "test:manual"
        assert new_state.kill_switch_triggered_at == "2025-11-30T12:00:00+00:00"
        # Original state should be unchanged
        assert state.kill_switch_active is False

    def test_activate_with_default_timestamp(self):
        """Should use current UTC time when triggered_at is None."""
        state = RiskControlState()

        new_state = activate_kill_switch(state, reason="env:KILL_SWITCH")

        assert new_state.kill_switch_active is True
        assert new_state.kill_switch_reason == "env:KILL_SWITCH"
        assert new_state.kill_switch_triggered_at is not None
        # Verify it's a valid ISO 8601 timestamp
        parsed = datetime.fromisoformat(new_state.kill_switch_triggered_at)
        assert parsed.tzinfo is not None

    def test_activate_preserves_daily_loss_fields(self):
        """Should not modify daily loss related fields."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
            daily_loss_pct=-3.5,
            daily_loss_triggered=False,
        )

        new_state = activate_kill_switch(state, reason="test:preserve")

        assert new_state.daily_start_equity == 10000.0
        assert new_state.daily_start_date == "2025-11-30"
        assert new_state.daily_loss_pct == -3.5
        assert new_state.daily_loss_triggered is False


class TestDeactivateKillSwitch:
    """Tests for deactivate_kill_switch function."""

    def test_deactivate_from_active_state(self):
        """Should deactivate Kill-Switch, set new reason, and preserve triggered_at."""
        state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="test:active",
            kill_switch_triggered_at="2025-11-30T10:00:00+00:00",
        )

        new_state = deactivate_kill_switch(state)

        assert new_state.kill_switch_active is False
        # AC1: reason should be set to deactivation reason (default: "runtime:resume")
        assert new_state.kill_switch_reason == "runtime:resume"
        # AC1: triggered_at should be preserved for audit trail
        assert new_state.kill_switch_triggered_at == "2025-11-30T10:00:00+00:00"
        # Original state should be unchanged
        assert state.kill_switch_active is True

    def test_deactivate_with_custom_reason(self):
        """Should accept custom deactivation reason."""
        state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="test:active",
            kill_switch_triggered_at="2025-11-30T10:00:00+00:00",
        )

        new_state = deactivate_kill_switch(state, reason="telegram:/resume")

        assert new_state.kill_switch_active is False
        assert new_state.kill_switch_reason == "telegram:/resume"
        assert new_state.kill_switch_triggered_at == "2025-11-30T10:00:00+00:00"

    def test_deactivate_logs_event_when_active(self, caplog):
        """Should log INFO when deactivating an active Kill-Switch (AC3)."""
        state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="test:active",
            kill_switch_triggered_at="2025-11-30T10:00:00+00:00",
            daily_loss_triggered=True,
        )

        with caplog.at_level(logging.INFO):
            deactivate_kill_switch(state, reason="runtime:resume", total_equity=9500.0)

        # Updated log format: "Kill-Switch state change" instead of "Kill-Switch deactivated"
        assert "Kill-Switch state change" in caplog.text
        assert "old_state=active" in caplog.text
        assert "new_state=inactive" in caplog.text
        assert "previous_reason=test:active" in caplog.text
        assert "deactivation_reason=runtime:resume" in caplog.text
        assert "daily_loss_triggered=True" in caplog.text
        assert "total_equity=9500.00" in caplog.text

    def test_deactivate_logs_debug_when_already_inactive(self, caplog):
        """Should log DEBUG when Kill-Switch is already inactive."""
        state = RiskControlState(kill_switch_active=False)

        with caplog.at_level(logging.DEBUG):
            deactivate_kill_switch(state, reason="runtime:resume")

        assert "already inactive" in caplog.text

    def test_deactivate_preserves_daily_loss_fields(self):
        """Should not modify daily loss related fields (AC1)."""
        state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="daily_loss",
            kill_switch_triggered_at="2025-11-30T10:00:00+00:00",
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
            daily_loss_pct=-5.0,
            daily_loss_triggered=True,
        )

        new_state = deactivate_kill_switch(state)

        assert new_state.daily_start_equity == 10000.0
        assert new_state.daily_start_date == "2025-11-30"
        assert new_state.daily_loss_pct == -5.0
        assert new_state.daily_loss_triggered is True


class TestApplyKillSwitchEnvOverride:
    """Tests for apply_kill_switch_env_override function (AC1 priority logic)."""

    def test_env_not_set_preserves_inactive_state(self):
        """When env var is not set, should preserve inactive state."""
        state = RiskControlState(kill_switch_active=False)

        new_state, overridden = apply_kill_switch_env_override(state, kill_switch_env=None)

        assert new_state.kill_switch_active is False
        assert overridden is False

    def test_env_not_set_preserves_active_state(self):
        """When env var is not set, should preserve active state from persistence."""
        state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="persisted:reason",
            kill_switch_triggered_at="2025-11-30T08:00:00+00:00",
        )

        new_state, overridden = apply_kill_switch_env_override(state, kill_switch_env=None)

        assert new_state.kill_switch_active is True
        assert new_state.kill_switch_reason == "persisted:reason"
        assert overridden is False

    @pytest.mark.parametrize("env_value", ["true", "True", "TRUE", "1", "yes", "on"])
    def test_env_true_activates_kill_switch(self, env_value):
        """KILL_SWITCH=true should activate Kill-Switch."""
        state = RiskControlState(kill_switch_active=False)

        new_state, overridden = apply_kill_switch_env_override(state, kill_switch_env=env_value)

        assert new_state.kill_switch_active is True
        assert new_state.kill_switch_reason == "env:KILL_SWITCH"
        assert new_state.kill_switch_triggered_at is not None
        assert overridden is True

    @pytest.mark.parametrize("env_value", ["false", "False", "FALSE", "0", "no", "off"])
    def test_env_false_deactivates_kill_switch(self, env_value):
        """KILL_SWITCH=false should deactivate Kill-Switch."""
        state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="persisted:reason",
            kill_switch_triggered_at="2025-11-30T08:00:00+00:00",
        )

        new_state, overridden = apply_kill_switch_env_override(state, kill_switch_env=env_value)

        assert new_state.kill_switch_active is False
        # AC1: reason should be set to env:KILL_SWITCH (deactivation reason)
        assert new_state.kill_switch_reason == "env:KILL_SWITCH"
        # AC1: triggered_at should be preserved for audit trail
        assert new_state.kill_switch_triggered_at == "2025-11-30T08:00:00+00:00"
        assert overridden is True

    def test_env_true_on_already_active_updates_reason(self):
        """KILL_SWITCH=true on already active state should update reason to env:KILL_SWITCH."""
        state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="persisted:reason",
            kill_switch_triggered_at="2025-11-30T08:00:00+00:00",
        )

        new_state, overridden = apply_kill_switch_env_override(state, kill_switch_env="true")

        assert new_state.kill_switch_active is True
        assert new_state.kill_switch_reason == "env:KILL_SWITCH"
        assert overridden is True

    def test_env_true_on_already_active_with_env_reason_no_change(self):
        """KILL_SWITCH=true on state already set by env should not report override."""
        state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="env:KILL_SWITCH",
            kill_switch_triggered_at="2025-11-30T08:00:00+00:00",
        )

        new_state, overridden = apply_kill_switch_env_override(state, kill_switch_env="true")

        assert new_state.kill_switch_active is True
        assert new_state.kill_switch_reason == "env:KILL_SWITCH"
        assert overridden is False

    def test_env_false_on_already_inactive_no_change(self):
        """KILL_SWITCH=false on inactive state should not report override."""
        state = RiskControlState(kill_switch_active=False)

        new_state, overridden = apply_kill_switch_env_override(state, kill_switch_env="false")

        assert new_state.kill_switch_active is False
        assert overridden is False

    def test_invalid_env_value_preserves_state(self, caplog):
        """Invalid env value should preserve state and log warning."""
        state = RiskControlState(kill_switch_active=False)

        with caplog.at_level(logging.WARNING):
            new_state, overridden = apply_kill_switch_env_override(state, kill_switch_env="invalid")

        assert new_state.kill_switch_active is False
        assert overridden is False
        assert "Invalid KILL_SWITCH environment variable value" in caplog.text


class TestCheckRiskLimitsKillSwitch:
    """Tests for check_risk_limits with Kill-Switch logic (AC2)."""

    def test_returns_true_when_kill_switch_inactive(self):
        """Should return True (allow entry) when Kill-Switch is inactive."""
        state = RiskControlState(kill_switch_active=False)

        result = check_risk_limits(
            risk_control_state=state,
            total_equity=10000.0,
            risk_control_enabled=True,
        )

        assert result is True

    def test_returns_false_when_kill_switch_active(self):
        """Should return False (block entry) when Kill-Switch is active."""
        state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="test:active",
            kill_switch_triggered_at="2025-11-30T10:00:00+00:00",
        )

        result = check_risk_limits(
            risk_control_state=state,
            total_equity=10000.0,
            risk_control_enabled=True,
        )

        assert result is False

    def test_returns_true_when_risk_control_disabled(self):
        """Should return True when RISK_CONTROL_ENABLED=False, even if Kill-Switch is active."""
        state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="test:active",
        )

        result = check_risk_limits(
            risk_control_state=state,
            total_equity=10000.0,
            risk_control_enabled=False,
        )

        assert result is True

    def test_logs_warning_when_kill_switch_active(self, caplog):
        """Should log warning when Kill-Switch is active."""
        state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="test:log",
            kill_switch_triggered_at="2025-11-30T10:00:00+00:00",
        )

        with caplog.at_level(logging.WARNING):
            check_risk_limits(
                risk_control_state=state,
                risk_control_enabled=True,
            )

        assert "Kill-Switch is active" in caplog.text
        assert "test:log" in caplog.text


class TestUpdateDailyBaseline:
    """Tests for update_daily_baseline helper (Story 7.3.1)."""

    def test_initializes_baseline_when_date_is_none(self, caplog):
        """Should initialize baseline when daily_start_date is None."""
        state = RiskControlState(
            daily_start_equity=None,
            daily_start_date=None,
            daily_loss_pct=-3.5,
            daily_loss_triggered=True,
        )
        current_equity = 10000.0

        with caplog.at_level(logging.INFO):
            update_daily_baseline(state, current_equity)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        assert state.daily_start_date == today
        assert state.daily_start_equity == current_equity
        assert state.daily_loss_pct == 0.0
        assert state.daily_loss_triggered is False
        assert "Daily baseline reset" in caplog.text
        assert f"equity={current_equity:.2f}" in caplog.text
        assert f"date={today}" in caplog.text

    def test_resets_baseline_when_date_changes(self, caplog):
        """Should reset baseline when stored date is different from today."""
        previous_date = "2000-01-01"
        state = RiskControlState(
            daily_start_equity=5000.0,
            daily_start_date=previous_date,
            daily_loss_pct=-5.0,
            daily_loss_triggered=True,
        )
        current_equity = 9500.0

        with caplog.at_level(logging.INFO):
            update_daily_baseline(state, current_equity)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        assert state.daily_start_date == today
        assert state.daily_start_equity == current_equity
        assert state.daily_loss_pct == 0.0
        assert state.daily_loss_triggered is False
        assert "Daily baseline reset" in caplog.text
        assert f"previous_date={previous_date}" in caplog.text

    def test_same_day_call_is_idempotent(self, caplog):
        """Calling helper multiple times on same day should not change baseline."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        state = RiskControlState(
            daily_start_equity=12345.0,
            daily_start_date=today,
            daily_loss_pct=-1.0,
            daily_loss_triggered=True,
        )
        current_equity = 9999.0

        with caplog.at_level(logging.DEBUG):
            update_daily_baseline(state, current_equity)

        assert state.daily_start_date == today
        assert state.daily_start_equity == 12345.0
        assert state.daily_loss_pct == -1.0
        assert state.daily_loss_triggered is True
        assert "Daily baseline unchanged" in caplog.text
        assert "Daily baseline reset" not in caplog.text

    @pytest.mark.parametrize("initial_equity", [0.0, None])
    def test_handles_zero_or_none_equity_without_error(self, initial_equity):
        """Should handle 0 or None previous equity without raising errors."""
        state = RiskControlState(
            daily_start_equity=initial_equity,
            daily_start_date=None,
        )

        update_daily_baseline(state, current_equity=0.0)

        assert state.daily_start_equity == 0.0


class TestCalculateDailyLossPct:
    """Tests for calculate_daily_loss_pct helper (Story 7.3.2)."""

    def test_zero_change_returns_zero(self):
        """Should return 0.0 when current_equity equals daily_start_equity (AC1)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        result = calculate_daily_loss_pct(state, current_equity=10000.0)

        assert result == 0.0
        assert state.daily_loss_pct == 0.0

    def test_profit_returns_positive_percentage(self):
        """Should return positive percentage when current_equity > daily_start_equity (AC1)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        result = calculate_daily_loss_pct(state, current_equity=10500.0)

        assert result == 5.0
        assert state.daily_loss_pct == 5.0

    def test_loss_returns_negative_percentage(self):
        """Should return negative percentage when current_equity < daily_start_equity (AC1)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        result = calculate_daily_loss_pct(state, current_equity=9500.0)

        assert result == -5.0
        assert state.daily_loss_pct == -5.0

    def test_formula_precision(self):
        """Should calculate with correct precision following the formula (AC1)."""
        state = RiskControlState(
            daily_start_equity=12500.0,
            daily_start_date="2025-11-30",
        )

        # (11875 - 12500) / 12500 * 100 = -5.0
        result = calculate_daily_loss_pct(state, current_equity=11875.0)

        assert result == -5.0
        assert state.daily_loss_pct == -5.0

        # (13125 - 12500) / 12500 * 100 = 5.0
        result = calculate_daily_loss_pct(state, current_equity=13125.0)

        assert result == 5.0
        assert state.daily_loss_pct == 5.0

    def test_none_baseline_returns_zero(self):
        """Should return 0.0 when daily_start_equity is None (AC2)."""
        state = RiskControlState(
            daily_start_equity=None,
            daily_start_date=None,
            daily_loss_pct=-3.5,  # Previous value should be reset
        )

        result = calculate_daily_loss_pct(state, current_equity=10000.0)

        assert result == 0.0
        assert state.daily_loss_pct == 0.0

    def test_zero_baseline_returns_zero(self):
        """Should return 0.0 when daily_start_equity is 0 (AC2)."""
        state = RiskControlState(
            daily_start_equity=0.0,
            daily_start_date="2025-11-30",
            daily_loss_pct=-5.0,  # Previous value should be reset
        )

        result = calculate_daily_loss_pct(state, current_equity=10000.0)

        assert result == 0.0
        assert state.daily_loss_pct == 0.0

    def test_negative_baseline_returns_zero(self):
        """Should return 0.0 when daily_start_equity is negative (AC2)."""
        state = RiskControlState(
            daily_start_equity=-100.0,
            daily_start_date="2025-11-30",
            daily_loss_pct=-2.0,  # Previous value should be reset
        )

        result = calculate_daily_loss_pct(state, current_equity=10000.0)

        assert result == 0.0
        assert state.daily_loss_pct == 0.0

    def test_boundary_cases_do_not_raise_exception(self):
        """Should not raise any exception for boundary cases (AC2)."""
        boundary_cases = [None, 0.0, -100.0, -0.001]

        for baseline in boundary_cases:
            state = RiskControlState(
                daily_start_equity=baseline,
                daily_start_date="2025-11-30",
            )

            # Should not raise
            result = calculate_daily_loss_pct(state, current_equity=10000.0)

            assert result == 0.0
            assert state.daily_loss_pct == 0.0

    def test_multiple_calls_update_state_correctly(self):
        """Should update state.daily_loss_pct on each call (AC4)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        # First call: profit
        result1 = calculate_daily_loss_pct(state, current_equity=10500.0)
        assert result1 == 5.0
        assert state.daily_loss_pct == 5.0

        # Second call: loss
        result2 = calculate_daily_loss_pct(state, current_equity=9800.0)
        assert result2 == -2.0
        assert state.daily_loss_pct == -2.0

        # Third call: back to break-even
        result3 = calculate_daily_loss_pct(state, current_equity=10000.0)
        assert result3 == 0.0
        assert state.daily_loss_pct == 0.0

    def test_return_value_matches_state_field(self):
        """Should return the same value as state.daily_loss_pct (AC1, AC2)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        result = calculate_daily_loss_pct(state, current_equity=9250.0)

        assert result == state.daily_loss_pct
        assert result == -7.5

    def test_does_not_modify_kill_switch_fields(self):
        """Should not modify Kill-Switch related fields (AC2)."""
        state = RiskControlState(
            kill_switch_active=False,
            kill_switch_reason=None,
            kill_switch_triggered_at=None,
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
            daily_loss_triggered=False,
        )

        calculate_daily_loss_pct(state, current_equity=8000.0)

        # Kill-Switch fields should remain unchanged
        assert state.kill_switch_active is False
        assert state.kill_switch_reason is None
        assert state.kill_switch_triggered_at is None
        # daily_loss_triggered should also remain unchanged (Story 7.3.3 responsibility)
        assert state.daily_loss_triggered is False

    def test_logs_debug_on_normal_calculation(self, caplog):
        """Should log DEBUG level for normal calculation."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        with caplog.at_level(logging.DEBUG):
            calculate_daily_loss_pct(state, current_equity=9500.0)

        assert "calculate_daily_loss_pct" in caplog.text
        assert "current_equity=9500.00" in caplog.text
        assert "daily_start_equity=10000.00" in caplog.text

    def test_logs_debug_on_invalid_baseline(self, caplog):
        """Should log DEBUG level for invalid baseline case."""
        state = RiskControlState(
            daily_start_equity=None,
            daily_start_date=None,
        )

        with caplog.at_level(logging.DEBUG):
            calculate_daily_loss_pct(state, current_equity=10000.0)

        assert "invalid baseline" in caplog.text
        assert "returning 0.0" in caplog.text

    def test_preserves_other_state_fields(self):
        """Should not modify fields other than daily_loss_pct."""
        state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="test:reason",
            kill_switch_triggered_at="2025-11-30T10:00:00+00:00",
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
            daily_loss_pct=0.0,
            daily_loss_triggered=True,
        )

        calculate_daily_loss_pct(state, current_equity=9000.0)

        # Only daily_loss_pct should change
        assert state.kill_switch_active is True
        assert state.kill_switch_reason == "test:reason"
        assert state.kill_switch_triggered_at == "2025-11-30T10:00:00+00:00"
        assert state.daily_start_equity == 10000.0
        assert state.daily_start_date == "2025-11-30"
        assert state.daily_loss_pct == -10.0  # This should change
        assert state.daily_loss_triggered is True  # This should NOT change


class TestCheckDailyLossLimit:
    """Tests for check_daily_loss_limit() function (Story 7.3.3).

    This test class covers:
    - AC1: Core trigger logic with threshold comparison
    - AC2: Integration with Kill-Switch activation
    - AC3: Logging and notification callbacks
    - AC4: Boundary cases and edge conditions
    """

    def test_returns_false_when_risk_control_disabled(self):
        """Should return False when RISK_CONTROL_ENABLED=False (AC4)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        result = check_daily_loss_limit(
            state,
            current_equity=9000.0,  # -10% loss, would trigger if enabled
            risk_control_enabled=False,
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
        )

        assert result is False
        assert state.daily_loss_triggered is False
        assert state.kill_switch_active is False

    def test_returns_false_when_daily_loss_limit_disabled(self):
        """Should return False when DAILY_LOSS_LIMIT_ENABLED=False (AC4)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        result = check_daily_loss_limit(
            state,
            current_equity=9000.0,  # -10% loss, would trigger if enabled
            risk_control_enabled=True,
            daily_loss_limit_enabled=False,
            daily_loss_limit_pct=5.0,
        )

        assert result is False
        assert state.daily_loss_triggered is False
        assert state.kill_switch_active is False

    def test_returns_false_when_daily_start_equity_is_none(self):
        """Should return False when daily_start_equity is None (AC4)."""
        state = RiskControlState(
            daily_start_equity=None,
            daily_start_date=None,
        )

        result = check_daily_loss_limit(
            state,
            current_equity=9000.0,
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
        )

        assert result is False
        assert state.daily_loss_triggered is False
        assert state.kill_switch_active is False

    def test_returns_false_when_daily_start_equity_is_zero(self):
        """Should return False when daily_start_equity is 0 (AC4)."""
        state = RiskControlState(
            daily_start_equity=0.0,
            daily_start_date="2025-11-30",
        )

        result = check_daily_loss_limit(
            state,
            current_equity=9000.0,
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
        )

        assert result is False
        assert state.daily_loss_triggered is False
        assert state.kill_switch_active is False

    def test_returns_false_when_daily_start_equity_is_negative(self):
        """Should return False when daily_start_equity is negative (AC4)."""
        state = RiskControlState(
            daily_start_equity=-1000.0,
            daily_start_date="2025-11-30",
        )

        result = check_daily_loss_limit(
            state,
            current_equity=9000.0,
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
        )

        assert result is False
        assert state.daily_loss_triggered is False
        assert state.kill_switch_active is False

    def test_returns_false_when_threshold_not_reached(self):
        """Should return False when loss is below threshold (AC1)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        # -3% loss, threshold is -5%
        result = check_daily_loss_limit(
            state,
            current_equity=9700.0,
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
        )

        assert result is False
        assert state.daily_loss_triggered is False
        assert state.kill_switch_active is False
        assert state.daily_loss_pct == -3.0

    def test_returns_false_when_profit(self):
        """Should return False when there is profit (AC1)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        # +5% profit
        result = check_daily_loss_limit(
            state,
            current_equity=10500.0,
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
        )

        assert result is False
        assert state.daily_loss_triggered is False
        assert state.kill_switch_active is False
        assert state.daily_loss_pct == 5.0

    def test_triggers_when_threshold_exactly_reached(self):
        """Should trigger when loss exactly equals threshold (AC1)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        # -5% loss, threshold is -5%
        result = check_daily_loss_limit(
            state,
            current_equity=9500.0,
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
        )

        assert result is True
        assert state.daily_loss_triggered is True
        assert state.kill_switch_active is True
        assert state.daily_loss_pct == -5.0
        assert "Daily loss limit reached" in state.kill_switch_reason

    def test_triggers_when_threshold_exceeded(self):
        """Should trigger when loss exceeds threshold (AC1)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        # -6.2% loss, threshold is -5%
        result = check_daily_loss_limit(
            state,
            current_equity=9380.0,
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
        )

        assert result is True
        assert state.daily_loss_triggered is True
        assert state.kill_switch_active is True
        assert state.daily_loss_pct == -6.2
        assert "-6.20%" in state.kill_switch_reason
        assert "-5.00%" in state.kill_switch_reason

    def test_returns_false_when_already_triggered(self):
        """Should return False when daily_loss_triggered is already True (AC1)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
            daily_loss_triggered=True,  # Already triggered
            kill_switch_active=True,
            kill_switch_reason="Previous trigger",
        )

        # -10% loss, would trigger if not already triggered
        result = check_daily_loss_limit(
            state,
            current_equity=9000.0,
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
        )

        assert result is False
        # State should remain unchanged
        assert state.daily_loss_triggered is True
        assert state.kill_switch_reason == "Previous trigger"

    def test_updates_daily_loss_pct_even_when_not_triggered(self):
        """Should update daily_loss_pct even when threshold not reached (AC1)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
            daily_loss_pct=0.0,
        )

        check_daily_loss_limit(
            state,
            current_equity=9800.0,  # -2% loss
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
        )

        assert state.daily_loss_pct == -2.0

    def test_calls_notify_fn_on_trigger(self):
        """Should call notify_fn when threshold is triggered (AC3)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        notify_calls = []

        def mock_notify(loss_pct, limit_pct, daily_start_equity, current_equity):
            notify_calls.append({
                "loss_pct": loss_pct,
                "limit_pct": limit_pct,
                "daily_start_equity": daily_start_equity,
                "current_equity": current_equity,
            })

        result = check_daily_loss_limit(
            state,
            current_equity=9400.0,  # -6% loss
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
            notify_fn=mock_notify,
        )

        assert result is True
        assert len(notify_calls) == 1
        assert notify_calls[0]["loss_pct"] == -6.0
        assert notify_calls[0]["limit_pct"] == 5.0
        assert notify_calls[0]["daily_start_equity"] == 10000.0
        assert notify_calls[0]["current_equity"] == 9400.0

    def test_does_not_call_notify_fn_when_not_triggered(self):
        """Should not call notify_fn when threshold not reached (AC3)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        notify_calls = []

        def mock_notify(loss_pct, limit_pct, daily_start_equity, current_equity):
            notify_calls.append(True)

        check_daily_loss_limit(
            state,
            current_equity=9800.0,  # -2% loss, below threshold
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
            notify_fn=mock_notify,
        )

        assert len(notify_calls) == 0

    def test_calls_record_event_fn_on_trigger(self):
        """Should call record_event_fn when threshold is triggered (AC3)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        record_calls = []

        def mock_record(action, reason):
            record_calls.append({"action": action, "reason": reason})

        result = check_daily_loss_limit(
            state,
            current_equity=9400.0,  # -6% loss
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
            record_event_fn=mock_record,
        )

        assert result is True
        assert len(record_calls) == 1
        assert record_calls[0]["action"] == "DAILY_LOSS_LIMIT_TRIGGERED"
        assert "Daily loss limit reached" in record_calls[0]["reason"]

    def test_does_not_call_record_event_fn_when_not_triggered(self):
        """Should not call record_event_fn when threshold not reached (AC3)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        record_calls = []

        def mock_record(action, reason):
            record_calls.append(True)

        check_daily_loss_limit(
            state,
            current_equity=9800.0,  # -2% loss, below threshold
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
            record_event_fn=mock_record,
        )

        assert len(record_calls) == 0

    def test_logs_warning_on_trigger(self, caplog):
        """Should log WARNING level when threshold is triggered (AC3)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        with caplog.at_level(logging.WARNING):
            check_daily_loss_limit(
                state,
                current_equity=9400.0,  # -6% loss
                daily_loss_limit_enabled=True,
                daily_loss_limit_pct=5.0,
            )

        assert "Daily loss limit triggered" in caplog.text
        assert "loss_pct=-6.00%" in caplog.text
        assert "threshold=-5.00%" in caplog.text
        assert "first_trigger=True" in caplog.text

    def test_logs_debug_when_not_triggered(self, caplog):
        """Should log DEBUG level when threshold not reached."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        with caplog.at_level(logging.DEBUG):
            check_daily_loss_limit(
                state,
                current_equity=9800.0,  # -2% loss
                daily_loss_limit_enabled=True,
                daily_loss_limit_pct=5.0,
            )

        assert "threshold not reached" in caplog.text

    def test_handles_notify_fn_exception(self, caplog):
        """Should handle notify_fn exception gracefully (AC3)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        def failing_notify(*args):
            raise RuntimeError("Notification failed")

        with caplog.at_level(logging.ERROR):
            result = check_daily_loss_limit(
                state,
                current_equity=9400.0,  # -6% loss
                daily_loss_limit_enabled=True,
                daily_loss_limit_pct=5.0,
                notify_fn=failing_notify,
            )

        # Should still return True (trigger succeeded)
        assert result is True
        assert state.daily_loss_triggered is True
        assert "Failed to send daily loss limit notification" in caplog.text

    def test_handles_record_event_fn_exception(self, caplog):
        """Should handle record_event_fn exception gracefully (AC3)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        def failing_record(*args):
            raise RuntimeError("Record failed")

        with caplog.at_level(logging.ERROR):
            result = check_daily_loss_limit(
                state,
                current_equity=9400.0,  # -6% loss
                daily_loss_limit_enabled=True,
                daily_loss_limit_pct=5.0,
                record_event_fn=failing_record,
            )

        # Should still return True (trigger succeeded)
        assert result is True
        assert state.daily_loss_triggered is True
        assert "Failed to record daily loss limit event" in caplog.text

    def test_multiple_calls_do_not_duplicate_trigger(self):
        """Should not trigger multiple times in same day (AC1)."""
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        notify_calls = []

        def mock_notify(*args):
            notify_calls.append(True)

        # First call: triggers
        result1 = check_daily_loss_limit(
            state,
            current_equity=9400.0,  # -6% loss
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
            notify_fn=mock_notify,
        )

        # Second call: should not trigger again
        result2 = check_daily_loss_limit(
            state,
            current_equity=9200.0,  # -8% loss, even worse
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
            notify_fn=mock_notify,
        )

        assert result1 is True
        assert result2 is False
        assert len(notify_calls) == 1  # Only one notification

    def test_different_threshold_values(self):
        """Should work with different threshold values (AC1)."""
        # Test with 10% threshold
        state = RiskControlState(
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
        )

        # -8% loss, threshold is 10%
        result = check_daily_loss_limit(
            state,
            current_equity=9200.0,
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=10.0,
        )

        assert result is False  # Not triggered yet
        assert state.daily_loss_triggered is False

        # -10% loss, threshold is 10%
        result = check_daily_loss_limit(
            state,
            current_equity=9000.0,
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=10.0,
        )

        assert result is True  # Now triggered
        assert state.daily_loss_triggered is True
