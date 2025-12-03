"""
Handler for /kill command to activate Kill-Switch.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Optional, TYPE_CHECKING

from notifications.commands.base import (
    TelegramCommand,
    CommandResult,
    escape_markdown,
)

if TYPE_CHECKING:
    from core.risk_control import RiskControlState


def handle_kill_command(
    cmd: TelegramCommand,
    state: "RiskControlState",
    *,
    activate_fn: Optional[Callable[["RiskControlState", str, int], "RiskControlState"]] = None,
    positions_count: int = 0,
) -> CommandResult:
    """Handle the /kill command to activate Kill-Switch.
    
    This function activates Kill-Switch via the risk control API and returns
    a result with the response message.
    
    Args:
        cmd: The TelegramCommand object for /kill.
        state: The current RiskControlState to modify.
        activate_fn: Optional function to activate Kill-Switch. If None, uses
            the default activate_kill_switch from core.risk_control.
        positions_count: Current number of open positions for notification.
    
    Returns:
        CommandResult with success status and response message.
    
    References:
        - AC1: /kill 命令激活 Kill-Switch
        - AC3: 日志与审计
    """
    from core.risk_control import activate_kill_switch
    
    reason = "Manual trigger via Telegram"
    triggered_at = datetime.now(timezone.utc)
    
    # Log command receipt (AC3)
    logging.info(
        "Telegram /kill command received: chat_id=%s, message_id=%d",
        cmd.chat_id,
        cmd.message_id,
    )
    
    # Check if already active
    if state.kill_switch_active:
        message = (
            "⚠️ *Kill\\-Switch 已处于激活状态*\n\n"
            f"*当前原因:* {escape_markdown(state.kill_switch_reason or 'unknown')}\n"
            f"*激活时间:* `{state.kill_switch_triggered_at}`\n\n"
            "无需重复激活。"
        )
        logging.info(
            "Telegram /kill: Kill-Switch already active, reason=%s",
            state.kill_switch_reason,
        )
        return CommandResult(
            success=True,
            message=message,
            state_changed=False,
            action=None,
        )
    
    # Activate Kill-Switch
    if activate_fn is not None:
        new_state = activate_fn(state, reason, positions_count)
    else:
        new_state = activate_kill_switch(
            state,
            reason=reason,
            triggered_at=triggered_at,
            positions_count=positions_count,
        )
    
    # Copy state changes back to the mutable state object
    state.kill_switch_active = new_state.kill_switch_active
    state.kill_switch_reason = new_state.kill_switch_reason
    state.kill_switch_triggered_at = new_state.kill_switch_triggered_at
    
    # Build response message
    message = (
        "🚨 *Kill\\-Switch 已激活*\n\n"
        f"*触发原因:* {escape_markdown(reason)}\n"
        f"*触发时间:* `{state.kill_switch_triggered_at}`\n"
        f"*当前持仓:* {positions_count} 个\n\n"
        "⚠️ 新开仓信号已被阻止，现有持仓的止损/止盈仍正常执行。\n\n"
        "💡 恢复交易请使用: `/resume`"
    )
    
    # Log state change (AC3)
    logging.warning(
        "Telegram /kill: Kill-Switch activated | chat_id=%s | reason=%s | "
        "positions_count=%d | triggered_at=%s",
        cmd.chat_id,
        reason,
        positions_count,
        state.kill_switch_triggered_at,
    )
    
    return CommandResult(
        success=True,
        message=message,
        state_changed=True,
        action="KILL_SWITCH_ACTIVATED",
    )
