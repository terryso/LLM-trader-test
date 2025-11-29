"""Tests for core/risk_control.py module."""
import json

import pytest

from core.risk_control import RiskControlState


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
