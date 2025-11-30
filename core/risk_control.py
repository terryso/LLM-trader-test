"""
Risk control state management.

This module defines the RiskControlState data structure for managing
risk control features including Kill-Switch and daily loss limits.
It also provides the check_risk_limits() entry point for the main trading loop.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, asdict, replace
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


@dataclass
class RiskControlState:
    """Risk control system state data structure.

    This dataclass holds all state related to risk control features,
    including Kill-Switch status and daily loss tracking.

    Attributes:
        kill_switch_active: Whether Kill-Switch is currently activated.
        kill_switch_reason: The reason for Kill-Switch activation.
        kill_switch_triggered_at: ISO 8601 timestamp when Kill-Switch was triggered.
        daily_start_equity: Starting equity for the current day (UTC).
        daily_start_date: Date string (YYYY-MM-DD) for daily baseline.
        daily_loss_pct: Current daily loss percentage (negative = loss).
        daily_loss_triggered: Whether Kill-Switch was triggered by daily loss limit.
    """

    kill_switch_active: bool = False
    kill_switch_reason: Optional[str] = None
    kill_switch_triggered_at: Optional[str] = None
    daily_start_equity: Optional[float] = None
    daily_start_date: Optional[str] = None
    daily_loss_pct: float = 0.0
    daily_loss_triggered: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state to a dictionary for JSON persistence.

        Returns:
            A dictionary representation of the state that can be
            serialized with json.dumps().
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiskControlState":
        """Deserialize state from a dictionary.

        Handles missing fields gracefully by using default values.

        Args:
            data: Dictionary containing state fields. Missing fields
                will use their default values.

        Returns:
            A new RiskControlState instance with values from the dictionary.
        """
        return cls(
            kill_switch_active=data.get("kill_switch_active", False),
            kill_switch_reason=data.get("kill_switch_reason"),
            kill_switch_triggered_at=data.get("kill_switch_triggered_at"),
            daily_start_equity=data.get("daily_start_equity"),
            daily_start_date=data.get("daily_start_date"),
            daily_loss_pct=data.get("daily_loss_pct", 0.0),
            daily_loss_triggered=data.get("daily_loss_triggered", False),
        )


def check_risk_limits(
    risk_control_state: RiskControlState,
    total_equity: Optional[float] = None,
    iteration_time: Optional[datetime] = None,
    risk_control_enabled: bool = True,
) -> bool:
    """Check risk limits at the start of each trading iteration.

    This is the unified entry point for risk control checks in the main loop.
    It is called at the beginning of each iteration, before market data fetching
    and LLM decision making.

    When Kill-Switch is active, this function returns False to signal that
    new entry trades should be blocked. Close trades and SL/TP checks are
    not affected by this function.

    Args:
        risk_control_state: The current risk control state object.
        total_equity: Current total account equity (optional, for future use).
        iteration_time: Current iteration timestamp (optional, for future use).
        risk_control_enabled: Whether risk control is enabled (from RISK_CONTROL_ENABLED).

    Returns:
        True if new entry trades should be allowed, False if they should be blocked
        (e.g., Kill-Switch is active).
    """
    if not risk_control_enabled:
        logging.info("Risk control check skipped: RISK_CONTROL_ENABLED=False")
        return True

    # Log the risk control check
    logging.debug(
        "Risk control check: kill_switch_active=%s, daily_loss_pct=%.2f%%",
        risk_control_state.kill_switch_active,
        risk_control_state.daily_loss_pct,
    )

    # Check Kill-Switch status (Epic 7.2)
    if risk_control_state.kill_switch_active:
        logging.warning(
            "Kill-Switch is active: reason=%s, triggered_at=%s",
            risk_control_state.kill_switch_reason,
            risk_control_state.kill_switch_triggered_at,
        )
        return False

    # Future Epic 7.3: Check daily loss limit
    # if daily_loss_limit_enabled and check_daily_loss_limit(...):
    #     return False

    return True


def activate_kill_switch(
    state: RiskControlState,
    reason: str,
    triggered_at: Optional[datetime] = None,
) -> RiskControlState:
    """Activate the Kill-Switch and return a new state.

    This function creates a new RiskControlState with Kill-Switch activated.
    It sets the reason and timestamp for the activation.

    Args:
        state: The current risk control state.
        reason: The reason for activating Kill-Switch (e.g., "env:KILL_SWITCH",
            "runtime:manual", "daily_loss_limit").
        triggered_at: The timestamp when Kill-Switch was triggered. If None,
            uses current UTC time.

    Returns:
        A new RiskControlState with Kill-Switch activated.
    """
    if triggered_at is None:
        triggered_at = datetime.now(timezone.utc)

    triggered_at_str = triggered_at.isoformat()

    return replace(
        state,
        kill_switch_active=True,
        kill_switch_reason=reason,
        kill_switch_triggered_at=triggered_at_str,
    )


def deactivate_kill_switch(state: RiskControlState) -> RiskControlState:
    """Deactivate the Kill-Switch and return a new state.

    This function creates a new RiskControlState with Kill-Switch deactivated.
    It clears the reason and timestamp fields.

    Args:
        state: The current risk control state.

    Returns:
        A new RiskControlState with Kill-Switch deactivated.
    """
    return replace(
        state,
        kill_switch_active=False,
        kill_switch_reason=None,
        kill_switch_triggered_at=None,
    )


def apply_kill_switch_env_override(
    state: RiskControlState,
    kill_switch_env: Optional[str] = None,
) -> Tuple[RiskControlState, bool]:
    """Apply KILL_SWITCH environment variable override to the state.

    This function implements the priority logic for Kill-Switch:
    - If KILL_SWITCH env var is explicitly set to 'true' or 'false', it overrides
      the persisted state.
    - If KILL_SWITCH env var is not set, the persisted state is preserved.

    Args:
        state: The current risk control state (typically loaded from persistence).
        kill_switch_env: The value of KILL_SWITCH environment variable. If None,
            reads from os.environ.

    Returns:
        A tuple of (new_state, was_overridden) where:
        - new_state: The potentially modified RiskControlState.
        - was_overridden: True if the env var caused a state change.
    """
    if kill_switch_env is None:
        kill_switch_env = os.environ.get("KILL_SWITCH")

    if kill_switch_env is None:
        # Env var not set, preserve persisted state
        return state, False

    normalized = kill_switch_env.strip().lower()

    if normalized in {"1", "true", "yes", "on"}:
        # Env var explicitly enables Kill-Switch
        if not state.kill_switch_active:
            new_state = activate_kill_switch(state, reason="env:KILL_SWITCH")
            logging.warning(
                "Kill-Switch activated via environment variable: KILL_SWITCH=%s",
                kill_switch_env,
            )
            return new_state, True
        else:
            # Already active, just update reason if different
            if state.kill_switch_reason != "env:KILL_SWITCH":
                new_state = replace(state, kill_switch_reason="env:KILL_SWITCH")
                return new_state, True
            return state, False

    if normalized in {"0", "false", "no", "off"}:
        # Env var explicitly disables Kill-Switch
        if state.kill_switch_active:
            new_state = deactivate_kill_switch(state)
            logging.info(
                "Kill-Switch deactivated via environment variable: KILL_SWITCH=%s",
                kill_switch_env,
            )
            return new_state, True
        return state, False

    # Invalid value, preserve persisted state and log warning
    logging.warning(
        "Invalid KILL_SWITCH environment variable value '%s'; ignoring. "
        "Valid values: true, false, 1, 0, yes, no, on, off",
        kill_switch_env,
    )
    return state, False
