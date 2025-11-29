"""
Logging and console output functionality.

This module handles logging AI messages, console output for trades,
and error notifications.
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from colorama import Fore, Style

from notifications.telegram import strip_ansi_codes


def _emit_line(line: str, print_fn: Callable[[str], None], record_fn: Callable[[str], None]) -> None:
    print_fn(line)
    record_fn(line)


def emit_entry_console_log(
    *,
    coin: str,
    side: str,
    leverage_display: str,
    entry_price: float,
    quantity: float,
    margin_required: float,
    risk_usd: float,
    liquidity: str,
    target_price: float,
    stop_price: float,
    gross_at_target: float,
    net_at_target: float,
    gross_at_stop: float,
    net_at_stop: float,
    entry_fee: float,
    fee_rate: float,
    rr_display: str,
    confidence: float,
    raw_reason: str,
    entry_result: Optional[Any],
    print_fn: Callable[[str], None],
    record_fn: Callable[[str], None],
) -> None:
    """Emit the ENTRY console/log lines for a newly opened position.

    This helper mirrors the formatting previously implemented inline in
    bot.execute_entry but delegates printing and iteration recording to the
    provided callables.
    """
    line = f"{Fore.GREEN}[ENTRY] {coin} {side.upper()} {leverage_display} @ ${entry_price:.4f}"
    _emit_line(line, print_fn, record_fn)

    line = f"  ├─ Size: {quantity:.4f} {coin} | Margin: ${margin_required:.2f}"
    _emit_line(line, print_fn, record_fn)

    line = f"  ├─ Risk: ${risk_usd:.2f} | Liquidity: {liquidity}"
    _emit_line(line, print_fn, record_fn)

    line = f"  ├─ Target: ${target_price:.4f} | Stop: ${stop_price:.4f}"
    _emit_line(line, print_fn, record_fn)

    reason_text = raw_reason or "No justification provided."
    reason_text = " ".join(reason_text.split())

    line = (
        f"  ├─ PnL @ Target: ${gross_at_target:+.2f} "
        f"(Net: ${net_at_target:+.2f})"
    )
    _emit_line(line, print_fn, record_fn)

    line = (
        f"  ├─ PnL @ Stop: ${gross_at_stop:+.2f} "
        f"(Net: ${net_at_stop:+.2f})"
    )
    _emit_line(line, print_fn, record_fn)

    if entry_fee > 0:
        line = f"  ├─ Estimated Fee: ${entry_fee:.2f} ({liquidity} @ {fee_rate*100:.4f}%)"
        _emit_line(line, print_fn, record_fn)

    if entry_result is not None:
        if getattr(entry_result, "entry_oid", None) is not None:
            line = f"  ├─ Live Entry OID ({entry_result.backend}): {entry_result.entry_oid}"
            _emit_line(line, print_fn, record_fn)
        if getattr(entry_result, "sl_oid", None) is not None:
            line = f"  ├─ Live SL OID ({entry_result.backend}): {entry_result.sl_oid}"
            _emit_line(line, print_fn, record_fn)
        if getattr(entry_result, "tp_oid", None) is not None:
            line = f"  ├─ Live TP OID ({entry_result.backend}): {entry_result.tp_oid}"
            _emit_line(line, print_fn, record_fn)

    line = f"  ├─ Confidence: {confidence*100:.0f}%"
    _emit_line(line, print_fn, record_fn)

    line = f"  ├─ Reward/Risk: {rr_display}"
    _emit_line(line, print_fn, record_fn)

    line = f"  └─ Reason: {reason_text}"
    _emit_line(line, print_fn, record_fn)


def emit_close_console_log(
    *,
    coin: str,
    pos: Dict[str, Any],
    current_price: float,
    pnl: float,
    exit_fee: float,
    total_fees: float,
    net_pnl: float,
    reason_text: str,
    balance: float,
    close_result: Optional[Any],
    print_fn: Callable[[str], None],
    record_fn: Callable[[str], None],
) -> None:
    """Emit the CLOSE console/log lines for a closed position.

    Mirrors the formatting previously implemented inline in bot.execute_close.
    """
    color = Fore.GREEN if net_pnl >= 0 else Fore.RED
    line = f"{color}[CLOSE] {coin} {pos['side'].upper()} {pos['quantity']:.4f} @ ${current_price:.4f}"
    _emit_line(line, print_fn, record_fn)

    line = f"  ├─ Entry: ${pos['entry_price']:.4f} | Gross PnL: ${pnl:.2f}"
    _emit_line(line, print_fn, record_fn)

    if total_fees > 0:
        line = f"  ├─ Fees Paid: ${total_fees:.2f} (includes exit fee ${exit_fee:.2f})"
        _emit_line(line, print_fn, record_fn)

    if close_result is not None and getattr(close_result, "close_oid", None) is not None:
        line = f"  ├─ Live Close OID ({close_result.backend}): {close_result.close_oid}"
        _emit_line(line, print_fn, record_fn)

    line = f"  ├─ Net PnL: ${net_pnl:.2f}"
    _emit_line(line, print_fn, record_fn)

    line = f"  ├─ Reason: {reason_text}"
    _emit_line(line, print_fn, record_fn)

    line = f"  └─ Balance: ${balance:.2f}"
    _emit_line(line, print_fn, record_fn)


def record_iteration_message(messages: Optional[List[str]], text: str) -> None:
    """Record console output for this iteration to share via Telegram."""
    if messages is None:
        return
    messages.append(strip_ansi_codes(text).rstrip())


def _append_recent_ai_message(
    *,
    messages_recent_csv: Path,
    max_recent_messages: int,
    row: List[str],
) -> None:
    rows: List[List[str]] = []
    header = ["timestamp", "direction", "role", "content", "metadata"]
    if messages_recent_csv.exists():
        with open(messages_recent_csv, "r", newline="") as f:
            reader = csv.reader(f)
            try:
                existing_header = next(reader)
            except StopIteration:
                existing_header = []
            if existing_header:
                header = existing_header
            for existing_row in reader:
                rows.append(existing_row)
    rows.append(row)
    if len(rows) > max_recent_messages:
        rows = rows[-max_recent_messages:]
    with open(messages_recent_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def log_ai_message(
    *,
    messages_csv: Path,
    messages_recent_csv: Path,
    max_recent_messages: int,
    now_iso: str,
    direction: str,
    role: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Log raw messages exchanged with the AI provider."""
    row = [
        now_iso,
        direction,
        role,
        content,
        json.dumps(metadata) if metadata else "",
    ]
    with open(messages_csv, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(row)
    try:
        _append_recent_ai_message(
            messages_recent_csv=messages_recent_csv,
            max_recent_messages=max_recent_messages,
            row=row,
        )
    except Exception as exc:  # pragma: no cover - defensive logging only
        logging.debug("Failed to update recent AI messages CSV: %s", exc)


def notify_error(
    *,
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
    log_error: bool = True,
    log_ai_message_fn: Optional[Callable[[str, str, str, Optional[Dict[str, Any]]], None]] = None,
    send_telegram_message_fn: Optional[Callable[[str, Optional[str], Optional[str]], None]] = None,
) -> None:
    """Log an error and forward a brief description to Telegram."""
    if log_error:
        logging.error(message)
    if log_ai_message_fn is not None:
        log_ai_message_fn(
            "error",
            "system",
            message,
            metadata,
        )
    if send_telegram_message_fn is not None:
        send_telegram_message_fn(message, None, None)
