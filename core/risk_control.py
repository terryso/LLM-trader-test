"""
Risk control state management.

This module defines the RiskControlState data structure for managing
risk control features including Kill-Switch and daily loss limits.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


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
