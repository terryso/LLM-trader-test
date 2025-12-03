"""
Handlers for /help and unknown commands.
"""
from __future__ import annotations

import logging

from notifications.commands.base import (
    TelegramCommand,
    CommandResult,
    build_help_message,
    escape_markdown,
)


def handle_help_command(
    cmd: TelegramCommand,
    *,
    risk_control_enabled: bool = True,
) -> CommandResult:
    """Handle the /help command to display available commands.

    This function returns a structured help message listing all available
    Telegram commands with their descriptions.

    Args:
        cmd: The TelegramCommand object for /help.
        risk_control_enabled: Whether risk control is globally enabled.

    Returns:
        CommandResult with success status and help message.

    References:
        - AC1: /help 返回完整且可扩展的命令帮助列表
    """
    # Log command receipt
    logging.info(
        "Telegram /help command received: chat_id=%s, message_id=%d",
        cmd.chat_id,
        cmd.message_id,
    )

    message = build_help_message(risk_control_enabled=risk_control_enabled)

    return CommandResult(
        success=True,
        message=message,
        state_changed=False,
        action="HELP_DISPLAYED",
    )


def handle_unknown_command(
    cmd: TelegramCommand,
    *,
    risk_control_enabled: bool = True,
) -> CommandResult:
    """Handle unknown commands by returning help information.

    This function provides a fallback for unrecognized commands, returning
    a friendly message with the available command list.

    Args:
        cmd: The TelegramCommand object for the unknown command.
        risk_control_enabled: Whether risk control is globally enabled.

    Returns:
        CommandResult with success status and unknown command message.

    References:
        - AC3: 未知命令统一回退到帮助信息
    """
    # Log unknown command
    logging.info(
        "Telegram unknown command received: /%s | chat_id=%s, message_id=%d",
        cmd.command,
        cmd.chat_id,
        cmd.message_id,
    )

    help_content = build_help_message(risk_control_enabled=risk_control_enabled)
    message = (
        f"❓ *未知命令:* `/{escape_markdown(cmd.command)}`\n\n"
        f"{help_content}"
    )

    return CommandResult(
        success=True,
        message=message,
        state_changed=False,
        action="UNKNOWN_COMMAND",
    )
