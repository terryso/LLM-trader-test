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
from pathlib import Path
from unittest import TestCase, mock

import core.state as core_state
from core.risk_control import (
    RiskControlState,
    check_risk_limits,
    activate_kill_switch,
    apply_kill_switch_env_override,
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
            self.assertIsNone(core_state.risk_control_state.kill_switch_reason)
            self.assertIsNone(core_state.risk_control_state.kill_switch_triggered_at)
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


if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
