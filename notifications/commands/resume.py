"""
Handler for /resume command to deactivate Kill-Switch.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Optional, TYPE_CHECKING

from notifications.commands.base import TelegramCommand, CommandResult

if TYPE_CHECKING:
    from core.risk_control import RiskControlState


def handle_resume_command(
    cmd: TelegramCommand,
    state: "RiskControlState",
    *,
    deactivate_fn: Optional[Callable[["RiskControlState", str], "RiskControlState"]] = None,
    force: bool = False,
) -> CommandResult:
    """Handle the /resume command to deactivate Kill-Switch.
    
    This function deactivates Kill-Switch via the risk control API, with
    optional protection when daily loss limits are triggered.
    
    Args:
        cmd: The TelegramCommand object for /resume.
        state: The current RiskControlState to modify.
        deactivate_fn: Optional function to deactivate Kill-Switch. If None, uses
            the default deactivate_kill_switch from core.risk_control.
        force: If True, force deactivation even if daily_loss_triggered is True.
    
    Returns:
        CommandResult with success status and response message.
    """
    from core.risk_control import deactivate_kill_switch
    
    # Log command receipt (AC3)
    logging.info(
        "Telegram /resume command received: chat_id=%s, message_id=%d, args=%s",
        cmd.chat_id,
        cmd.message_id,
        cmd.args,
    )
    
    # Check if Kill-Switch is not active
    if not state.kill_switch_active:
        message = (
            "ℹ️ *Kill\\-Switch 当前未激活*\n\n"
            "交易功能正常运行中，无需恢复。"
        )
        logging.info(
            "Telegram /resume: Kill-Switch not active, no action needed"
        )
        return CommandResult(
            success=True,
            message=message,
            state_changed=False,
            action=None,
        )
    
    # Check if daily loss triggered and force is not set
    if state.daily_loss_triggered and not force:
        message = (
            "❌ *无法解除 Kill\\-Switch*\n\n"
            "*原因:* 每日亏损限制仍在生效\n"
            f"*当日亏损:* `{state.daily_loss_pct:.2f}%`\n\n"
            "💡 如需强制恢复，请使用 `/reset_daily` 重置每日亏损限制后再试。"
        )
        logging.warning(
            "Telegram /resume: blocked by daily_loss_triggered | "
            "chat_id=%s | daily_loss_pct=%.2f%%",
            cmd.chat_id,
            state.daily_loss_pct,
        )
        return CommandResult(
            success=False,
            message=message,
            state_changed=False,
            action="RESUME_BLOCKED_DAILY_LOSS",
        )
    
    # Deactivate Kill-Switch
    reason = "telegram:/resume"
    if deactivate_fn is not None:
        new_state = deactivate_fn(state, reason)
    else:
        new_state = deactivate_kill_switch(
            state,
            reason=reason,
        )
    
    # Copy state changes back to the mutable state object
    state.kill_switch_active = new_state.kill_switch_active
    state.kill_switch_reason = new_state.kill_switch_reason
    
    deactivated_at = datetime.now(timezone.utc).isoformat()
    
    # Build response message
    message = (
        "✅ *Kill\\-Switch 已解除*\n\n"
        f"*解除时间:* `{deactivated_at}`\n"
        f"*解除原因:* Telegram 命令 /resume\n\n"
        "📈 交易功能已恢复正常，新开仓信号将被正常处理。"
    )
    
    # Log state change (AC3)
    logging.info(
        "Telegram /resume: Kill-Switch deactivated | chat_id=%s | "
        "reason=%s | deactivated_at=%s",
        cmd.chat_id,
        reason,
        deactivated_at,
    )
    
    return CommandResult(
        success=True,
        message=message,
        state_changed=True,
        action="KILL_SWITCH_DEACTIVATED",
    )
