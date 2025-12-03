"""
Handler for /status command to show Bot profit/loss status.
"""
from __future__ import annotations

import logging
from typing import Optional

from notifications.commands.base import TelegramCommand, CommandResult


def handle_status_command(
    cmd: TelegramCommand,
    *,
    balance: float,
    total_equity: Optional[float],
    total_margin: float,
    positions_count: int,
    start_capital: float,
    sortino_ratio: Optional[float],
    kill_switch_active: bool = False,
) -> CommandResult:
    """Handle the /status command to show Bot profit/loss status.
    
    This command displays the current financial status of the bot,
    similar to the PORTFOLIO SUMMARY shown in the terminal.
    
    Args:
        cmd: The TelegramCommand object for /status.
        balance: Current available balance.
        total_equity: Current total equity.
        total_margin: Total margin allocated to positions.
        positions_count: Number of open positions.
        start_capital: Starting capital for return calculation.
        sortino_ratio: Current Sortino ratio (or None if unavailable).
        kill_switch_active: Whether Kill-Switch is active (for status indicator).
    
    Returns:
        CommandResult with success status and response message.
    """
    logging.info(
        "Telegram /status command received: chat_id=%s, message_id=%d",
        cmd.chat_id,
        cmd.message_id,
    )

    # Calculate return percentage
    if total_equity is None or total_equity != total_equity:
        equity_display = "N/A"
        return_pct_display = "N/A"
        unrealized_pnl_display = "N/A"
    else:
        equity_display = f"${total_equity:,.2f}"
        if start_capital > 0:
            return_pct = ((total_equity - start_capital) / start_capital) * 100
            return_pct_display = f"{return_pct:+.2f}%"
        else:
            return_pct_display = "N/A"
        # Unrealized PnL = Total Equity - Balance - Margin
        unrealized_pnl = total_equity - balance - total_margin
        unrealized_pnl_display = f"${unrealized_pnl:+,.2f}"

    # Sortino ratio display
    if sortino_ratio is not None:
        sortino_display = f"{sortino_ratio:+.2f}"
    else:
        sortino_display = "N/A"

    # Trading status indicator
    if kill_switch_active:
        trading_status = "🔴 已暂停"
    else:
        trading_status = "🟢 正常"

    message = (
        "📊 *Bot 状态*\n\n"
        f"*交易状态:* {trading_status}\n"
        f"*可用余额:* `${balance:,.2f}`\n"
    )
    
    if total_margin > 0:
        message += f"*已用保证金:* `${total_margin:,.2f}`\n"
    
    message += (
        f"*总权益:* `{equity_display} ({return_pct_display})`\n"
        f"*未实现盈亏:* `{unrealized_pnl_display}`\n"
        f"*Sortino Ratio:* `{sortino_display}`\n"
        f"*持仓数量:* {positions_count}"
    )

    logging.info(
        "Telegram /status snapshot | chat_id=%s | balance=%.2f | equity=%s | "
        "positions=%d | sortino=%s",
        cmd.chat_id,
        balance,
        equity_display,
        positions_count,
        sortino_display,
    )

    return CommandResult(
        success=True,
        message=message,
        state_changed=False,
        action="BOT_STATUS",
    )
