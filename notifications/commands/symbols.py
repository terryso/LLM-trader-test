"""
Handlers for /symbols command and subcommands.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from notifications.commands.base import (
    TelegramCommand,
    CommandResult,
    escape_markdown,
    check_admin_permission,
)


_SYMBOLS_AUDIT_MAX_REASON_LENGTH = 512


def _sanitize_reason(
    reason: Optional[str], max_length: int = _SYMBOLS_AUDIT_MAX_REASON_LENGTH
) -> str:
    """Sanitize reason string for logging.
    
    Replaces newlines/carriage returns with spaces and truncates if too long.
    
    Args:
        reason: Raw reason string.
        max_length: Maximum length before truncation.
        
    Returns:
        Sanitized reason string safe for single-line logging.
    """
    if not reason:
        return "unknown"
    # Replace newlines and carriage returns with spaces
    sanitized = reason.replace("\n", " ").replace("\r", " ")
    # Collapse multiple spaces
    sanitized = " ".join(sanitized.split())
    # Truncate if too long, reserving space for suffix
    if len(sanitized) > max_length:
        suffix = "... (truncated)"
        cutoff = max(0, max_length - len(suffix))
        sanitized = sanitized[:cutoff] + suffix
    return sanitized


def _log_symbols_audit(
    *,
    action: str,
    symbol: str,
    user_id: str,
    chat_id: str,
    old_universe: Optional[List[str]] = None,
    new_universe: Optional[List[str]] = None,
    success: bool,
    reason_code: Optional[str] = None,
    reason_detail: Optional[str] = None,
) -> None:
    """Write structured audit log for symbol universe changes.
    
    This function logs Universe modifications in a structured format
    for security auditing and compliance purposes (Story 9.4 AC3).
    
    Log levels:
    - INFO: Successful add/remove operations
    - WARNING: Denied modifications (non-admin, invalid symbol)
    
    Note: Internal errors should be logged separately by the caller using
    logging.error() with appropriate context.
    
    Args:
        action: Action type (ADD, REMOVE, or DENY).
        symbol: The symbol being added or removed.
        user_id: Telegram user ID of the requester.
        chat_id: Chat ID where the command was received.
        old_universe: Universe before the change (also included for DENY for context).
        new_universe: Universe after the change (None for DENY).
        success: Whether the change was successful.
        reason_code: Machine-readable reason code (e.g., "add_permission_denied").
        reason_detail: Human-readable reason detail (e.g., error message).
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Build universe summary strings
    old_summary = f"{len(old_universe)} symbols" if old_universe is not None else "N/A"
    new_summary = f"{len(new_universe)} symbols" if new_universe is not None else "N/A"
    
    # Story 9.4 AC3 & AC4: Unified audit log format with SYMBOLS_AUDIT prefix
    # - Successful add/remove: INFO level
    # - Denied modifications: WARNING level
    if success:
        logging.info(
            "SYMBOLS_AUDIT | action=%s | symbol=%s | user_id=%s | chat_id=%s | "
            "old_universe=%s | new_universe=%s | success=%s | timestamp=%s",
            action,
            symbol,
            user_id,
            chat_id,
            old_summary,
            new_summary,
            success,
            timestamp,
        )
    else:
        # Sanitize reason_detail to prevent log injection and excessive length
        sanitized_detail = _sanitize_reason(reason_detail)
        
        # DENY logs include old_universe for audit context, reason_code for machine parsing
        logging.warning(
            "SYMBOLS_AUDIT | action=%s | symbol=%s | user_id=%s | chat_id=%s | "
            "old_universe=%s | success=%s | reason_code=%s | reason=%s | timestamp=%s",
            action,
            symbol,
            user_id,
            chat_id,
            old_summary,
            success,
            reason_code or "unknown",
            sanitized_detail,
            timestamp,
        )


def _normalize_symbol(symbol: str) -> str:
    """Normalize a symbol string to uppercase without whitespace.
    
    Args:
        symbol: Raw symbol input (e.g., "btcusdt", " BTCUSDT ").
        
    Returns:
        Normalized symbol (e.g., "BTCUSDT").
    """
    return symbol.strip().upper()


def handle_symbols_list_command(cmd: TelegramCommand) -> CommandResult:
    """Handle the /symbols list subcommand to display current Universe.
    
    This function returns the current effective symbol Universe in a
    format suitable for Telegram chat display.
    
    Args:
        cmd: The TelegramCommand object for /symbols list.
        
    Returns:
        CommandResult with success status and Universe list message.
        
    References:
        - Story 9.2 AC1: /symbols list 展示当前 Universe
    """
    from config.universe import get_effective_symbol_universe
    
    logging.info(
        "Telegram /symbols list command received: chat_id=%s, message_id=%d",
        cmd.chat_id,
        cmd.message_id,
    )
    
    universe = get_effective_symbol_universe()
    
    if not universe:
        message = (
            "📋 *当前交易 Universe*\n\n"
            "⚠️ Universe 为空，系统不会开启任何新交易。\n\n"
            "💡 使用 `/symbols add SYMBOL` 添加交易对"
        )
    else:
        # Sort symbols alphabetically for stable display
        sorted_symbols = sorted(universe)
        symbol_list = "\n".join(f"• `{escape_markdown(s)}`" for s in sorted_symbols)
        count = len(sorted_symbols)
        message = (
            f"📋 *当前交易 Universe* \\({count} 个\\)\n\n"
            f"{symbol_list}\n\n"
            "💡 使用 `/symbols add` 或 `/symbols remove` 管理交易对"
        )
    
    return CommandResult(
        success=True,
        message=message,
        state_changed=False,
        action="SYMBOLS_LIST",
    )


def handle_symbols_add_command(
    cmd: TelegramCommand,
    symbol: str,
) -> CommandResult:
    """Handle the /symbols add <SYMBOL> subcommand to add a symbol to Universe.
    
    This function implements admin-only permission control and symbol
    validation before adding to the Universe.
    
    Args:
        cmd: The TelegramCommand object for /symbols add.
        symbol: The symbol to add (raw input, will be normalized).
        
    Returns:
        CommandResult with success status and result message.
        
    References:
        - Story 9.2 AC2: /symbols add 成功路径
        - Story 9.2 AC3: 非管理员 & 校验失败路径
    """
    from config.universe import get_effective_symbol_universe, set_symbol_universe
    
    logging.info(
        "Telegram /symbols add command received: chat_id=%s, message_id=%d, "
        "user_id=%s, symbol=%s",
        cmd.chat_id,
        cmd.message_id,
        cmd.user_id,
        symbol,
    )
    
    # ─────────────────────────────────────────────────────────────────
    # Permission Check: Only admin can execute /symbols add
    # ─────────────────────────────────────────────────────────────────
    is_admin, admin_user_id = check_admin_permission(cmd)
    
    if not is_admin:
        deny_reason = "admin_not_configured" if not admin_user_id else "not_admin"
        
        # Get current universe for audit context
        current_universe = get_effective_symbol_universe()
        
        # Story 9.4 AC3: Audit log for denied modifications
        _log_symbols_audit(
            action="DENY",
            symbol=_normalize_symbol(symbol),
            user_id=cmd.user_id,
            chat_id=cmd.chat_id,
            old_universe=current_universe,
            success=False,
            reason_code="add_permission_denied",
            reason_detail=deny_reason,
        )
        
        logging.warning(
            "Telegram /symbols add: permission denied | user_id=%s | "
            "admin_user_id=%s | chat_id=%s | symbol=%s",
            cmd.user_id,
            admin_user_id if admin_user_id else "(not configured)",
            cmd.chat_id,
            symbol,
        )
        
        if not admin_user_id:
            message = (
                "🔒 *无权限修改 Universe*\n\n"
                "管理员 User ID 未配置，所有修改请求已被拒绝。\n\n"
                "💡 请在 `.env` 中设置 `TELEGRAM_ADMIN_USER_ID` 后重启 Bot。\n"
                "📖 您仍可使用 `/symbols list` 查看当前 Universe。"
            )
        else:
            message = (
                "🔒 *无权限修改 Universe*\n\n"
                "您没有权限执行此操作，只能查看 Universe。\n\n"
                "📖 您可以使用 `/symbols list` 查看当前 Universe。"
            )
        
        return CommandResult(
            success=False,
            message=message,
            state_changed=False,
            action="SYMBOLS_ADD_PERMISSION_DENIED",
        )
    
    # Normalize symbol
    normalized_symbol = _normalize_symbol(symbol)
    
    if not normalized_symbol:
        message = (
            "❌ *缺少参数*\n\n"
            "用法: `/symbols add SYMBOL`\n\n"
            "💡 示例: `/symbols add BTCUSDT`"
        )
        return CommandResult(
            success=False,
            message=message,
            state_changed=False,
            action="SYMBOLS_ADD_MISSING_SYMBOL",
        )
    
    # ─────────────────────────────────────────────────────────────────
    # Symbol Validation (Story 9.3 interface)
    # ─────────────────────────────────────────────────────────────────
    from config.universe import validate_symbol_for_universe
    is_valid, error_msg = validate_symbol_for_universe(normalized_symbol)
    
    if not is_valid:
        # Get current universe for audit context
        current_universe = get_effective_symbol_universe()
        
        # Story 9.4 AC3: Audit log for invalid symbol
        _log_symbols_audit(
            action="DENY",
            symbol=normalized_symbol,
            user_id=cmd.user_id,
            chat_id=cmd.chat_id,
            old_universe=current_universe,
            success=False,
            reason_code="add_invalid_symbol",
            reason_detail=error_msg,
        )
        
        message = (
            f"❌ *无效的交易对*\n\n"
            f"*Symbol:* `{escape_markdown(normalized_symbol)}`\n"
            f"*错误:* {escape_markdown(error_msg)}\n\n"
            "💡 请检查交易对名称是否正确"
        )
        logging.warning(
            "Telegram /symbols add: invalid symbol '%s' | chat_id=%s | error=%s",
            normalized_symbol,
            cmd.chat_id,
            error_msg,
        )
        return CommandResult(
            success=False,
            message=message,
            state_changed=False,
            action="SYMBOLS_ADD_INVALID_SYMBOL",
        )
    
    # Get current Universe
    old_universe = get_effective_symbol_universe()
    
    # Check if already in Universe
    if normalized_symbol in old_universe:
        message = (
            f"ℹ️ *Symbol 已存在*\n\n"
            f"`{escape_markdown(normalized_symbol)}` 已在当前 Universe 中，无需重复添加。\n\n"
            f"*当前 Universe:* {len(old_universe)} 个交易对"
        )
        logging.info(
            "Telegram /symbols add: symbol '%s' already in universe | chat_id=%s",
            normalized_symbol,
            cmd.chat_id,
        )
        return CommandResult(
            success=True,
            message=message,
            state_changed=False,
            action="SYMBOLS_ADD_ALREADY_EXISTS",
        )
    
    # Add symbol to Universe
    new_universe = old_universe + [normalized_symbol]
    set_symbol_universe(new_universe)
    
    # Verify the change
    actual_universe = get_effective_symbol_universe()
    
    # Build response message
    message = (
        f"✅ *Symbol 已添加*\n\n"
        f"*新增:* `{escape_markdown(normalized_symbol)}`\n"
        f"*原 Universe:* {len(old_universe)} 个交易对\n"
        f"*新 Universe:* {len(actual_universe)} 个交易对\n\n"
        "📈 新交易对将在下一轮循环中生效"
    )
    
    # Audit log
    _log_symbols_audit(
        action="ADD",
        symbol=normalized_symbol,
        user_id=cmd.user_id,
        chat_id=cmd.chat_id,
        old_universe=old_universe,
        new_universe=actual_universe,
        success=True,
    )
    
    logging.info(
        "Telegram /symbols add: symbol added | chat_id=%s | symbol=%s | "
        "old_count=%d | new_count=%d",
        cmd.chat_id,
        normalized_symbol,
        len(old_universe),
        len(actual_universe),
    )
    
    return CommandResult(
        success=True,
        message=message,
        state_changed=True,
        action="SYMBOLS_ADD",
    )


def handle_symbols_remove_command(
    cmd: TelegramCommand,
    symbol: str,
) -> CommandResult:
    """Handle the /symbols remove <SYMBOL> subcommand to remove a symbol.
    
    This function implements admin-only permission control. Removing a symbol
    does NOT trigger forced position closure - existing positions will still
    be managed by SL/TP logic.
    
    Args:
        cmd: The TelegramCommand object for /symbols remove.
        symbol: The symbol to remove (raw input, will be normalized).
        
    Returns:
        CommandResult with success status and result message.
        
    References:
        - Story 9.2 AC4: /symbols remove 不触发强制平仓
    """
    from config.universe import get_effective_symbol_universe, set_symbol_universe
    
    logging.info(
        "Telegram /symbols remove command received: chat_id=%s, message_id=%d, "
        "user_id=%s, symbol=%s",
        cmd.chat_id,
        cmd.message_id,
        cmd.user_id,
        symbol,
    )
    
    # ─────────────────────────────────────────────────────────────────
    # Permission Check: Only admin can execute /symbols remove
    # ─────────────────────────────────────────────────────────────────
    is_admin, admin_user_id = check_admin_permission(cmd)
    
    if not is_admin:
        deny_reason = "admin_not_configured" if not admin_user_id else "not_admin"
        
        # Get current universe for audit context
        current_universe = get_effective_symbol_universe()
        
        # Story 9.4 AC3: Audit log for denied modifications
        _log_symbols_audit(
            action="DENY",
            symbol=_normalize_symbol(symbol),
            user_id=cmd.user_id,
            chat_id=cmd.chat_id,
            old_universe=current_universe,
            success=False,
            reason_code="remove_permission_denied",
            reason_detail=deny_reason,
        )
        
        logging.warning(
            "Telegram /symbols remove: permission denied | user_id=%s | "
            "admin_user_id=%s | chat_id=%s | symbol=%s",
            cmd.user_id,
            admin_user_id if admin_user_id else "(not configured)",
            cmd.chat_id,
            symbol,
        )
        
        if not admin_user_id:
            message = (
                "🔒 *无权限修改 Universe*\n\n"
                "管理员 User ID 未配置，所有修改请求已被拒绝。\n\n"
                "💡 请在 `.env` 中设置 `TELEGRAM_ADMIN_USER_ID` 后重启 Bot。\n"
                "📖 您仍可使用 `/symbols list` 查看当前 Universe。"
            )
        else:
            message = (
                "🔒 *无权限修改 Universe*\n\n"
                "您没有权限执行此操作，只能查看 Universe。\n\n"
                "📖 您可以使用 `/symbols list` 查看当前 Universe。"
            )
        
        return CommandResult(
            success=False,
            message=message,
            state_changed=False,
            action="SYMBOLS_REMOVE_PERMISSION_DENIED",
        )
    
    # Normalize symbol
    normalized_symbol = _normalize_symbol(symbol)
    
    if not normalized_symbol:
        message = (
            "❌ *缺少参数*\n\n"
            "用法: `/symbols remove SYMBOL`\n\n"
            "💡 示例: `/symbols remove BTCUSDT`"
        )
        return CommandResult(
            success=False,
            message=message,
            state_changed=False,
            action="SYMBOLS_REMOVE_MISSING_SYMBOL",
        )
    
    # Get current Universe
    old_universe = get_effective_symbol_universe()
    
    # Check if symbol is in Universe
    if normalized_symbol not in old_universe:
        message = (
            f"ℹ️ *Symbol 不在 Universe 中*\n\n"
            f"`{escape_markdown(normalized_symbol)}` 不在当前 Universe 中，无需移除。\n\n"
            f"*当前 Universe:* {len(old_universe)} 个交易对"
        )
        logging.info(
            "Telegram /symbols remove: symbol '%s' not in universe | chat_id=%s",
            normalized_symbol,
            cmd.chat_id,
        )
        return CommandResult(
            success=True,
            message=message,
            state_changed=False,
            action="SYMBOLS_REMOVE_NOT_FOUND",
        )
    
    # Remove symbol from Universe
    new_universe = [s for s in old_universe if s != normalized_symbol]
    set_symbol_universe(new_universe)
    
    # Verify the change
    actual_universe = get_effective_symbol_universe()
    
    # Build response message with important notice about positions
    message = (
        f"✅ *Symbol 已移除*\n\n"
        f"*移除:* `{escape_markdown(normalized_symbol)}`\n"
        f"*原 Universe:* {len(old_universe)} 个交易对\n"
        f"*新 Universe:* {len(actual_universe)} 个交易对\n\n"
        "⚠️ *重要说明:*\n"
        "• 后续不会为该 Symbol 生成新开仓信号\n"
        "• 现有持仓\\(如有\\)仍由 SL/TP 逻辑管理\n"
        "• 不会触发强制平仓"
    )
    
    # Audit log
    _log_symbols_audit(
        action="REMOVE",
        symbol=normalized_symbol,
        user_id=cmd.user_id,
        chat_id=cmd.chat_id,
        old_universe=old_universe,
        new_universe=actual_universe,
        success=True,
    )
    
    logging.info(
        "Telegram /symbols remove: symbol removed | chat_id=%s | symbol=%s | "
        "old_count=%d | new_count=%d",
        cmd.chat_id,
        normalized_symbol,
        len(old_universe),
        len(actual_universe),
    )
    
    return CommandResult(
        success=True,
        message=message,
        state_changed=True,
        action="SYMBOLS_REMOVE",
    )


def handle_symbols_command(cmd: TelegramCommand) -> CommandResult:
    """Handle the /symbols command with subcommands list/add/remove.
    
    This is the main entry point for /symbols command processing.
    It dispatches to the appropriate subcommand handler based on arguments.
    
    Args:
        cmd: The TelegramCommand object for /symbols.
        
    Returns:
        CommandResult with success status and response message.
        
    References:
        - Story 9.2: Telegram /symbols 命令接口
    """
    logging.info(
        "Telegram /symbols command received: chat_id=%s, message_id=%d, args=%s",
        cmd.chat_id,
        cmd.message_id,
        cmd.args,
    )
    
    # Parse subcommand
    if not cmd.args:
        # No subcommand - show usage help
        message = (
            "📋 */symbols 命令用法*\n\n"
            "• `/symbols list` \\- 查看当前交易 Universe\n"
            "• `/symbols add SYMBOL` \\- 添加交易对 \\(管理员\\)\n"
            "• `/symbols remove SYMBOL` \\- 移除交易对 \\(管理员\\)\n\n"
            "💡 示例:\n"
            "`/symbols list`\n"
            "`/symbols add BTCUSDT`\n"
            "`/symbols remove SOLUSDT`"
        )
        return CommandResult(
            success=True,
            message=message,
            state_changed=False,
            action="SYMBOLS_HELP",
        )
    
    subcommand = cmd.args[0].lower()
    
    if subcommand == "list":
        return handle_symbols_list_command(cmd)
    
    if subcommand == "add":
        if len(cmd.args) < 2:
            message = (
                "❌ *缺少参数*\n\n"
                "用法: `/symbols add SYMBOL`\n\n"
                "💡 示例: `/symbols add BTCUSDT`"
            )
            return CommandResult(
                success=False,
                message=message,
                state_changed=False,
                action="SYMBOLS_ADD_MISSING_SYMBOL",
            )
        symbol = cmd.args[1]
        return handle_symbols_add_command(cmd, symbol)
    
    if subcommand == "remove":
        if len(cmd.args) < 2:
            message = (
                "❌ *缺少参数*\n\n"
                "用法: `/symbols remove SYMBOL`\n\n"
                "💡 示例: `/symbols remove BTCUSDT`"
            )
            return CommandResult(
                success=False,
                message=message,
                state_changed=False,
                action="SYMBOLS_REMOVE_MISSING_SYMBOL",
            )
        symbol = cmd.args[1]
        return handle_symbols_remove_command(cmd, symbol)
    
    # Unknown subcommand
    message = (
        f"❌ *未知子命令:* `{escape_markdown(subcommand)}`\n\n"
        "可用子命令:\n"
        "• `list` \\- 查看当前交易 Universe\n"
        "• `add SYMBOL` \\- 添加交易对\n"
        "• `remove SYMBOL` \\- 移除交易对"
    )
    logging.warning(
        "Telegram /symbols: unknown subcommand '%s' | chat_id=%s",
        subcommand,
        cmd.chat_id,
    )
    return CommandResult(
        success=False,
        message=message,
        state_changed=False,
        action="SYMBOLS_UNKNOWN_SUBCOMMAND",
    )
