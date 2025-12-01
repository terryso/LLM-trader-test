"""Integration tests for risk control state persistence and main loop integration.

Covers:
- Saving RiskControlState into portfolio_state.json via core.state.save_state
- Loading RiskControlState from JSON via core.state.load_state
- Backward compatibility when risk_control field is missing or malformed
- Risk control check entry point in main loop (Story 7.1.4)
- Risk control configuration logging at startup
"""

import copy
import json
import logging
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import TestCase, mock

import core.state as core_state
from core.risk_control import (
    RiskControlState,
    check_risk_limits,
    activate_kill_switch,
    deactivate_kill_switch,
    apply_kill_switch_env_override,
    update_daily_baseline,
)


class RiskControlPersistenceIntegrationTests(TestCase):
    """Integration tests for RiskControlState persistence and compatibility."""

    def setUp(self) -> None:
        self._orig_balance = core_state.balance
        self._orig_positions = copy.deepcopy(core_state.positions)
        self._orig_iteration = core_state.iteration_counter
        self._orig_risk_control_state = core_state.risk_control_state
        self._orig_state_json = core_state.STATE_JSON

    def tearDown(self) -> None:
        core_state.balance = self._orig_balance
        core_state.positions = copy.deepcopy(self._orig_positions)
        core_state.iteration_counter = self._orig_iteration
        core_state.risk_control_state = self._orig_risk_control_state
        core_state.STATE_JSON = self._orig_state_json

    def test_save_state_includes_risk_control_field(self) -> None:
        """save_state should include risk_control field matching to_dict()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"

            core_state.balance = 111.1
            core_state.positions = {}
            core_state.iteration_counter = 42
            core_state.risk_control_state = RiskControlState(
                kill_switch_active=True,
                kill_switch_reason="Daily loss limit",
                daily_start_equity=5000.0,
                daily_start_date="2025-11-30",
                daily_loss_pct=-5.0,
                daily_loss_triggered=True,
            )

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.save_state()

            data = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("risk_control", data)
            self.assertEqual(data["risk_control"], core_state.risk_control_state.to_dict())

    def test_load_state_restores_risk_control_from_json(self) -> None:
        """load_state should restore RiskControlState from risk_control field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            payload = {
                "balance": 9000.0,
                "positions": {},
                "iteration": 7,
                "updated_at": "2025-11-30T00:00:00+00:00",
                "risk_control": {
                    "kill_switch_active": True,
                    "kill_switch_reason": "Manual trigger",
                    "kill_switch_triggered_at": "2025-11-30T10:00:00+00:00",
                    "daily_start_equity": 10000.0,
                    "daily_start_date": "2025-11-30",
                    "daily_loss_pct": -3.5,
                    "daily_loss_triggered": False,
                },
            }
            state_path.write_text(json.dumps(payload), encoding="utf-8")

            core_state.balance = 0.0
            core_state.positions = {}
            core_state.iteration_counter = 0
            core_state.risk_control_state = RiskControlState()

            # Mock os.environ to ensure KILL_SWITCH is not set (isolate from .env)
            import os
            with mock.patch.dict("os.environ", {}, clear=False):
                os.environ.pop("KILL_SWITCH", None)
                with mock.patch.object(core_state, "STATE_JSON", state_path):
                    core_state.load_state()

            self.assertEqual(core_state.balance, 9000.0)
            self.assertEqual(core_state.iteration_counter, 7)

            state = core_state.risk_control_state
            self.assertTrue(state.kill_switch_active)
            self.assertEqual(state.kill_switch_reason, "Manual trigger")
            self.assertEqual(state.kill_switch_triggered_at, "2025-11-30T10:00:00+00:00")
            self.assertEqual(state.daily_start_equity, 10000.0)
            self.assertEqual(state.daily_start_date, "2025-11-30")
            self.assertEqual(state.daily_loss_pct, -3.5)
            self.assertFalse(state.daily_loss_triggered)

    def test_load_state_uses_default_when_risk_control_missing(self) -> None:
        """load_state should fall back to default RiskControlState when field missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            payload = {
                "balance": 5000.0,
                "positions": {},
                "iteration": 1,
                "updated_at": "2025-11-30T00:00:00+00:00",
            }
            state_path.write_text(json.dumps(payload), encoding="utf-8")

            core_state.balance = 0.0
            core_state.positions = {}
            core_state.iteration_counter = 0
            core_state.risk_control_state = RiskControlState(
                kill_switch_active=True,
                daily_loss_pct=-10.0,
                daily_loss_triggered=True,
            )

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.load_state()

            self.assertEqual(core_state.balance, 5000.0)

            state = core_state.risk_control_state
            self.assertFalse(state.kill_switch_active)
            self.assertEqual(state.daily_loss_pct, 0.0)
            self.assertFalse(state.daily_loss_triggered)

    def test_load_state_handles_malformed_risk_control_field(self) -> None:
        """Non-dict risk_control field should be treated as missing and use defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            payload = {
                "balance": 6000.0,
                "positions": {},
                "iteration": 2,
                "updated_at": "2025-11-30T00:00:00+00:00",
                "risk_control": "not-a-dict",
            }
            state_path.write_text(json.dumps(payload), encoding="utf-8")

            core_state.balance = 0.0
            core_state.positions = {}
            core_state.iteration_counter = 0
            core_state.risk_control_state = RiskControlState(
                kill_switch_active=True,
                daily_loss_pct=-1.0,
                daily_loss_triggered=True,
            )

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.load_state()

            self.assertEqual(core_state.balance, 6000.0)

            state = core_state.risk_control_state
            self.assertFalse(state.kill_switch_active)
            self.assertEqual(state.daily_loss_pct, 0.0)
            self.assertFalse(state.daily_loss_triggered)


class RiskControlCheckIntegrationTests(TestCase):
    """Integration tests for check_risk_limits() entry point (Story 7.1.4)."""

    def test_check_risk_limits_returns_true_when_enabled(self) -> None:
        """check_risk_limits should return True when risk control is enabled."""
        state = RiskControlState()
        result = check_risk_limits(
            risk_control_state=state,
            total_equity=10000.0,
            risk_control_enabled=True,
        )
        self.assertTrue(result)

    def test_check_risk_limits_returns_true_when_disabled(self) -> None:
        """check_risk_limits should return True and skip checks when disabled."""
        state = RiskControlState(kill_switch_active=True)
        result = check_risk_limits(
            risk_control_state=state,
            total_equity=10000.0,
            risk_control_enabled=False,
        )
        self.assertTrue(result)

    def test_check_risk_limits_logs_skip_when_disabled(self, caplog=None) -> None:
        """check_risk_limits should log when risk control is disabled."""
        state = RiskControlState()
        with self.assertLogs(level=logging.INFO) as cm:
            check_risk_limits(
                risk_control_state=state,
                risk_control_enabled=False,
            )
        self.assertTrue(
            any("RISK_CONTROL_ENABLED=False" in msg for msg in cm.output),
            f"Expected log message about disabled risk control, got: {cm.output}",
        )

    def test_check_risk_limits_accepts_optional_params(self) -> None:
        """check_risk_limits should accept optional total_equity and iteration_time."""
        from datetime import datetime, timezone

        state = RiskControlState()
        # Should not raise
        result = check_risk_limits(
            risk_control_state=state,
            total_equity=None,
            iteration_time=None,
            risk_control_enabled=True,
        )
        self.assertTrue(result)

        result = check_risk_limits(
            risk_control_state=state,
            total_equity=5000.0,
            iteration_time=datetime.now(timezone.utc),
            risk_control_enabled=True,
        )
        self.assertTrue(result)


class RiskControlStateRestartTests(TestCase):
    """Integration tests for risk control state persistence across restarts."""

    def setUp(self) -> None:
        self._orig_balance = core_state.balance
        self._orig_positions = copy.deepcopy(core_state.positions)
        self._orig_iteration = core_state.iteration_counter
        self._orig_risk_control_state = core_state.risk_control_state
        self._orig_state_json = core_state.STATE_JSON

    def tearDown(self) -> None:
        core_state.balance = self._orig_balance
        core_state.positions = copy.deepcopy(self._orig_positions)
        core_state.iteration_counter = self._orig_iteration
        core_state.risk_control_state = self._orig_risk_control_state
        core_state.STATE_JSON = self._orig_state_json

    def test_risk_control_state_survives_simulated_restart(self) -> None:
        """Risk control state should be preserved across save/load cycles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"

            # Simulate iteration 1: set initial state
            core_state.balance = 10000.0
            core_state.positions = {}
            core_state.iteration_counter = 1
            core_state.risk_control_state = RiskControlState(
                kill_switch_active=False,
                daily_start_equity=10000.0,
                daily_start_date="2025-11-30",
                daily_loss_pct=0.0,
            )

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.save_state()

            # Simulate iteration 2: update state
            core_state.balance = 9500.0
            core_state.iteration_counter = 2
            core_state.risk_control_state = RiskControlState(
                kill_switch_active=False,
                daily_start_equity=10000.0,
                daily_start_date="2025-11-30",
                daily_loss_pct=-5.0,
            )

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.save_state()

            # Simulate restart: reset state and reload
            core_state.balance = 0.0
            core_state.positions = {}
            core_state.iteration_counter = 0
            core_state.risk_control_state = RiskControlState()

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.load_state()

            # Verify state was restored
            self.assertEqual(core_state.balance, 9500.0)
            self.assertEqual(core_state.iteration_counter, 2)
            self.assertEqual(core_state.risk_control_state.daily_start_equity, 10000.0)
            self.assertEqual(core_state.risk_control_state.daily_start_date, "2025-11-30")
            self.assertEqual(core_state.risk_control_state.daily_loss_pct, -5.0)
            self.assertFalse(core_state.risk_control_state.kill_switch_active)

    def test_risk_control_state_with_kill_switch_survives_restart(self) -> None:
        """Kill-switch state should be preserved across restarts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"

            # Set state with kill switch active
            core_state.balance = 8000.0
            core_state.positions = {}
            core_state.iteration_counter = 5
            core_state.risk_control_state = RiskControlState(
                kill_switch_active=True,
                kill_switch_reason="Daily loss limit exceeded",
                kill_switch_triggered_at="2025-11-30T10:30:00+00:00",
                daily_start_equity=10000.0,
                daily_start_date="2025-11-30",
                daily_loss_pct=-20.0,
                daily_loss_triggered=True,
            )

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.save_state()

            # Reset and reload
            core_state.balance = 0.0
            core_state.iteration_counter = 0
            core_state.risk_control_state = RiskControlState()

            # Mock os.environ to ensure KILL_SWITCH is not set (isolate from .env)
            import os
            with mock.patch.dict("os.environ", {}, clear=False):
                os.environ.pop("KILL_SWITCH", None)
                with mock.patch.object(core_state, "STATE_JSON", state_path):
                    core_state.load_state()

            # Verify kill switch state was restored
            self.assertTrue(core_state.risk_control_state.kill_switch_active)
            self.assertEqual(
                core_state.risk_control_state.kill_switch_reason,
                "Daily loss limit exceeded",
            )
            self.assertEqual(
                core_state.risk_control_state.kill_switch_triggered_at,
                "2025-11-30T10:30:00+00:00",
            )
            self.assertTrue(core_state.risk_control_state.daily_loss_triggered)
            self.assertEqual(core_state.risk_control_state.daily_loss_pct, -20.0)


class DailyBaselineIntegrationTests(TestCase):
    """Integration tests for daily baseline persistence and restart semantics."""

    def setUp(self) -> None:
        self._orig_balance = core_state.balance
        self._orig_positions = copy.deepcopy(core_state.positions)
        self._orig_iteration = core_state.iteration_counter
        self._orig_risk_control_state = core_state.risk_control_state
        self._orig_state_json = core_state.STATE_JSON

    def tearDown(self) -> None:
        core_state.balance = self._orig_balance
        core_state.positions = copy.deepcopy(self._orig_positions)
        core_state.iteration_counter = self._orig_iteration
        core_state.risk_control_state = self._orig_risk_control_state
        core_state.STATE_JSON = self._orig_state_json

    def test_daily_baseline_persists_across_restart_same_day(self) -> None:
        """Baseline for the same UTC day should persist across restart and remain unchanged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            # Simulate existing baseline for today and save state
            core_state.balance = 10000.0
            core_state.positions = {}
            core_state.iteration_counter = 1
            core_state.risk_control_state = RiskControlState(
                kill_switch_active=False,
                daily_start_equity=10000.0,
                daily_start_date=today,
                daily_loss_pct=0.0,
                daily_loss_triggered=False,
            )

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.save_state()

            # Simulate restart: reset in-memory state and reload
            core_state.balance = 0.0
            core_state.positions = {}
            core_state.iteration_counter = 0
            core_state.risk_control_state = RiskControlState()

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.load_state()

            # Same-day restart should keep existing baseline before helper call
            self.assertEqual(core_state.risk_control_state.daily_start_date, today)
            self.assertEqual(core_state.risk_control_state.daily_start_equity, 10000.0)

            # Calling update_daily_baseline on same day should not reset baseline
            update_daily_baseline(core_state.risk_control_state, current_equity=9500.0)

            self.assertEqual(core_state.risk_control_state.daily_start_date, today)
            self.assertEqual(core_state.risk_control_state.daily_start_equity, 10000.0)
            self.assertEqual(core_state.risk_control_state.daily_loss_pct, 0.0)
            self.assertFalse(core_state.risk_control_state.daily_loss_triggered)

    def test_daily_baseline_resets_on_cross_day_restart(self) -> None:
        """Baseline should reset on first iteration after crossing UTC day."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            previous_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

            # Persist state with previous day's baseline
            core_state.balance = 10000.0
            core_state.positions = {}
            core_state.iteration_counter = 1
            core_state.risk_control_state = RiskControlState(
                kill_switch_active=False,
                daily_start_equity=10000.0,
                daily_start_date=previous_date,
                daily_loss_pct=-5.0,
                daily_loss_triggered=True,
            )

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.save_state()

            # Simulate restart: reset in-memory state and reload
            core_state.balance = 0.0
            core_state.positions = {}
            core_state.iteration_counter = 0
            core_state.risk_control_state = RiskControlState()

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.load_state()

            # After load, baseline still reflects previous date
            self.assertEqual(core_state.risk_control_state.daily_start_date, previous_date)
            self.assertEqual(core_state.risk_control_state.daily_start_equity, 10000.0)

            # First iteration on new UTC day should reset baseline to new equity
            new_equity = 9500.0
            update_daily_baseline(core_state.risk_control_state, current_equity=new_equity)

            self.assertEqual(core_state.risk_control_state.daily_start_date, today)
            self.assertEqual(core_state.risk_control_state.daily_start_equity, new_equity)
            self.assertEqual(core_state.risk_control_state.daily_loss_pct, 0.0)
            self.assertFalse(core_state.risk_control_state.daily_loss_triggered)

            # Persist again and verify JSON reflects updated baseline
            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.save_state()

            data = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("risk_control", data)
            rc = data["risk_control"]
            self.assertEqual(rc["daily_start_equity"], new_equity)
            self.assertEqual(rc["daily_start_date"], today)
            self.assertEqual(rc["daily_loss_pct"], 0.0)
            self.assertFalse(rc["daily_loss_triggered"])


class KillSwitchEnvOverrideIntegrationTests(TestCase):
    """Integration tests for KILL_SWITCH env var priority logic (AC1, AC4)."""

    def setUp(self) -> None:
        self._orig_balance = core_state.balance
        self._orig_positions = copy.deepcopy(core_state.positions)
        self._orig_iteration = core_state.iteration_counter
        self._orig_risk_control_state = core_state.risk_control_state
        self._orig_state_json = core_state.STATE_JSON
        self._orig_kill_switch_env = os.environ.get("KILL_SWITCH")

    def tearDown(self) -> None:
        core_state.balance = self._orig_balance
        core_state.positions = copy.deepcopy(self._orig_positions)
        core_state.iteration_counter = self._orig_iteration
        core_state.risk_control_state = self._orig_risk_control_state
        core_state.STATE_JSON = self._orig_state_json
        # Restore KILL_SWITCH env var
        if self._orig_kill_switch_env is None:
            os.environ.pop("KILL_SWITCH", None)
        else:
            os.environ["KILL_SWITCH"] = self._orig_kill_switch_env

    def test_env_kill_switch_true_overrides_persisted_false(self) -> None:
        """KILL_SWITCH=true should activate Kill-Switch even if persisted state is inactive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            payload = {
                "balance": 10000.0,
                "positions": {},
                "iteration": 1,
                "updated_at": "2025-11-30T00:00:00+00:00",
                "risk_control": {
                    "kill_switch_active": False,
                    "kill_switch_reason": None,
                    "kill_switch_triggered_at": None,
                    "daily_start_equity": 10000.0,
                    "daily_start_date": "2025-11-30",
                    "daily_loss_pct": 0.0,
                    "daily_loss_triggered": False,
                },
            }
            state_path.write_text(json.dumps(payload), encoding="utf-8")

            os.environ["KILL_SWITCH"] = "true"

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.load_state()

            # Kill-Switch should be activated via env override
            self.assertTrue(core_state.risk_control_state.kill_switch_active)
            self.assertEqual(core_state.risk_control_state.kill_switch_reason, "env:KILL_SWITCH")
            self.assertIsNotNone(core_state.risk_control_state.kill_switch_triggered_at)

    def test_env_kill_switch_false_overrides_persisted_true(self) -> None:
        """KILL_SWITCH=false should deactivate Kill-Switch even if persisted state is active."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            payload = {
                "balance": 8000.0,
                "positions": {},
                "iteration": 5,
                "updated_at": "2025-11-30T00:00:00+00:00",
                "risk_control": {
                    "kill_switch_active": True,
                    "kill_switch_reason": "runtime:manual",
                    "kill_switch_triggered_at": "2025-11-30T10:00:00+00:00",
                    "daily_start_equity": 10000.0,
                    "daily_start_date": "2025-11-30",
                    "daily_loss_pct": -20.0,
                    "daily_loss_triggered": True,
                },
            }
            state_path.write_text(json.dumps(payload), encoding="utf-8")

            os.environ["KILL_SWITCH"] = "false"

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.load_state()

            # Kill-Switch should be deactivated via env override
            self.assertFalse(core_state.risk_control_state.kill_switch_active)
            # AC1: reason should be set to env:KILL_SWITCH (deactivation reason)
            self.assertEqual(core_state.risk_control_state.kill_switch_reason, "env:KILL_SWITCH")
            # AC1: triggered_at should be preserved for audit trail
            self.assertEqual(
                core_state.risk_control_state.kill_switch_triggered_at,
                "2025-11-30T10:00:00+00:00",
            )
            # Daily loss fields should be preserved
            self.assertEqual(core_state.risk_control_state.daily_loss_pct, -20.0)
            self.assertTrue(core_state.risk_control_state.daily_loss_triggered)

    def test_env_not_set_preserves_persisted_active_state(self) -> None:
        """When KILL_SWITCH env is not set, persisted active state should be preserved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            payload = {
                "balance": 8000.0,
                "positions": {},
                "iteration": 5,
                "updated_at": "2025-11-30T00:00:00+00:00",
                "risk_control": {
                    "kill_switch_active": True,
                    "kill_switch_reason": "runtime:manual",
                    "kill_switch_triggered_at": "2025-11-30T10:00:00+00:00",
                    "daily_start_equity": 10000.0,
                    "daily_start_date": "2025-11-30",
                    "daily_loss_pct": -5.0,
                    "daily_loss_triggered": False,
                },
            }
            state_path.write_text(json.dumps(payload), encoding="utf-8")

            # Ensure KILL_SWITCH is not set
            os.environ.pop("KILL_SWITCH", None)

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.load_state()

            # Kill-Switch should remain active from persisted state
            self.assertTrue(core_state.risk_control_state.kill_switch_active)
            self.assertEqual(core_state.risk_control_state.kill_switch_reason, "runtime:manual")
            self.assertEqual(
                core_state.risk_control_state.kill_switch_triggered_at,
                "2025-11-30T10:00:00+00:00",
            )


class KillSwitchRestartPersistenceTests(TestCase):
    """Integration tests for Kill-Switch state persistence across restarts (AC4)."""

    def setUp(self) -> None:
        self._orig_balance = core_state.balance
        self._orig_positions = copy.deepcopy(core_state.positions)
        self._orig_iteration = core_state.iteration_counter
        self._orig_risk_control_state = core_state.risk_control_state
        self._orig_state_json = core_state.STATE_JSON
        self._orig_kill_switch_env = os.environ.get("KILL_SWITCH")

    def tearDown(self) -> None:
        core_state.balance = self._orig_balance
        core_state.positions = copy.deepcopy(self._orig_positions)
        core_state.iteration_counter = self._orig_iteration
        core_state.risk_control_state = self._orig_risk_control_state
        core_state.STATE_JSON = self._orig_state_json
        if self._orig_kill_switch_env is None:
            os.environ.pop("KILL_SWITCH", None)
        else:
            os.environ["KILL_SWITCH"] = self._orig_kill_switch_env

    def test_kill_switch_activated_at_runtime_persists_across_restart(self) -> None:
        """Kill-Switch activated at runtime should persist and be restored on restart."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            os.environ.pop("KILL_SWITCH", None)  # Ensure env is not set

            # Run 1: Start with inactive Kill-Switch, then activate it
            core_state.balance = 10000.0
            core_state.positions = {}
            core_state.iteration_counter = 1
            core_state.risk_control_state = RiskControlState(
                kill_switch_active=False,
                daily_start_equity=10000.0,
                daily_start_date="2025-11-30",
            )

            # Simulate runtime activation (e.g., via Telegram command or daily loss trigger)
            core_state.risk_control_state = activate_kill_switch(
                core_state.risk_control_state,
                reason="runtime:manual",
            )

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.save_state()

            # Verify state was saved
            saved_data = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertTrue(saved_data["risk_control"]["kill_switch_active"])
            self.assertEqual(saved_data["risk_control"]["kill_switch_reason"], "runtime:manual")

            # Run 2: Simulate restart - reset state and reload
            core_state.balance = 0.0
            core_state.positions = {}
            core_state.iteration_counter = 0
            core_state.risk_control_state = RiskControlState()

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.load_state()

            # Kill-Switch should be restored from persisted state
            self.assertTrue(core_state.risk_control_state.kill_switch_active)
            self.assertEqual(core_state.risk_control_state.kill_switch_reason, "runtime:manual")
            self.assertIsNotNone(core_state.risk_control_state.kill_switch_triggered_at)

    def test_state_file_missing_uses_default_kill_switch(self) -> None:
        """When state file is missing, Kill-Switch should default to inactive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "nonexistent.json"
            os.environ.pop("KILL_SWITCH", None)

            core_state.risk_control_state = RiskControlState(kill_switch_active=True)

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.load_state()

            # Should use default (inactive) state
            self.assertFalse(core_state.risk_control_state.kill_switch_active)

    def test_corrupted_risk_control_field_uses_default(self) -> None:
        """Corrupted risk_control field should fall back to default state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            os.environ.pop("KILL_SWITCH", None)

            # Write state with corrupted risk_control (not a dict)
            payload = {
                "balance": 5000.0,
                "positions": {},
                "iteration": 3,
                "updated_at": "2025-11-30T00:00:00+00:00",
                "risk_control": "corrupted-string",
            }
            state_path.write_text(json.dumps(payload), encoding="utf-8")

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.load_state()

            # Should use default state
            self.assertFalse(core_state.risk_control_state.kill_switch_active)
            self.assertEqual(core_state.risk_control_state.daily_loss_pct, 0.0)


class KillSwitchBlocksEntryIntegrationTests(TestCase):
    """Integration tests for Kill-Switch blocking entry signals (AC3)."""

    def test_check_risk_limits_returns_false_when_kill_switch_active(self) -> None:
        """check_risk_limits should return False when Kill-Switch is active."""
        state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="test:integration",
            kill_switch_triggered_at="2025-11-30T12:00:00+00:00",
        )

        result = check_risk_limits(
            risk_control_state=state,
            total_equity=10000.0,
            risk_control_enabled=True,
        )

        self.assertFalse(result)

    def test_check_risk_limits_returns_true_when_kill_switch_inactive(self) -> None:
        """check_risk_limits should return True when Kill-Switch is inactive."""
        state = RiskControlState(kill_switch_active=False)

        result = check_risk_limits(
            risk_control_state=state,
            total_equity=10000.0,
            risk_control_enabled=True,
        )

        self.assertTrue(result)

    def test_check_risk_limits_logs_kill_switch_active(self) -> None:
        """check_risk_limits should log warning when Kill-Switch is active."""
        state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="test:log-check",
            kill_switch_triggered_at="2025-11-30T12:00:00+00:00",
        )

        with self.assertLogs(level=logging.WARNING) as cm:
            check_risk_limits(
                risk_control_state=state,
                risk_control_enabled=True,
            )

        self.assertTrue(
            any("Kill-Switch is active" in msg for msg in cm.output),
            f"Expected Kill-Switch warning in logs, got: {cm.output}",
        )
        self.assertTrue(
            any("test:log-check" in msg for msg in cm.output),
            f"Expected reason in logs, got: {cm.output}",
        )


class ExecutorKillSwitchGuardTests(TestCase):
    """Integration tests for Kill-Switch guard in execution/executor.py (Task 2.3)."""

    def test_executor_blocks_entry_when_kill_switch_active(self) -> None:
        """TradeExecutor.execute_entry should block when Kill-Switch is active."""
        from unittest.mock import MagicMock, patch
        from execution.executor import TradeExecutor

        # Create mock dependencies
        positions = {}
        mock_balance = MagicMock(return_value=10000.0)
        mock_set_balance = MagicMock()
        mock_get_time = MagicMock()
        mock_calc_pnl = MagicMock(return_value=0.0)
        mock_exit_fee = MagicMock(return_value=0.0)
        mock_record_msg = MagicMock()
        mock_log_trade = MagicMock()
        mock_log_decision = MagicMock()
        mock_save_state = MagicMock()
        mock_send_telegram = MagicMock()
        mock_escape_md = MagicMock(return_value="")
        mock_fetch_data = MagicMock(return_value={"price": 50000.0})
        mock_hl_trader = MagicMock()
        mock_hl_trader.is_live = False
        mock_binance_exchange = MagicMock()

        # Kill-Switch is active
        is_kill_switch_active = MagicMock(return_value=True)

        executor = TradeExecutor(
            positions=positions,
            get_balance=mock_balance,
            set_balance=mock_set_balance,
            get_current_time=mock_get_time,
            calculate_unrealized_pnl=mock_calc_pnl,
            estimate_exit_fee=mock_exit_fee,
            record_iteration_message=mock_record_msg,
            log_trade=mock_log_trade,
            log_ai_decision=mock_log_decision,
            save_state=mock_save_state,
            send_telegram_message=mock_send_telegram,
            escape_markdown=mock_escape_md,
            fetch_market_data=mock_fetch_data,
            hyperliquid_trader=mock_hl_trader,
            get_binance_futures_exchange=mock_binance_exchange,
            trading_backend="paper",
            binance_futures_live=False,
            backpack_futures_live=False,
            is_kill_switch_active=is_kill_switch_active,
        )

        decision = {
            "signal": "entry",
            "side": "long",
            "leverage": 5,
            "profit_target": 52000.0,
            "stop_loss": 48000.0,
            "confidence": 80,
            "justification": "Test entry",
        }

        # Patch RISK_CONTROL_ENABLED to True
        with patch("execution.executor.RISK_CONTROL_ENABLED", True):
            with self.assertLogs(level=logging.WARNING) as cm:
                executor.execute_entry("BTC", decision, 50000.0)

        # Verify entry was blocked
        self.assertEqual(len(positions), 0)
        mock_log_trade.assert_not_called()
        mock_save_state.assert_not_called()

        # Verify warning was logged
        self.assertTrue(
            any("Kill-Switch active (executor guard)" in msg for msg in cm.output),
            f"Expected executor guard warning, got: {cm.output}",
        )

    def test_executor_allows_entry_when_kill_switch_inactive(self) -> None:
        """TradeExecutor.execute_entry should proceed when Kill-Switch is inactive."""
        from unittest.mock import MagicMock, patch
        from execution.executor import TradeExecutor

        # Create mock dependencies
        positions = {}
        mock_balance = MagicMock(return_value=10000.0)
        mock_set_balance = MagicMock()
        mock_get_time = MagicMock()
        mock_calc_pnl = MagicMock(return_value=0.0)
        mock_exit_fee = MagicMock(return_value=0.0)
        mock_record_msg = MagicMock()
        mock_log_trade = MagicMock()
        mock_log_decision = MagicMock()
        mock_save_state = MagicMock()
        mock_send_telegram = MagicMock()
        mock_escape_md = MagicMock(return_value="")
        mock_fetch_data = MagicMock(return_value={"price": 50000.0})
        mock_hl_trader = MagicMock()
        mock_hl_trader.is_live = False
        mock_binance_exchange = MagicMock()

        # Kill-Switch is inactive
        is_kill_switch_active = MagicMock(return_value=False)

        executor = TradeExecutor(
            positions=positions,
            get_balance=mock_balance,
            set_balance=mock_set_balance,
            get_current_time=mock_get_time,
            calculate_unrealized_pnl=mock_calc_pnl,
            estimate_exit_fee=mock_exit_fee,
            record_iteration_message=mock_record_msg,
            log_trade=mock_log_trade,
            log_ai_decision=mock_log_decision,
            save_state=mock_save_state,
            send_telegram_message=mock_send_telegram,
            escape_markdown=mock_escape_md,
            fetch_market_data=mock_fetch_data,
            hyperliquid_trader=mock_hl_trader,
            get_binance_futures_exchange=mock_binance_exchange,
            trading_backend="paper",
            binance_futures_live=False,
            backpack_futures_live=False,
            is_kill_switch_active=is_kill_switch_active,
        )

        decision = {
            "signal": "entry",
            "side": "long",
            "leverage": 5,
            "profit_target": 52000.0,
            "stop_loss": 48000.0,
            "confidence": 80,
            "justification": "Test entry",
        }

        # Patch RISK_CONTROL_ENABLED to True
        with patch("execution.executor.RISK_CONTROL_ENABLED", True):
            executor.execute_entry("BTC", decision, 50000.0)

        # Verify entry proceeded (position created)
        self.assertIn("BTC", positions)
        mock_log_trade.assert_called_once()
        mock_save_state.assert_called_once()

    def test_executor_allows_entry_when_callback_not_provided(self) -> None:
        """TradeExecutor.execute_entry should proceed when is_kill_switch_active is None."""
        from unittest.mock import MagicMock, patch
        from execution.executor import TradeExecutor

        # Create mock dependencies
        positions = {}
        mock_balance = MagicMock(return_value=10000.0)
        mock_set_balance = MagicMock()
        mock_get_time = MagicMock()
        mock_calc_pnl = MagicMock(return_value=0.0)
        mock_exit_fee = MagicMock(return_value=0.0)
        mock_record_msg = MagicMock()
        mock_log_trade = MagicMock()
        mock_log_decision = MagicMock()
        mock_save_state = MagicMock()
        mock_send_telegram = MagicMock()
        mock_escape_md = MagicMock(return_value="")
        mock_fetch_data = MagicMock(return_value={"price": 50000.0})
        mock_hl_trader = MagicMock()
        mock_hl_trader.is_live = False
        mock_binance_exchange = MagicMock()

        # No Kill-Switch callback provided (backward compatibility)
        executor = TradeExecutor(
            positions=positions,
            get_balance=mock_balance,
            set_balance=mock_set_balance,
            get_current_time=mock_get_time,
            calculate_unrealized_pnl=mock_calc_pnl,
            estimate_exit_fee=mock_exit_fee,
            record_iteration_message=mock_record_msg,
            log_trade=mock_log_trade,
            log_ai_decision=mock_log_decision,
            save_state=mock_save_state,
            send_telegram_message=mock_send_telegram,
            escape_markdown=mock_escape_md,
            fetch_market_data=mock_fetch_data,
            hyperliquid_trader=mock_hl_trader,
            get_binance_futures_exchange=mock_binance_exchange,
            trading_backend="paper",
            binance_futures_live=False,
            backpack_futures_live=False,
            # is_kill_switch_active not provided (defaults to None)
        )

        decision = {
            "signal": "entry",
            "side": "long",
            "leverage": 5,
            "profit_target": 52000.0,
            "stop_loss": 48000.0,
            "confidence": 80,
            "justification": "Test entry",
        }

        # Patch RISK_CONTROL_ENABLED to True
        with patch("execution.executor.RISK_CONTROL_ENABLED", True):
            executor.execute_entry("BTC", decision, 50000.0)

        # Verify entry proceeded (position created)
        self.assertIn("BTC", positions)
        mock_log_trade.assert_called_once()
        mock_save_state.assert_called_once()


class KillSwitchDeactivationIntegrationTests(TestCase):
    """Integration tests for Kill-Switch deactivation and resume (Story 7.2.2, AC4)."""

    def setUp(self) -> None:
        self._orig_balance = core_state.balance
        self._orig_positions = copy.deepcopy(core_state.positions)
        self._orig_iteration = core_state.iteration_counter
        self._orig_risk_control_state = core_state.risk_control_state
        self._orig_state_json = core_state.STATE_JSON
        self._orig_kill_switch_env = os.environ.get("KILL_SWITCH")

    def tearDown(self) -> None:
        core_state.balance = self._orig_balance
        core_state.positions = copy.deepcopy(self._orig_positions)
        core_state.iteration_counter = self._orig_iteration
        core_state.risk_control_state = self._orig_risk_control_state
        core_state.STATE_JSON = self._orig_state_json
        if self._orig_kill_switch_env is None:
            os.environ.pop("KILL_SWITCH", None)
        else:
            os.environ["KILL_SWITCH"] = self._orig_kill_switch_env

    def test_scenario_a_deactivate_persists_and_allows_entry_after_restart(self) -> None:
        """Scenario A: Activate → Deactivate → Save → Restart → Kill-Switch inactive, entry allowed.

        AC4: After deactivation and save_state(), restarting without KILL_SWITCH env
        should result in Kill-Switch being inactive and check_risk_limits() returning True.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            os.environ.pop("KILL_SWITCH", None)  # Ensure env is not set

            # Phase 1: Start with inactive Kill-Switch
            core_state.balance = 10000.0
            core_state.positions = {}
            core_state.iteration_counter = 1
            core_state.risk_control_state = RiskControlState(
                kill_switch_active=False,
                daily_start_equity=10000.0,
                daily_start_date="2025-11-30",
            )

            # Phase 2: Activate Kill-Switch at runtime
            core_state.risk_control_state = activate_kill_switch(
                core_state.risk_control_state,
                reason="runtime:manual",
            )
            self.assertTrue(core_state.risk_control_state.kill_switch_active)

            # Verify check_risk_limits returns False (entry blocked)
            result = check_risk_limits(
                risk_control_state=core_state.risk_control_state,
                total_equity=10000.0,
                risk_control_enabled=True,
            )
            self.assertFalse(result)

            # Phase 3: Deactivate Kill-Switch
            core_state.risk_control_state = deactivate_kill_switch(
                core_state.risk_control_state,
                reason="runtime:resume",
                total_equity=9500.0,
            )
            self.assertFalse(core_state.risk_control_state.kill_switch_active)
            self.assertEqual(core_state.risk_control_state.kill_switch_reason, "runtime:resume")
            # AC1: triggered_at should be preserved
            self.assertIsNotNone(core_state.risk_control_state.kill_switch_triggered_at)

            # Phase 4: Save state
            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.save_state()

            # Verify saved state
            saved_data = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertFalse(saved_data["risk_control"]["kill_switch_active"])
            self.assertEqual(saved_data["risk_control"]["kill_switch_reason"], "runtime:resume")
            self.assertIsNotNone(saved_data["risk_control"]["kill_switch_triggered_at"])

            # Phase 5: Simulate restart - reset state and reload
            core_state.balance = 0.0
            core_state.positions = {}
            core_state.iteration_counter = 0
            core_state.risk_control_state = RiskControlState()

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.load_state()

            # Verify Kill-Switch is inactive after restart
            self.assertFalse(core_state.risk_control_state.kill_switch_active)
            self.assertEqual(core_state.risk_control_state.kill_switch_reason, "runtime:resume")

            # Verify check_risk_limits returns True (entry allowed)
            # Note: Disable daily_loss_limit to avoid triggering it with 9500/10000 = -5%
            result = check_risk_limits(
                risk_control_state=core_state.risk_control_state,
                total_equity=9500.0,
                risk_control_enabled=True,
                daily_loss_limit_enabled=False,
            )
            self.assertTrue(result)

    def test_scenario_b_env_override_takes_precedence_after_deactivation(self) -> None:
        """Scenario B: With KILL_SWITCH=true env, deactivation is overridden on restart.

        AC4: Even if Kill-Switch is deactivated at runtime and saved, restarting with
        KILL_SWITCH=true should result in Kill-Switch being active (env takes precedence).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"

            # Phase 1: Start with active Kill-Switch (from env)
            os.environ["KILL_SWITCH"] = "true"
            core_state.balance = 10000.0
            core_state.positions = {}
            core_state.iteration_counter = 1
            core_state.risk_control_state = RiskControlState(
                kill_switch_active=True,
                kill_switch_reason="env:KILL_SWITCH",
                kill_switch_triggered_at="2025-11-30T10:00:00+00:00",
            )

            # Phase 2: Deactivate Kill-Switch at runtime
            # Note: In a real scenario, this might be allowed temporarily within the session
            core_state.risk_control_state = deactivate_kill_switch(
                core_state.risk_control_state,
                reason="runtime:resume",
            )
            self.assertFalse(core_state.risk_control_state.kill_switch_active)

            # Phase 3: Save state (with deactivated Kill-Switch)
            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.save_state()

            # Verify saved state shows deactivated
            saved_data = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertFalse(saved_data["risk_control"]["kill_switch_active"])

            # Phase 4: Simulate restart with KILL_SWITCH=true still set
            core_state.balance = 0.0
            core_state.positions = {}
            core_state.iteration_counter = 0
            core_state.risk_control_state = RiskControlState()

            # KILL_SWITCH=true is still set in env
            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.load_state()

            # Verify Kill-Switch is ACTIVE after restart (env takes precedence)
            self.assertTrue(core_state.risk_control_state.kill_switch_active)
            self.assertEqual(core_state.risk_control_state.kill_switch_reason, "env:KILL_SWITCH")

            # Verify check_risk_limits returns False (entry blocked)
            result = check_risk_limits(
                risk_control_state=core_state.risk_control_state,
                total_equity=10000.0,
                risk_control_enabled=True,
            )
            self.assertFalse(result)

    def test_deactivation_preserves_triggered_at_for_audit(self) -> None:
        """AC1: Deactivation should preserve kill_switch_triggered_at for audit trail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            os.environ.pop("KILL_SWITCH", None)

            original_triggered_at = "2025-11-30T10:00:00+00:00"

            # Set up state with active Kill-Switch
            core_state.balance = 10000.0
            core_state.positions = {}
            core_state.iteration_counter = 1
            core_state.risk_control_state = RiskControlState(
                kill_switch_active=True,
                kill_switch_reason="runtime:manual",
                kill_switch_triggered_at=original_triggered_at,
                daily_loss_triggered=True,
            )

            # Deactivate
            core_state.risk_control_state = deactivate_kill_switch(
                core_state.risk_control_state,
                reason="runtime:resume",
            )

            # Verify triggered_at is preserved
            self.assertEqual(
                core_state.risk_control_state.kill_switch_triggered_at,
                original_triggered_at,
            )

            # Save and reload
            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.save_state()

            core_state.risk_control_state = RiskControlState()

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.load_state()

            # Verify triggered_at is still preserved after restart
            self.assertEqual(
                core_state.risk_control_state.kill_switch_triggered_at,
                original_triggered_at,
            )

    def test_deactivation_preserves_daily_loss_fields(self) -> None:
        """AC1: Deactivation should not modify daily loss related fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            os.environ.pop("KILL_SWITCH", None)

            # Set up state with active Kill-Switch and daily loss data
            core_state.balance = 8000.0
            core_state.positions = {}
            core_state.iteration_counter = 5
            core_state.risk_control_state = RiskControlState(
                kill_switch_active=True,
                kill_switch_reason="daily_loss_limit",
                kill_switch_triggered_at="2025-11-30T10:00:00+00:00",
                daily_start_equity=10000.0,
                daily_start_date="2025-11-30",
                daily_loss_pct=-20.0,
                daily_loss_triggered=True,
            )

            # Deactivate
            core_state.risk_control_state = deactivate_kill_switch(
                core_state.risk_control_state,
                reason="runtime:resume",
            )

            # Verify daily loss fields are preserved
            self.assertEqual(core_state.risk_control_state.daily_start_equity, 10000.0)
            self.assertEqual(core_state.risk_control_state.daily_start_date, "2025-11-30")
            self.assertEqual(core_state.risk_control_state.daily_loss_pct, -20.0)
            self.assertTrue(core_state.risk_control_state.daily_loss_triggered)

            # Save and reload
            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.save_state()

            core_state.risk_control_state = RiskControlState()

            with mock.patch.object(core_state, "STATE_JSON", state_path):
                core_state.load_state()

            # Verify daily loss fields are still preserved after restart
            self.assertEqual(core_state.risk_control_state.daily_start_equity, 10000.0)
            self.assertEqual(core_state.risk_control_state.daily_start_date, "2025-11-30")
            self.assertEqual(core_state.risk_control_state.daily_loss_pct, -20.0)
            self.assertTrue(core_state.risk_control_state.daily_loss_triggered)


class SignalFilteringIntegrationTests(TestCase):
    """Integration tests for signal filtering logic (Story 7.2.3).

    Covers:
    - AC1: Signal filtering based on check_risk_limits result (allow_entry)
    - AC2: Kill-Switch active scenario blocking entry but allowing close/hold
    - AC3: Structured logging for blocked entry signals
    - AC4: CSV audit record for blocked entry signals
    - AC5: Test coverage for boundary conditions
    """

    def setUp(self) -> None:
        self._orig_balance = core_state.balance
        self._orig_positions = copy.deepcopy(core_state.positions)
        self._orig_iteration = core_state.iteration_counter
        self._orig_risk_control_state = core_state.risk_control_state

    def tearDown(self) -> None:
        core_state.balance = self._orig_balance
        core_state.positions = copy.deepcopy(self._orig_positions)
        core_state.iteration_counter = self._orig_iteration
        core_state.risk_control_state = self._orig_risk_control_state

    def test_process_ai_decisions_blocks_entry_when_allow_entry_false(self) -> None:
        """AC1/AC2: Entry signals should be blocked when allow_entry=False."""
        from unittest.mock import MagicMock, patch
        import bot

        # Mock dependencies
        mock_executor = MagicMock()
        mock_fetch_market_data = MagicMock(return_value={"price": 50000.0})
        mock_log_ai_decision = MagicMock()
        mock_execute_entry = MagicMock()
        mock_execute_close = MagicMock()

        decisions = {
            "BTC": {
                "signal": "entry",
                "side": "long",
                "leverage": 5,
                "profit_target": 52000.0,
                "stop_loss": 48000.0,
                "confidence": 80,
                "justification": "Test entry signal",
            }
        }

        with patch.object(bot, "_get_executor", return_value=mock_executor), \
             patch.object(bot, "fetch_market_data", mock_fetch_market_data), \
             patch.object(bot, "log_ai_decision", mock_log_ai_decision), \
             patch.object(bot, "execute_entry", mock_execute_entry), \
             patch.object(bot, "execute_close", mock_execute_close), \
             patch.object(bot, "SYMBOL_TO_COIN", {"BTCUSDT": "BTC"}), \
             patch.object(bot, "COIN_TO_SYMBOL", {"BTC": "BTCUSDT"}):

            # Call with allow_entry=False (Kill-Switch active)
            with self.assertLogs(level=logging.WARNING) as cm:
                bot.process_ai_decisions(
                    decisions,
                    allow_entry=False,
                    kill_switch_active=True,
                    kill_switch_reason="test:integration",
                )

        # Verify entry was NOT executed
        mock_execute_entry.assert_not_called()

        # Verify log_ai_decision was called twice:
        # 1. Original decision (signal="entry")
        # 2. Blocked decision (signal="blocked")
        self.assertEqual(mock_log_ai_decision.call_count, 2)

        # Verify the second call was for the blocked signal
        blocked_call = mock_log_ai_decision.call_args_list[1]
        self.assertEqual(blocked_call[0][0], "BTC")  # coin
        self.assertEqual(blocked_call[0][1], "blocked")  # signal
        self.assertIn("RISK_CONTROL_BLOCKED", blocked_call[0][2])  # reasoning
        self.assertIn("Kill-Switch active", blocked_call[0][2])

        # AC3: Verify structured log was produced
        self.assertTrue(
            any("entry blocked" in msg and "kill_switch_active=True" in msg for msg in cm.output),
            f"Expected structured log with kill_switch_active, got: {cm.output}",
        )

    def test_process_ai_decisions_allows_entry_when_allow_entry_true(self) -> None:
        """AC5 Scenario C: Entry signals should proceed when allow_entry=True."""
        from unittest.mock import MagicMock, patch
        import bot

        mock_executor = MagicMock()
        mock_fetch_market_data = MagicMock(return_value={"price": 50000.0})
        mock_log_ai_decision = MagicMock()
        mock_execute_entry = MagicMock()

        decisions = {
            "BTC": {
                "signal": "entry",
                "side": "long",
                "leverage": 5,
                "profit_target": 52000.0,
                "stop_loss": 48000.0,
                "confidence": 80,
                "justification": "Test entry signal",
            }
        }

        with patch.object(bot, "_get_executor", return_value=mock_executor), \
             patch.object(bot, "fetch_market_data", mock_fetch_market_data), \
             patch.object(bot, "log_ai_decision", mock_log_ai_decision), \
             patch.object(bot, "execute_entry", mock_execute_entry), \
             patch.object(bot, "SYMBOL_TO_COIN", {"BTCUSDT": "BTC"}), \
             patch.object(bot, "COIN_TO_SYMBOL", {"BTC": "BTCUSDT"}):

            bot.process_ai_decisions(
                decisions,
                allow_entry=True,
                kill_switch_active=False,
            )

        # Verify entry WAS executed
        mock_execute_entry.assert_called_once()

        # Verify log_ai_decision was called only once (original decision)
        self.assertEqual(mock_log_ai_decision.call_count, 1)
        self.assertEqual(mock_log_ai_decision.call_args[0][1], "entry")

    def test_process_ai_decisions_allows_close_when_allow_entry_false(self) -> None:
        """AC2/AC5 Scenario B: Close signals should proceed even when allow_entry=False."""
        from unittest.mock import MagicMock, patch
        import bot

        mock_executor = MagicMock()
        mock_fetch_market_data = MagicMock(return_value={"price": 50000.0})
        mock_log_ai_decision = MagicMock()
        mock_execute_entry = MagicMock()
        mock_execute_close = MagicMock()

        decisions = {
            "BTC": {
                "signal": "close",
                "confidence": 90,
                "justification": "Test close signal",
            }
        }

        with patch.object(bot, "_get_executor", return_value=mock_executor), \
             patch.object(bot, "fetch_market_data", mock_fetch_market_data), \
             patch.object(bot, "log_ai_decision", mock_log_ai_decision), \
             patch.object(bot, "execute_entry", mock_execute_entry), \
             patch.object(bot, "execute_close", mock_execute_close), \
             patch.object(bot, "SYMBOL_TO_COIN", {"BTCUSDT": "BTC"}), \
             patch.object(bot, "COIN_TO_SYMBOL", {"BTC": "BTCUSDT"}):

            bot.process_ai_decisions(
                decisions,
                allow_entry=False,
                kill_switch_active=True,
                kill_switch_reason="test:integration",
            )

        # Verify close WAS executed
        mock_execute_close.assert_called_once()

        # Verify entry was NOT executed
        mock_execute_entry.assert_not_called()

        # Verify log_ai_decision was called only once (no blocked record for close)
        self.assertEqual(mock_log_ai_decision.call_count, 1)
        self.assertEqual(mock_log_ai_decision.call_args[0][1], "close")

    def test_process_ai_decisions_allows_hold_when_allow_entry_false(self) -> None:
        """AC2/AC5 Scenario B: Hold signals should proceed even when allow_entry=False."""
        from unittest.mock import MagicMock, patch
        import bot

        mock_executor = MagicMock()
        mock_fetch_market_data = MagicMock(return_value={"price": 50000.0})
        mock_log_ai_decision = MagicMock()
        mock_execute_entry = MagicMock()
        mock_execute_close = MagicMock()

        decisions = {
            "BTC": {
                "signal": "hold",
                "confidence": 70,
                "justification": "Test hold signal",
            }
        }

        with patch.object(bot, "_get_executor", return_value=mock_executor), \
             patch.object(bot, "fetch_market_data", mock_fetch_market_data), \
             patch.object(bot, "log_ai_decision", mock_log_ai_decision), \
             patch.object(bot, "execute_entry", mock_execute_entry), \
             patch.object(bot, "execute_close", mock_execute_close), \
             patch.object(bot, "SYMBOL_TO_COIN", {"BTCUSDT": "BTC"}), \
             patch.object(bot, "COIN_TO_SYMBOL", {"BTC": "BTCUSDT"}):

            bot.process_ai_decisions(
                decisions,
                allow_entry=False,
                kill_switch_active=True,
                kill_switch_reason="test:integration",
            )

        # Verify hold was processed
        mock_executor.process_hold_signal.assert_called_once()

        # Verify entry and close were NOT executed
        mock_execute_entry.assert_not_called()
        mock_execute_close.assert_not_called()

        # Verify log_ai_decision was called only once (no blocked record for hold)
        self.assertEqual(mock_log_ai_decision.call_count, 1)
        self.assertEqual(mock_log_ai_decision.call_args[0][1], "hold")

    def test_blocked_entry_log_contains_required_fields(self) -> None:
        """AC3: Blocked entry log should contain coin, signal, allow_entry, kill_switch_active, reason."""
        from unittest.mock import MagicMock, patch
        import bot

        mock_executor = MagicMock()
        mock_fetch_market_data = MagicMock(return_value={"price": 50000.0})
        mock_log_ai_decision = MagicMock()
        mock_execute_entry = MagicMock()

        decisions = {
            "BTC": {
                "signal": "entry",
                "side": "long",
                "leverage": 5,
                "profit_target": 52000.0,
                "stop_loss": 48000.0,
                "confidence": 85,
                "justification": "Bullish momentum",
            }
        }

        with patch.object(bot, "_get_executor", return_value=mock_executor), \
             patch.object(bot, "fetch_market_data", mock_fetch_market_data), \
             patch.object(bot, "log_ai_decision", mock_log_ai_decision), \
             patch.object(bot, "execute_entry", mock_execute_entry), \
             patch.object(bot, "SYMBOL_TO_COIN", {"BTCUSDT": "BTC"}), \
             patch.object(bot, "COIN_TO_SYMBOL", {"BTC": "BTCUSDT"}):

            with self.assertLogs(level=logging.WARNING) as cm:
                bot.process_ai_decisions(
                    decisions,
                    allow_entry=False,
                    kill_switch_active=True,
                    kill_switch_reason="env:KILL_SWITCH",
                )

        # Verify all required fields are in the log
        log_output = "\n".join(cm.output)
        self.assertIn("coin=BTC", log_output)
        self.assertIn("signal=entry", log_output)
        self.assertIn("allow_entry=False", log_output)
        self.assertIn("kill_switch_active=True", log_output)
        self.assertIn("Kill-Switch active", log_output)
        self.assertIn("env:KILL_SWITCH", log_output)

    def test_blocked_entry_csv_record_contains_risk_control_marker(self) -> None:
        """AC4: Blocked entry should produce CSV record with RISK_CONTROL_BLOCKED marker."""
        from unittest.mock import MagicMock, patch
        import bot

        mock_executor = MagicMock()
        mock_fetch_market_data = MagicMock(return_value={"price": 50000.0})
        mock_log_ai_decision = MagicMock()
        mock_execute_entry = MagicMock()

        decisions = {
            "BTC": {
                "signal": "entry",
                "side": "long",
                "leverage": 5,
                "profit_target": 52000.0,
                "stop_loss": 48000.0,
                "confidence": 75,
                "justification": "Strong support level",
            }
        }

        with patch.object(bot, "_get_executor", return_value=mock_executor), \
             patch.object(bot, "fetch_market_data", mock_fetch_market_data), \
             patch.object(bot, "log_ai_decision", mock_log_ai_decision), \
             patch.object(bot, "execute_entry", mock_execute_entry), \
             patch.object(bot, "SYMBOL_TO_COIN", {"BTCUSDT": "BTC"}), \
             patch.object(bot, "COIN_TO_SYMBOL", {"BTC": "BTCUSDT"}):

            bot.process_ai_decisions(
                decisions,
                allow_entry=False,
                kill_switch_active=True,
                kill_switch_reason="runtime:manual",
            )

        # Find the blocked call
        blocked_calls = [
            call for call in mock_log_ai_decision.call_args_list
            if call[0][1] == "blocked"
        ]
        self.assertEqual(len(blocked_calls), 1)

        blocked_call = blocked_calls[0]
        reasoning = blocked_call[0][2]

        # Verify RISK_CONTROL_BLOCKED marker
        self.assertIn("RISK_CONTROL_BLOCKED", reasoning)
        self.assertIn("Kill-Switch active", reasoning)
        self.assertIn("runtime:manual", reasoning)
        # Verify original justification is preserved
        self.assertIn("Strong support level", reasoning)

    def test_non_kill_switch_risk_control_produces_appropriate_log(self) -> None:
        """AC3: Non-Kill-Switch risk control should produce appropriate log message."""
        from unittest.mock import MagicMock, patch
        import bot

        mock_executor = MagicMock()
        mock_fetch_market_data = MagicMock(return_value={"price": 50000.0})
        mock_log_ai_decision = MagicMock()
        mock_execute_entry = MagicMock()

        decisions = {
            "BTC": {
                "signal": "entry",
                "side": "long",
                "leverage": 5,
                "profit_target": 52000.0,
                "stop_loss": 48000.0,
                "confidence": 80,
                "justification": "Test entry",
            }
        }

        with patch.object(bot, "_get_executor", return_value=mock_executor), \
             patch.object(bot, "fetch_market_data", mock_fetch_market_data), \
             patch.object(bot, "log_ai_decision", mock_log_ai_decision), \
             patch.object(bot, "execute_entry", mock_execute_entry), \
             patch.object(bot, "SYMBOL_TO_COIN", {"BTCUSDT": "BTC"}), \
             patch.object(bot, "COIN_TO_SYMBOL", {"BTC": "BTCUSDT"}):

            with self.assertLogs(level=logging.WARNING) as cm:
                # allow_entry=False but kill_switch_active=False
                # (future scenario: daily loss limit without Kill-Switch)
                bot.process_ai_decisions(
                    decisions,
                    allow_entry=False,
                    kill_switch_active=False,
                    kill_switch_reason=None,
                )

        # Verify log contains generic risk control message
        log_output = "\n".join(cm.output)
        self.assertIn("allow_entry=False", log_output)
        self.assertIn("kill_switch_active=False", log_output)
        self.assertIn("Risk control", log_output)


class KillSwitchAndStopLossTakeProfitIntegrationTests(TestCase):
    """Integration tests for Kill-Switch + SL/TP behaviour (Story 7.2.4).

    Focus: When Kill-Switch is active, SL/TP checks must still run in the
    main loop and trigger closes as usual; Kill-Switch only affects entry.
    """

    def setUp(self) -> None:
        self._orig_balance = core_state.balance
        self._orig_positions = copy.deepcopy(core_state.positions)
        self._orig_iteration = core_state.iteration_counter
        self._orig_risk_control_state = core_state.risk_control_state

        import bot  # Local import to avoid circulars at module import time

        self._bot = bot
        self._orig_bot_positions = copy.deepcopy(bot.positions)
        self._orig_bot_hyperliquid_trader = bot.hyperliquid_trader
        self._orig_bot_risk_control_enabled = bot.RISK_CONTROL_ENABLED

    def tearDown(self) -> None:
        core_state.balance = self._orig_balance
        core_state.positions = copy.deepcopy(self._orig_positions)
        core_state.iteration_counter = self._orig_iteration
        core_state.risk_control_state = self._orig_risk_control_state

        self._bot.positions = copy.deepcopy(self._orig_bot_positions)
        self._bot.hyperliquid_trader = self._orig_bot_hyperliquid_trader
        self._bot.RISK_CONTROL_ENABLED = self._orig_bot_risk_control_enabled

    def test_run_iteration_triggers_sl_tp_close_when_kill_switch_active(self) -> None:
        from unittest.mock import MagicMock, patch
        import bot

        core_state.risk_control_state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="test:sl-tp-integration",
            kill_switch_triggered_at="2025-11-30T12:00:00+00:00",
        )

        bot.RISK_CONTROL_ENABLED = True

        class _DummyTrader:
            def __init__(self) -> None:
                self.is_live = False

        bot.hyperliquid_trader = _DummyTrader()

        bot.positions = {
            "ETH": {
                "side": "long",
                "entry_price": 100.0,
                "stop_loss": 90.0,
                "profit_target": 120.0,
                "quantity": 1.0,
                "margin": 50.0,
                "fees_paid": 0.0,
                "fee_rate": 0.001,
                "leverage": 1.0,
            }
        }

        fake_market_data = {
            "price": 100.0,
            "low": 85.0,
            "high": 110.0,
        }

        with patch.object(bot, "SYMBOL_TO_COIN", {"ETHUSDT": "ETH"}), \
             patch.object(bot, "COIN_TO_SYMBOL", {"ETH": "ETHUSDT"}), \
             patch.object(bot, "get_binance_client", MagicMock(return_value=object())), \
             patch.object(bot, "call_deepseek_api", MagicMock(return_value=None)), \
             patch.object(bot, "_display_portfolio_summary", MagicMock()), \
             patch.object(bot, "_log_portfolio_state", MagicMock()), \
             patch.object(bot, "send_telegram_message", MagicMock()), \
             patch.object(bot, "save_state", MagicMock()), \
             patch.object(bot, "sleep_with_countdown", MagicMock()), \
             patch.object(bot, "fetch_market_data", MagicMock(return_value=fake_market_data)), \
             patch.object(bot, "execute_close") as mock_execute_close:

            bot._run_iteration()

        mock_execute_close.assert_called_once_with(
            "ETH",
            {"justification": "Stop loss hit"},
            90.0,
        )


class DailyLossLimitNotificationIntegrationTests(TestCase):
    """Integration tests for daily loss limit notification (Story 7.3.4).

    Covers:
    - AC2: Notification triggered only on first daily loss limit trigger
    - AC3: Error handling in notification path
    - AC4: Integration with check_daily_loss_limit and check_risk_limits
    """

    def test_check_daily_loss_limit_calls_notify_fn_on_first_trigger(self) -> None:
        """AC2: notify_fn should be called exactly once when threshold is first reached."""
        from core.risk_control import check_daily_loss_limit, RiskControlState

        state = RiskControlState(
            kill_switch_active=False,
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
            daily_loss_pct=0.0,
            daily_loss_triggered=False,
        )

        notify_calls = []

        def mock_notify(loss_pct, limit_pct, daily_start_equity, current_equity):
            notify_calls.append({
                "loss_pct": loss_pct,
                "limit_pct": limit_pct,
                "daily_start_equity": daily_start_equity,
                "current_equity": current_equity,
            })

        # First call: threshold reached (-6% <= -5%)
        result = check_daily_loss_limit(
            state=state,
            current_equity=9400.0,  # -6% loss
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
            risk_control_enabled=True,
            positions_count=0,
            notify_fn=mock_notify,
        )

        self.assertTrue(result)  # Kill-Switch was triggered
        self.assertEqual(len(notify_calls), 1)  # Notification called once
        self.assertAlmostEqual(notify_calls[0]["loss_pct"], -6.0, places=1)
        self.assertEqual(notify_calls[0]["limit_pct"], 5.0)
        self.assertEqual(notify_calls[0]["daily_start_equity"], 10000.0)
        self.assertEqual(notify_calls[0]["current_equity"], 9400.0)

    def test_check_daily_loss_limit_does_not_notify_on_subsequent_calls(self) -> None:
        """AC2: notify_fn should NOT be called on subsequent iterations after first trigger."""
        from core.risk_control import check_daily_loss_limit, RiskControlState

        state = RiskControlState(
            kill_switch_active=True,  # Already active
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
            daily_loss_pct=-6.0,
            daily_loss_triggered=True,  # Already triggered
        )

        notify_calls = []

        def mock_notify(loss_pct, limit_pct, daily_start_equity, current_equity):
            notify_calls.append(True)

        # Second call: threshold still exceeded but already triggered
        result = check_daily_loss_limit(
            state=state,
            current_equity=9300.0,  # -7% loss (even worse)
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
            risk_control_enabled=True,
            positions_count=0,
            notify_fn=mock_notify,
        )

        self.assertFalse(result)  # No new trigger
        self.assertEqual(len(notify_calls), 0)  # No notification

    def test_check_risk_limits_passes_notify_fn_to_daily_loss_check(self) -> None:
        """AC4: check_risk_limits should pass notify_daily_loss_fn to check_daily_loss_limit."""
        from core.risk_control import check_risk_limits, RiskControlState

        state = RiskControlState(
            kill_switch_active=False,
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
            daily_loss_pct=0.0,
            daily_loss_triggered=False,
        )

        notify_calls = []

        def mock_notify(loss_pct, limit_pct, daily_start_equity, current_equity):
            notify_calls.append({
                "loss_pct": loss_pct,
                "limit_pct": limit_pct,
            })

        # Call check_risk_limits with notify callback
        result = check_risk_limits(
            risk_control_state=state,
            total_equity=9400.0,  # -6% loss
            risk_control_enabled=True,
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
            positions_count=0,
            notify_daily_loss_fn=mock_notify,
        )

        self.assertFalse(result)  # Entry blocked
        self.assertEqual(len(notify_calls), 1)  # Notification was called

    def test_notification_failure_does_not_affect_kill_switch_activation(self) -> None:
        """AC3: Notification failure should not prevent Kill-Switch activation."""
        from core.risk_control import check_daily_loss_limit, RiskControlState

        state = RiskControlState(
            kill_switch_active=False,
            daily_start_equity=10000.0,
            daily_start_date="2025-11-30",
            daily_loss_pct=0.0,
            daily_loss_triggered=False,
        )

        def failing_notify(loss_pct, limit_pct, daily_start_equity, current_equity):
            raise Exception("Network error - Telegram unavailable")

        # Call with failing notify function
        with self.assertLogs(level=logging.ERROR) as cm:
            result = check_daily_loss_limit(
                state=state,
                current_equity=9400.0,  # -6% loss
                daily_loss_limit_enabled=True,
                daily_loss_limit_pct=5.0,
                risk_control_enabled=True,
                positions_count=0,
                notify_fn=failing_notify,
            )

        # Kill-Switch should still be activated despite notification failure
        self.assertTrue(result)
        self.assertTrue(state.kill_switch_active)
        self.assertTrue(state.daily_loss_triggered)

        # Error should be logged
        self.assertTrue(
            any("Failed to send daily loss limit notification" in msg for msg in cm.output),
            f"Expected notification error log, got: {cm.output}",
        )

    def test_notification_not_called_when_telegram_not_configured(self) -> None:
        """AC2: When Telegram is not configured, callback should be None."""
        from notifications.telegram import create_daily_loss_limit_notify_callback

        # No bot_token
        callback = create_daily_loss_limit_notify_callback(
            bot_token="",
            chat_id="123456",
        )
        self.assertIsNone(callback)

        # No chat_id
        callback = create_daily_loss_limit_notify_callback(
            bot_token="test_token",
            chat_id="",
        )
        self.assertIsNone(callback)

    def test_end_to_end_daily_loss_trigger_with_notification(self) -> None:
        """End-to-end test: Daily loss trigger → Kill-Switch activation → Notification."""
        from core.risk_control import check_risk_limits, update_daily_baseline, RiskControlState
        from notifications.telegram import create_daily_loss_limit_notify_callback
        from unittest.mock import MagicMock

        # Create fresh state
        state = RiskControlState()

        # Simulate first iteration: set daily baseline
        update_daily_baseline(state, current_equity=10000.0)
        self.assertEqual(state.daily_start_equity, 10000.0)
        self.assertFalse(state.kill_switch_active)

        # Create mock notification callback
        mock_send = MagicMock()
        notify_callback = create_daily_loss_limit_notify_callback(
            bot_token="test_token",
            chat_id="123456",
            send_fn=mock_send,
        )
        self.assertIsNotNone(notify_callback)

        # Simulate iteration with significant loss (-6%)
        result = check_risk_limits(
            risk_control_state=state,
            total_equity=9400.0,
            risk_control_enabled=True,
            daily_loss_limit_enabled=True,
            daily_loss_limit_pct=5.0,
            positions_count=2,
            notify_daily_loss_fn=notify_callback,
        )

        # Verify Kill-Switch was activated
        self.assertFalse(result)  # Entry blocked
        self.assertTrue(state.kill_switch_active)
        self.assertTrue(state.daily_loss_triggered)

        # Verify notification was sent
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["parse_mode"], "MarkdownV2")
        self.assertIn("-6", call_kwargs["text"])  # Loss percentage in message


if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
