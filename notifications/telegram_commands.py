"""
Telegram command receiving and parsing functionality.

This module handles receiving commands from Telegram Bot API via getUpdates
polling mechanism. It provides:
- TelegramCommand dataclass for structured command representation
- TelegramCommandHandler for polling and parsing commands
- Command handlers for /kill and /resume commands (Story 7.4.2)

This module is part of Epic 7.4: Telegram Command Integration.
Story 7.4.1: Implement Telegram command receiving mechanism.
Story 7.4.2: Implement /kill and /resume commands.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from core.risk_control import RiskControlState


@dataclass
class TelegramCommand:
    """Structured representation of a parsed Telegram command.
    
    Attributes:
        command: Command name without leading slash (e.g., "kill", "resume", "status").
        args: List of arguments split by whitespace (e.g., ["confirm"] for "/resume confirm").
        chat_id: Chat ID where the command was sent.
        message_id: Unique message ID within the chat.
        raw_text: Original message text including the command.
        raw_update: Complete update payload from Telegram API.
    """
    command: str
    args: List[str]
    chat_id: str
    message_id: int
    raw_text: str
    raw_update: Dict[str, Any] = field(default_factory=dict)


class TelegramCommandHandler:
    """Handler for receiving and parsing Telegram commands via getUpdates API.
    
    This class manages:
    - Polling Telegram Bot API for new updates
    - Filtering commands by allowed chat ID
    - Parsing command text into structured TelegramCommand objects
    - Tracking last_update_id to avoid duplicate processing
    
    Usage:
        handler = TelegramCommandHandler(
            bot_token="your_bot_token",
            allowed_chat_id="123456789",
        )
        commands = handler.poll_commands()
        for cmd in commands:
            print(f"Received command: /{cmd.command} {cmd.args}")
    """
    
    # API timeout for getUpdates (short polling, not long polling)
    DEFAULT_TIMEOUT = 5
    # Maximum number of updates to fetch per poll
    DEFAULT_LIMIT = 10
    
    def __init__(
        self,
        bot_token: str,
        allowed_chat_id: str,
        last_update_id: int = 0,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        limit: int = DEFAULT_LIMIT,
    ) -> None:
        """Initialize the command handler.
        
        Args:
            bot_token: Telegram Bot API token.
            allowed_chat_id: Only commands from this chat ID will be returned.
            last_update_id: Initial offset for getUpdates (0 = start from oldest).
            timeout: HTTP timeout for getUpdates request in seconds.
            limit: Maximum number of updates to fetch per poll.
        """
        self._bot_token = bot_token
        self._allowed_chat_id = str(allowed_chat_id).strip()
        self._last_update_id = last_update_id
        self._timeout = timeout
        self._limit = limit
    
    @property
    def last_update_id(self) -> int:
        """Current offset for getUpdates polling."""
        return self._last_update_id
    
    def poll_commands(self) -> List[TelegramCommand]:
        """Poll Telegram API for new commands.
        
        This method:
        1. Calls getUpdates with offset = last_update_id + 1
        2. Filters updates to only message type with text starting with /
        3. Filters by allowed_chat_id (logs WARNING for unauthorized chats)
        4. Parses command text into TelegramCommand objects
        5. Updates last_update_id to prevent duplicate processing
        
        Returns:
            List of parsed TelegramCommand objects from allowed chat.
            Empty list if no new commands, API error, or Telegram not configured.
        
        Note:
            Network errors and API failures are logged but do not raise exceptions.
            This ensures the main trading loop continues even if command polling fails.
        """
        if not self._bot_token or not self._allowed_chat_id:
            logging.debug(
                "Telegram command polling skipped: not configured "
                "(bot_token=%s, allowed_chat_id=%s)",
                "set" if self._bot_token else "missing",
                "set" if self._allowed_chat_id else "missing",
            )
            return []
        
        updates = self._fetch_updates()
        if updates is None:
            return []
        
        commands: List[TelegramCommand] = []
        for update in updates:
            update_id = update.get("update_id")
            if update_id is not None:
                # Always update last_update_id to avoid reprocessing
                self._last_update_id = max(self._last_update_id, update_id)
            
            command = self._parse_update(update)
            if command is not None:
                commands.append(command)
        
        if commands:
            logging.debug(
                "Telegram commands polled: %d (last_update_id=%d)",
                len(commands),
                self._last_update_id,
            )
        
        return commands
    
    def _fetch_updates(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch updates from Telegram Bot API.
        
        Returns:
            List of update objects, or None if request failed.
        """
        url = f"https://api.telegram.org/bot{self._bot_token}/getUpdates"
        params: Dict[str, Any] = {
            "timeout": self._timeout,
            "limit": self._limit,
        }
        # Use offset = last_update_id + 1 to get only new updates
        if self._last_update_id > 0:
            params["offset"] = self._last_update_id + 1
        
        try:
            response = requests.get(url, params=params, timeout=self._timeout + 5)
            
            if response.status_code != 200:
                logging.warning(
                    "Failed to poll Telegram updates: HTTP %d | response=%s",
                    response.status_code,
                    response.text[:200] if response.text else "(empty)",
                )
                return None
            
            data = response.json()
            if not data.get("ok"):
                logging.warning(
                    "Telegram getUpdates returned ok=false: %s",
                    data.get("description", "unknown error"),
                )
                return None
            
            return data.get("result", [])
            
        except requests.exceptions.Timeout:
            logging.warning(
                "Telegram getUpdates request timed out after %ds",
                self._timeout + 5,
            )
            return None
        except requests.exceptions.RequestException as exc:
            logging.warning(
                "Telegram getUpdates request failed: %s",
                exc,
            )
            return None
        except ValueError as exc:
            # JSON decode error
            logging.warning(
                "Failed to parse Telegram getUpdates response: %s",
                exc,
            )
            return None
    
    def _parse_update(self, update: Dict[str, Any]) -> Optional[TelegramCommand]:
        """Parse a single update into a TelegramCommand.
        
        Args:
            update: Raw update object from Telegram API.
        
        Returns:
            TelegramCommand if update is a valid command from allowed chat,
            None otherwise.
        """
        update_id = update.get("update_id", "unknown")
        
        # Only process message type updates
        message = update.get("message")
        if not message:
            # Silently ignore non-message updates (callback_query, etc.)
            return None
        
        # Extract chat_id
        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))
        
        # Check if from allowed chat
        if chat_id != self._allowed_chat_id:
            logging.warning(
                "Ignoring Telegram command from unauthorized chat: chat_id=%s | "
                "allowed_chat_id=%s | update_id=%s",
                chat_id,
                self._allowed_chat_id,
                update_id,
            )
            return None
        
        # Extract message text
        text = message.get("text", "")
        if not text:
            return None
        
        # Only process commands (text starting with /)
        text = text.strip()
        if not text.startswith("/"):
            return None
        
        # Parse command and arguments
        message_id = message.get("message_id", 0)
        command, args = self._parse_command_text(text)
        
        return TelegramCommand(
            command=command,
            args=args,
            chat_id=chat_id,
            message_id=message_id,
            raw_text=text,
            raw_update=update,
        )
    
    @staticmethod
    def _parse_command_text(text: str) -> tuple[str, List[str]]:
        """Parse command text into command name and arguments.
        
        Args:
            text: Message text starting with / (e.g., "/resume confirm").
        
        Returns:
            Tuple of (command_name, args_list).
            command_name is without leading slash.
            args_list may be empty.
        
        Examples:
            "/kill" -> ("kill", [])
            "/resume confirm" -> ("resume", ["confirm"])
            "/status" -> ("status", [])
            "/reset_daily" -> ("reset_daily", [])
        """
        # Remove leading slash and split by whitespace
        parts = text[1:].split()
        if not parts:
            return ("", [])
        
        # Handle @BotName suffix in commands (e.g., "/status@MyBot")
        command = parts[0]
        if "@" in command:
            command = command.split("@")[0]
        
        args = parts[1:] if len(parts) > 1 else []
        return (command, args)


def create_command_handler(
    bot_token: str,
    chat_id: str,
    last_update_id: int = 0,
) -> Optional[TelegramCommandHandler]:
    """Factory function to create a TelegramCommandHandler if configured.
    
    Args:
        bot_token: Telegram Bot API token.
        chat_id: Allowed chat ID for command filtering.
        last_update_id: Initial offset for getUpdates.
    
    Returns:
        TelegramCommandHandler instance if both bot_token and chat_id are set,
        None otherwise.
    """
    if not bot_token or not chat_id:
        return None
    return TelegramCommandHandler(
        bot_token=bot_token,
        allowed_chat_id=chat_id,
        last_update_id=last_update_id,
    )


def process_telegram_commands(
    commands: List[TelegramCommand],
    *,
    command_handlers: Optional[Dict[str, Callable[[TelegramCommand], None]]] = None,
) -> None:
    """Process a list of Telegram commands.
    
    This is a neutral dispatch entry point for command processing.
    In Story 7.4.1, this function only logs received commands.
    Stories 7.4.2-7.4.5 will implement actual command handlers.
    
    Args:
        commands: List of TelegramCommand objects to process.
        command_handlers: Optional dict mapping command names to handler functions.
            If not provided, commands are only logged.
    """
    if not commands:
        return
    
    for cmd in commands:
        if command_handlers and cmd.command in command_handlers:
            try:
                command_handlers[cmd.command](cmd)
            except Exception as exc:
                logging.error(
                    "Error processing Telegram command /%s: %s",
                    cmd.command,
                    exc,
                )
        else:
            # Log unhandled commands at DEBUG level
            # Stories 7.4.2-7.4.5 will add actual handlers
            logging.debug(
                "Telegram command received (no handler): /%s %s | chat_id=%s",
                cmd.command,
                " ".join(cmd.args) if cmd.args else "",
                cmd.chat_id,
            )


# ═══════════════════════════════════════════════════════════════════
# COMMAND RESULT DATACLASS (Story 7.4.2)
# ═══════════════════════════════════════════════════════════════════


@dataclass
class CommandResult:
    """Result of processing a Telegram command.
    
    Attributes:
        success: Whether the command was processed successfully.
        message: Response message to send back to the user.
        state_changed: Whether the risk control state was modified.
        action: Action type for audit logging (e.g., "KILL_SWITCH_ACTIVATED").
    """
    success: bool
    message: str
    state_changed: bool = False
    action: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════
# KILL AND RESUME COMMAND HANDLERS (Story 7.4.2)
# ═══════════════════════════════════════════════════════════════════


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
            f"*当前原因:* {_escape_markdown(state.kill_switch_reason or 'unknown')}\n"
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
        f"*触发原因:* {_escape_markdown(reason)}\n"
        f"*触发时间:* `{state.kill_switch_triggered_at}`\n"
        f"*当前持仓:* {positions_count} 个\n\n"
        "⚠️ 新开仓信号已被阻止，现有持仓的止损/止盈仍正常执行。\n\n"
        "💡 恢复交易请使用: `/resume confirm`"
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


def handle_resume_command(
    cmd: TelegramCommand,
    state: "RiskControlState",
    *,
    deactivate_fn: Optional[Callable[["RiskControlState", str], "RiskControlState"]] = None,
    force: bool = False,
) -> CommandResult:
    """Handle the /resume command to deactivate Kill-Switch.
    
    This function implements the two-step confirmation mechanism:
    - /resume without 'confirm' returns a prompt asking for confirmation
    - /resume confirm actually deactivates Kill-Switch (if allowed)
    
    Args:
        cmd: The TelegramCommand object for /resume.
        state: The current RiskControlState to modify.
        deactivate_fn: Optional function to deactivate Kill-Switch. If None, uses
            the default deactivate_kill_switch from core.risk_control.
        force: If True, force deactivation even if daily_loss_triggered is True.
    
    Returns:
        CommandResult with success status and response message.
    
    References:
        - AC2: /resume 与 /resume confirm 的二次确认机制
        - AC3: 日志与审计
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
    
    # Check for 'confirm' argument
    has_confirm = len(cmd.args) > 0 and cmd.args[0].lower() == "confirm"
    
    if not has_confirm:
        # Return prompt for confirmation (AC2)
        message = (
            "⚠️ *确认解除 Kill\\-Switch*\n\n"
            f"*当前状态:* Kill\\-Switch 激活中\n"
            f"*激活原因:* {_escape_markdown(state.kill_switch_reason or 'unknown')}\n"
            f"*激活时间:* `{state.kill_switch_triggered_at}`\n\n"
            "🔐 解除 Kill\\-Switch 将恢复新开仓信号处理。\n\n"
            "请发送 `/resume confirm` 确认解除。"
        )
        logging.info(
            "Telegram /resume: confirmation required, state unchanged | "
            "chat_id=%s | current_reason=%s",
            cmd.chat_id,
            state.kill_switch_reason,
        )
        return CommandResult(
            success=True,
            message=message,
            state_changed=False,
            action="RESUME_PENDING_CONFIRM",
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
            "Telegram /resume confirm: blocked by daily_loss_triggered | "
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
        f"*解除原因:* Telegram 命令 /resume confirm\n\n"
        "📈 交易功能已恢复正常，新开仓信号将被正常处理。"
    )
    
    # Log state change (AC3)
    logging.info(
        "Telegram /resume confirm: Kill-Switch deactivated | chat_id=%s | "
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


def _escape_markdown(text: str) -> str:
    """Escape characters that have special meaning in Telegram MarkdownV2.
    
    Args:
        text: The text to escape.
    
    Returns:
        Escaped text safe for MarkdownV2.
    """
    if not text:
        return text
    specials = r"_*[]()~`>#+-=|{}.!\\"
    return "".join(f"\\{char}" if char in specials else char for char in text)


def create_kill_resume_handlers(
    state: "RiskControlState",
    *,
    positions_count_fn: Optional[Callable[[], int]] = None,
    send_fn: Optional[Callable[[str, str], None]] = None,
    record_event_fn: Optional[Callable[[str, str], None]] = None,
    bot_token: str = "",
    chat_id: str = "",
) -> Dict[str, Callable[[TelegramCommand], None]]:
    """Create command handlers for /kill and /resume commands.
    
    This factory function creates properly configured handlers that can be
    passed to process_telegram_commands.
    
    Args:
        state: The RiskControlState instance to modify.
        positions_count_fn: Optional function to get current positions count.
        send_fn: Optional function to send Telegram messages.
            Signature: send_fn(text, parse_mode).
        record_event_fn: Optional function to record audit events.
            Signature: record_event_fn(action, detail).
        bot_token: Telegram bot token for sending responses.
        chat_id: Telegram chat ID for sending responses.
    
    Returns:
        Dict mapping command names to handler functions.
    """
    from notifications.telegram import send_telegram_message
    
    def _send_response(text: str, target_chat_id: str) -> None:
        """Send response message to Telegram."""
        if not bot_token or not target_chat_id:
            logging.debug(
                "Telegram response not sent: missing bot_token or chat_id"
            )
            return
        
        if send_fn is not None:
            try:
                send_fn(text, "MarkdownV2")
            except Exception as e:
                logging.error("Failed to send Telegram response: %s", e)
        else:
            try:
                send_telegram_message(
                    bot_token=bot_token,
                    default_chat_id=target_chat_id,
                    text=text,
                    parse_mode="MarkdownV2",
                )
            except Exception as e:
                logging.error("Failed to send Telegram response: %s", e)
    
    def _record_event(action: str, detail: str) -> None:
        """Record audit event."""
        if record_event_fn is not None:
            try:
                record_event_fn(action, detail)
            except Exception as e:
                logging.error("Failed to record audit event: %s", e)
    
    def kill_handler(cmd: TelegramCommand) -> None:
        """Handler for /kill command."""
        positions = positions_count_fn() if positions_count_fn else 0
        result = handle_kill_command(
            cmd,
            state,
            positions_count=positions,
        )
        
        # Send response
        _send_response(result.message, cmd.chat_id)
        
        # Record audit event if state changed
        if result.state_changed and result.action:
            _record_event(
                result.action,
                f"Kill-Switch activated via Telegram /kill | chat_id={cmd.chat_id}",
            )
    
    def resume_handler(cmd: TelegramCommand) -> None:
        """Handler for /resume command."""
        result = handle_resume_command(cmd, state)
        
        # Send response
        _send_response(result.message, cmd.chat_id)
        
        # Record audit event if state changed or action taken
        if result.action:
            detail = f"Telegram /resume | chat_id={cmd.chat_id}"
            if result.action == "RESUME_PENDING_CONFIRM":
                detail = f"Resume requested, confirmation pending | chat_id={cmd.chat_id}"
            elif result.action == "RESUME_BLOCKED_DAILY_LOSS":
                detail = f"Resume blocked by daily loss limit | chat_id={cmd.chat_id}"
            elif result.action == "KILL_SWITCH_DEACTIVATED":
                detail = f"Kill-Switch deactivated via Telegram /resume confirm | chat_id={cmd.chat_id}"
            
            _record_event(result.action, detail)
    
    return {
        "kill": kill_handler,
        "resume": resume_handler,
    }
