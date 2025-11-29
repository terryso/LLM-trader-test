"""Notifications module for LLM-trader."""
from notifications.telegram import (
    send_telegram_message,
    send_entry_signal_to_telegram,
    send_close_signal_to_telegram,
    strip_ansi_codes,
    escape_markdown,
)
from notifications.logging import (
    log_ai_message,
    record_iteration_message,
    notify_error,
    emit_entry_console_log,
    emit_close_console_log,
)

__all__ = [
    # Telegram
    "send_telegram_message",
    "send_entry_signal_to_telegram",
    "send_close_signal_to_telegram",
    "strip_ansi_codes",
    "escape_markdown",
    # Logging
    "log_ai_message",
    "record_iteration_message",
    "notify_error",
    "emit_entry_console_log",
    "emit_close_console_log",
]
