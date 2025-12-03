"""
Handler for /risk command to show risk control status.
"""
from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

from notifications.commands.base import TelegramCommand, CommandResult, escape_markdown

if TYPE_CHECKING:
    from core.risk_control import RiskControlState


def handle_risk_command(
    cmd: TelegramCommand,
    state: "RiskControlState",
    *,
    total_equity: Optional[float],
    positions_count: int,
    risk_control_enabled: bool,
    daily_loss_limit_enabled: bool,
    daily_loss_limit_pct: float,
) -> CommandResult:
    """Handle the /risk command to show risk control status.
    
    This command displays the current risk control configuration and state,
    including Kill-Switch status and daily loss limit information.
    
    Args:
        cmd: The TelegramCommand object for /risk.
        state: The current RiskControlState.
        total_equity: Current total equity.
        positions_count: Number of open positions.
        risk_control_enabled: Whether risk control is enabled.
        daily_loss_limit_enabled: Whether daily loss limit is enabled.
        daily_loss_limit_pct: Daily loss limit percentage threshold.
    
    Returns:
        CommandResult with success status and response message.
    """
    logging.info(
        "Telegram /risk command received: chat_id=%s, message_id=%d",
        cmd.chat_id,
        cmd.message_id,
    )

    if not risk_control_enabled:
        message = (
            "🛡 *风控状态*\n\n"
            "⚠️ 风控系统未启用。\n"
            "请检查 `RISK_CONTROL_ENABLED` 配置。"
        )
        return CommandResult(
            success=True,
            message=message,
            state_changed=False,
            action=None,
        )

    kill_active = state.kill_switch_active
    daily_loss_pct = state.daily_loss_pct
    daily_triggered = state.daily_loss_triggered
    daily_start_equity = state.daily_start_equity

    if total_equity is None or total_equity != total_equity:
        equity_display = "N/A"
    else:
        equity_display = f"${total_equity:,.2f}"

    if daily_start_equity is None or daily_start_equity <= 0:
        start_equity_display = "N/A"
    else:
        start_equity_display = f"${daily_start_equity:,.2f}"

    kill_status = "🟢 已关闭"
    if kill_active:
        kill_status = "🔴 已激活"

    risk_flags = []
    if kill_active:
        risk_flags.append("🔴 Kill\\-Switch 已激活")
    if daily_triggered:
        risk_flags.append("⚠️ 日亏限制已触发")

    flags_line = "".join(f"\n{flag}" for flag in risk_flags) if risk_flags else ""

    loss_pct_display = f"{daily_loss_pct:.2f}%"
    limit_pct_display = f"\\-{daily_loss_limit_pct:.2f}%" if daily_loss_limit_enabled else "已关闭"

    reason = state.kill_switch_reason or "无"
    triggered_at = state.kill_switch_triggered_at or "N/A"

    message = (
        "🛡 *风控状态*\n\n"
        f"*Kill\\-Switch:* {kill_status}\n"
        f"*触发原因:* {escape_markdown(reason)}\n"
        f"*触发时间:* `{triggered_at}`\n\n"
        f"*当日亏损:* `{loss_pct_display}`\n"
        f"*亏损阈值:* `{limit_pct_display}`\n"
        f"*今日起始权益:* `{start_equity_display}`\n"
        f"*当前权益:* `{equity_display}`\n\n"
        f"*风控开关:* {'✅ 启用' if risk_control_enabled else '❌ 关闭'}\n"
        f"*每日亏损限制:* {'✅ 启用' if daily_loss_limit_enabled else '❌ 关闭'}"
        f"{flags_line}"
    )

    logging.info(
        "Telegram /risk snapshot | chat_id=%s | kill_switch_active=%s | "
        "daily_loss_pct=%.2f | daily_loss_triggered=%s | equity=%s | positions=%d",
        cmd.chat_id,
        kill_active,
        daily_loss_pct,
        daily_triggered,
        equity_display,
        positions_count,
    )

    return CommandResult(
        success=True,
        message=message,
        state_changed=False,
        action="RISK_CONTROL_STATUS",
    )
