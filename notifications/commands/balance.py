"""
Handler for /balance command to show account balance and positions.
"""
from __future__ import annotations

import logging
from typing import Optional

from notifications.commands.base import TelegramCommand, CommandResult


def handle_balance_command(
    cmd: TelegramCommand,
    *,
    balance: float,
    total_equity: Optional[float],
    total_margin: float,
    positions_count: int,
    start_capital: float,
) -> CommandResult:
    """Handle the /balance command to show account balance and positions.

    This command focuses on the current account snapshot: balance, equity,
    margin usage and open positions count.

    Notes:
        当 `TRADING_BACKEND` 为 `binance_futures` 或 `backpack_futures` 且启用实盘时，
        调用方会通过 `account_snapshot_fn` 注入实盘账户快照：
        - Binance Futures: 使用 `Client.futures_account()` 获取账户信息
        - Backpack Futures: 使用 `collateralQuery` 和 `positionQuery` API

        当实盘快照不可用（未配置实盘、API 调用失败等）时，回退到本地组合视图
        （基于 `portfolio_state.json` 的 Paper Trading 状态）。
    """
    logging.info(
        "Telegram /balance command received: chat_id=%s, message_id=%d",
        cmd.chat_id,
        cmd.message_id,
    )

    if total_equity is None or total_equity != total_equity:
        equity_display = "N/A"
        return_pct_display = "N/A"
    else:
        equity_display = f"${total_equity:,.2f}"
        if start_capital > 0:
            return_pct = ((total_equity - start_capital) / start_capital) * 100
            return_pct_display = f"{return_pct:+.2f}%"
        else:
            return_pct_display = "N/A"

    message = (
        "💰 *账户余额与持仓*\n\n"
        f"*可用余额:* `${balance:,.2f}`\n"
        f"*总权益:* `{equity_display} ({return_pct_display})`\n"
    )

    if total_margin > 0:
        message += f"*已用保证金:* `${total_margin:,.2f}`\n"

    message += f"*持仓数量:* {positions_count}"

    logging.info(
        "Telegram /balance snapshot | chat_id=%s | balance=%.2f | equity=%s | "
        "positions=%d",
        cmd.chat_id,
        balance,
        equity_display,
        positions_count,
    )

    return CommandResult(
        success=True,
        message=message,
        state_changed=False,
        action="ACCOUNT_BALANCE",
    )
