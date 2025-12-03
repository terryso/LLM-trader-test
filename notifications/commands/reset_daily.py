"""
Handler for /reset_daily command to manually reset daily loss baseline.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional, TYPE_CHECKING

from notifications.commands.base import TelegramCommand, CommandResult

if TYPE_CHECKING:
    from core.risk_control import RiskControlState


def handle_reset_daily_command(
    cmd: TelegramCommand,
    state: "RiskControlState",
    *,
    total_equity: Optional[float],
    risk_control_enabled: bool,
    reset_fn: Optional[Callable[["RiskControlState", float, str], "RiskControlState"]] = None,
) -> CommandResult:
    """Handle the /reset_daily command to manually reset daily loss baseline.

    This function resets the daily loss baseline to the current equity, allowing
    users to start a new risk window after reviewing a large drawdown day.

    IMPORTANT: This command does NOT automatically deactivate Kill-Switch.
    Users must explicitly call /resume after /reset_daily to resume
    trading. This design prevents accidental resumption after large losses.

    Args:
        cmd: The TelegramCommand object for /reset_daily.
        state: The current RiskControlState to modify.
        total_equity: Current total account equity for the new baseline.
        risk_control_enabled: Whether risk control is globally enabled.
        reset_fn: Optional function to reset daily baseline. If None, uses
            the default reset_daily_baseline from core.risk_control.

    Returns:
        CommandResult with success status and response message.

    References:
        - AC1: /reset_daily 正确重置每日亏损基准
        - AC2: 与 Kill-Switch / 每日亏损限制的协同行为
        - AC3: 用户反馈与文案
        - AC4: 安全性、健壮性与审计
    """
    from core.risk_control import reset_daily_baseline

    # Log command receipt (AC4)
    logging.info(
        "Telegram /reset_daily command received: chat_id=%s, message_id=%d",
        cmd.chat_id,
        cmd.message_id,
    )

    # Check if risk control is enabled (AC3 - degradation)
    if not risk_control_enabled:
        message = (
            "⚠️ *无法重置每日基准*\n\n"
            "风控系统未启用，无法执行此操作。\n"
            "请检查 `RISK_CONTROL_ENABLED` 配置。"
        )
        logging.warning(
            "Telegram /reset_daily: risk control not enabled | chat_id=%s",
            cmd.chat_id,
        )
        return CommandResult(
            success=False,
            message=message,
            state_changed=False,
            action=None,
        )

    # Check if equity is available (AC3 - degradation)
    if total_equity is None or total_equity != total_equity:  # NaN check
        message = (
            "⚠️ *无法重置每日基准*\n\n"
            "当前权益数据不可用，无法执行此操作。\n"
            "请稍后重试。"
        )
        logging.warning(
            "Telegram /reset_daily: equity unavailable | chat_id=%s | equity=%s",
            cmd.chat_id,
            total_equity,
        )
        return CommandResult(
            success=False,
            message=message,
            state_changed=False,
            action=None,
        )

    # Capture old values for response message
    old_daily_start_equity = state.daily_start_equity
    old_daily_loss_pct = state.daily_loss_pct
    old_daily_loss_triggered = state.daily_loss_triggered
    kill_switch_active = state.kill_switch_active

    # Reset daily baseline
    reason = "telegram:/reset_daily"
    if reset_fn is not None:
        new_state = reset_fn(state, total_equity, reason)
    else:
        new_state = reset_daily_baseline(
            state,
            total_equity,
            reason=reason,
        )

    # Copy state changes back to the mutable state object
    state.daily_start_equity = new_state.daily_start_equity
    state.daily_start_date = new_state.daily_start_date
    state.daily_loss_pct = new_state.daily_loss_pct
    state.daily_loss_triggered = new_state.daily_loss_triggered

    # Build response message (AC3)
    equity_display = f"${total_equity:,.2f}"
    old_equity_display = (
        f"${old_daily_start_equity:,.2f}"
        if old_daily_start_equity is not None
        else "N/A"
    )

    # Determine next step guidance based on Kill-Switch status
    if kill_switch_active:
        next_step = (
            "\n\n⚠️ *Kill\\-Switch 仍处于激活状态*\n"
            "如需恢复交易，请发送 `/resume`"
        )
    else:
        next_step = "\n\n✅ 交易功能正常运行中。"

    message = (
        "🧮 *每日亏损基准已重置*\n\n"
        f"*新起始权益:* `{equity_display}`\n"
        f"*原起始权益:* `{old_equity_display}`\n"
        f"*当前亏损:* `0\\.00%`\n"
        f"*原亏损:* `{old_daily_loss_pct:.2f}%`\n"
        f"*日亏触发标志:* `{old_daily_loss_triggered}` → `False`"
        f"{next_step}"
    )

    # Log state change (AC4)
    logging.info(
        "Telegram /reset_daily: daily baseline reset | chat_id=%s | "
        "old_equity=%s | new_equity=%.2f | old_loss_pct=%.2f%% | "
        "old_triggered=%s | kill_switch_active=%s",
        cmd.chat_id,
        old_equity_display,
        total_equity,
        old_daily_loss_pct,
        old_daily_loss_triggered,
        kill_switch_active,
    )

    return CommandResult(
        success=True,
        message=message,
        state_changed=True,
        action="DAILY_BASELINE_RESET",
    )
