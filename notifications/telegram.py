"""
Telegram notification functionality.

This module handles sending notifications to Telegram including
trade signals and error messages.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, Optional

import requests

from display.formatters import (
    build_entry_signal_message as _build_entry_signal_message,
    build_close_signal_message as _build_close_signal_message,
)


ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI color codes so Telegram receives plain text."""
    return ANSI_ESCAPE_RE.sub("", text)


def escape_markdown(text: str) -> str:
    """Escape characters that have special meaning in Telegram Markdown."""
    if not text:
        return text
    specials = r"_*[]()~`>#+-=|{}.!\\"
    return "".join(f"\\{char}" if char in specials else char for char in text)


def send_telegram_message(
    *,
    bot_token: str,
    default_chat_id: str,
    text: str,
    chat_id: Optional[str] = None,
    parse_mode: Optional[str] = "Markdown",
) -> None:
    """Send a notification message to Telegram if credentials are configured.

    If `chat_id` is provided it will be used; otherwise `default_chat_id` is used.
    This allows sending different message types to a dedicated signals group.
    """
    effective_chat = (chat_id or default_chat_id or "").strip()
    if not bot_token or not effective_chat:
        return

    try:
        payload: Dict[str, Any] = {
            "chat_id": effective_chat,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json=payload,
            timeout=10,
        )
        if response.status_code == 200:
            return

        response_text_lower = response.text.lower()
        logging.warning(
            "Telegram notification failed (%s): %s",
            response.status_code,
            response.text,
        )
        if (
            response.status_code == 400
            and "can't parse entities" in response_text_lower
            and parse_mode
        ):
            fallback_payload: Dict[str, Any] = {
                "chat_id": effective_chat,
                "text": strip_ansi_codes(text),
            }
            try:
                fallback_response = requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json=fallback_payload,
                    timeout=10,
                )
                if fallback_response.status_code != 200:
                    logging.warning(
                        "Telegram fallback notification failed (%s): %s",
                        fallback_response.status_code,
                        fallback_response.text,
                    )
            except Exception as fallback_exc:  # pragma: no cover - defensive logging only
                logging.error("Fallback Telegram message failed: %s", fallback_exc)
    except Exception as exc:  # pragma: no cover - defensive logging only
        logging.error("Error sending Telegram message: %s", exc)


def send_entry_signal_to_telegram(
    *,
    coin: str,
    side: str,
    leverage_display: str,
    entry_price: float,
    quantity: float,
    margin_required: float,
    risk_usd: float,
    profit_target_price: float,
    stop_loss_price: float,
    gross_at_target: float,
    gross_at_stop: float,
    rr_display: str,
    entry_fee: float,
    confidence: float,
    reason_text_for_signal: str,
    liquidity: str,
    timestamp: str,
    send_fn: Callable[[str, Optional[str], Optional[str]], None],
    signals_chat_id: Optional[str],
) -> None:
    """Build and send the rich ENTRY Telegram signal.

    This helper centralises the use of strategy_core.build_entry_signal_message and
    the low-level Telegram sender, so callers only need to provide numeric
    values and metadata.
    """
    signal_text = _build_entry_signal_message(
        coin=coin,
        side=side,
        leverage_display=leverage_display,
        entry_price=entry_price,
        quantity=quantity,
        margin_required=margin_required,
        risk_usd=risk_usd,
        profit_target_price=profit_target_price,
        stop_loss_price=stop_loss_price,
        gross_at_target=gross_at_target,
        gross_at_stop=gross_at_stop,
        rr_display=rr_display,
        entry_fee=entry_fee,
        confidence=confidence,
        reason_text_for_signal=reason_text_for_signal,
        liquidity=liquidity,
        timestamp=timestamp,
    )
    send_fn(signal_text, signals_chat_id, "Markdown")


def send_close_signal_to_telegram(
    *,
    coin: str,
    side: str,
    quantity: float,
    entry_price: float,
    current_price: float,
    pnl: float,
    total_fees: float,
    net_pnl: float,
    margin: float,
    balance: float,
    reason_text_for_signal: str,
    timestamp: str,
    send_fn: Callable[[str, Optional[str], Optional[str]], None],
    signals_chat_id: Optional[str],
) -> None:
    """Build and send the rich CLOSE Telegram signal."""
    close_text = _build_close_signal_message(
        coin=coin,
        side=side,
        quantity=quantity,
        entry_price=entry_price,
        current_price=current_price,
        pnl=pnl,
        total_fees=total_fees,
        net_pnl=net_pnl,
        margin=margin,
        balance=balance,
        reason_text_for_signal=reason_text_for_signal,
        timestamp=timestamp,
    )
    send_fn(close_text, signals_chat_id, "Markdown")
