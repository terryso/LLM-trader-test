"""
Telegram command receiving and parsing functionality.

This module is a compatibility layer that re-exports all public APIs from
the notifications.commands package. The actual implementations have been
refactored into separate modules under notifications/commands/.

This module handles receiving commands from Telegram Bot API via getUpdates
polling mechanism. It provides:
- TelegramCommand dataclass for structured command representation
- TelegramCommandHandler for polling and parsing commands
- Command handlers for various Telegram commands

This module is part of Epic 7.4: Telegram Command Integration.
"""
from __future__ import annotations

# Re-export all public APIs from the commands package for backward compatibility
from notifications.commands import (
    # Core classes
    TelegramCommand,
    TelegramCommandHandler,
    CommandResult,
    # Factory functions
    create_command_handler,
    process_telegram_commands,
    create_kill_resume_handlers,
    # Utilities
    escape_markdown,
    trim_decimal,
    COMMAND_REGISTRY,
    build_help_message,
    register_telegram_commands,
    check_admin_permission,
    # Command handlers
    handle_kill_command,
    handle_resume_command,
    handle_status_command,
    handle_balance_command,
    handle_positions_command,
    handle_risk_command,
    handle_reset_daily_command,
    handle_help_command,
    handle_unknown_command,
    handle_config_command,
    handle_config_list_command,
    handle_config_get_command,
    handle_config_set_command,
    handle_symbols_command,
    handle_symbols_list_command,
    handle_symbols_add_command,
    handle_symbols_remove_command,
    handle_audit_command,
    # Config constants
    CONFIG_KEY_DESCRIPTIONS,
    CONFIG_KEYS_FOR_TELEGRAM,
)

# Import internal functions used by tests
from notifications.commands.config import _get_config_value_info
from notifications.commands.base import log_config_audit as _log_config_audit
from notifications.commands.symbols import (
    _normalize_symbol,
    _log_symbols_audit,
)

# Alias for backward compatibility
_check_symbols_admin_permission = check_admin_permission

# Backward compatibility aliases
_escape_markdown = escape_markdown
_trim_decimal = trim_decimal
_build_help_message = build_help_message
_check_admin_permission = check_admin_permission

__all__ = [
    # Core classes
    "TelegramCommand",
    "TelegramCommandHandler",
    "CommandResult",
    # Factory functions
    "create_command_handler",
    "process_telegram_commands",
    "create_kill_resume_handlers",
    # Utilities (public)
    "escape_markdown",
    "trim_decimal",
    "COMMAND_REGISTRY",
    "build_help_message",
    "register_telegram_commands",
    "check_admin_permission",
    # Utilities (backward compatibility with underscore prefix)
    "_escape_markdown",
    "_trim_decimal",
    "_build_help_message",
    "_check_admin_permission",
    # Internal functions used by tests
    "_get_config_value_info",
    "_log_config_audit",
    "_normalize_symbol",
    "_log_symbols_audit",
    "_check_symbols_admin_permission",
    # Command handlers
    "handle_kill_command",
    "handle_resume_command",
    "handle_status_command",
    "handle_balance_command",
    "handle_positions_command",
    "handle_risk_command",
    "handle_reset_daily_command",
    "handle_help_command",
    "handle_unknown_command",
    "handle_config_command",
    "handle_config_list_command",
    "handle_config_get_command",
    "handle_config_set_command",
    "handle_symbols_command",
    "handle_symbols_list_command",
    "handle_symbols_add_command",
    "handle_symbols_remove_command",
    "handle_audit_command",
    # Config constants
    "CONFIG_KEY_DESCRIPTIONS",
    "CONFIG_KEYS_FOR_TELEGRAM",
]
