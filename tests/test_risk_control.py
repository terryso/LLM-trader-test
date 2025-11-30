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
