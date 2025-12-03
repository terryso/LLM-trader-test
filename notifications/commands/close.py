"""
Handler for /close command to close a specific position.

This module implements the /close command for partial or full position closing
via Telegram. It supports:
- Full close: /close SYMBOL or /close SYMBOL all
- Partial close: /close SYMBOL AMOUNT (where AMOUNT is 0-100 percentage)

Part of Epic 7.4: Telegram Command Integration (Story 7.4.6).
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from notifications.commands.base import (
    TelegramCommand,
    CommandResult,
    escape_markdown,
    trim_decimal,
)
from notifications.commands.positions import parse_live_positions


def _normalize_symbol(symbol: str) -> str:
    """Normalize symbol to uppercase without suffix.
    
    Args:
        symbol: Raw symbol input (e.g., "btc", "BTCUSDT", "BTC_USDC_PERP").
        
    Returns:
        Normalized symbol (e.g., "BTC").
    """
    if not symbol:
        return ""
    
    upper = symbol.strip().upper()
    
    # Remove common suffixes
    for suffix in ("_USDC_PERP", "_USDT_PERP", "USDT", "USDC", "USD"):
        if upper.endswith(suffix):
            upper = upper[:-len(suffix)]
            break
    
    # Handle underscore-separated formats (e.g., "BTC_USDC")
    if "_" in upper:
        upper = upper.split("_")[0]
    
    return upper


def _parse_close_args(args: List[str]) -> tuple[Optional[str], Optional[float], Optional[str]]:
    """Parse /close command arguments.
    
    Args:
        args: List of command arguments.
        
    Returns:
        Tuple of (symbol, amount_pct, error_message).
        - symbol: Normalized symbol or None if invalid.
        - amount_pct: Percentage to close (0-100) or None for full close.
        - error_message: Error message if parsing failed, None otherwise.
    """
    if not args:
        return None, None, "请指定要平仓的品种，例如: /close BTC 或 /close BTC 50"
    
    symbol = _normalize_symbol(args[0])
    if not symbol:
        return None, None, "无效的品种名称"
    
    # No second argument = full close
    if len(args) < 2:
        return symbol, None, None
    
    second_arg = args[1].strip().lower()
    
    # "all" = full close
    if second_arg == "all":
        return symbol, None, None
    
    # Try to parse as percentage
    try:
        amount_pct = float(second_arg)
    except ValueError:
        return None, None, f"无效的平仓比例 '{args[1]}'，请输入 0-100 之间的数字或 'all'"
    
    if amount_pct < 0:
        return None, None, "平仓比例不能为负数"
    
    if amount_pct == 0:
        return None, None, "平仓比例不能为 0"
    
    return symbol, amount_pct, None


def _find_position_for_symbol(
    symbol: str,
    positions: Dict[str, Dict[str, Any]],
) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Find position matching the given symbol.
    
    Args:
        symbol: Normalized symbol to find.
        positions: Dict of positions keyed by coin.
        
    Returns:
        Tuple of (matched_key, position_data) or (None, None) if not found.
    """
    if not positions:
        return None, None
    
    # Direct match
    if symbol in positions:
        return symbol, positions[symbol]
    
    # Case-insensitive match
    symbol_upper = symbol.upper()
    for key, pos in positions.items():
        if key.upper() == symbol_upper:
            return key, pos
    
    return None, None


def _calculate_close_quantity(
    position: Dict[str, Any],
    amount_pct: Optional[float],
) -> tuple[float, float, bool]:
    """Calculate the quantity to close based on percentage.
    
    Args:
        position: Position data dict.
        amount_pct: Percentage to close (0-100) or None for full close.
        
    Returns:
        Tuple of (close_quantity, remaining_quantity, is_full_close).
    """
    try:
        total_quantity = abs(float(position.get("quantity", 0) or 0))
    except (TypeError, ValueError):
        total_quantity = 0.0
    
    if total_quantity <= 0:
        return 0.0, 0.0, True
    
    # Full close if no percentage specified or >= 100%
    if amount_pct is None or amount_pct >= 100:
        return total_quantity, 0.0, True
    
    # Partial close
    close_quantity = total_quantity * (amount_pct / 100.0)
    remaining_quantity = total_quantity - close_quantity
    
    return close_quantity, remaining_quantity, False


def _calculate_notional(
    quantity: float,
    entry_price: float,
) -> float:
    """Calculate notional value.
    
    Args:
        quantity: Position quantity.
        entry_price: Entry price.
        
    Returns:
        Notional value in USD.
    """
    if quantity <= 0 or entry_price <= 0:
        return 0.0
    return abs(quantity * entry_price)


def handle_close_command(
    cmd: TelegramCommand,
    *,
    positions: Dict[str, Dict[str, Any]],
    execute_close_fn: Optional[Callable[[str, str, float], Any]] = None,
) -> CommandResult:
    """Handle the /close command for partial or full position closing.
    
    This command supports:
    - /close SYMBOL - Full close of the position
    - /close SYMBOL all - Full close of the position
    - /close SYMBOL AMOUNT - Partial close (AMOUNT is percentage 0-100)
    
    When AMOUNT >= 100, it degrades to full close with a note.
    
    Args:
        cmd: The TelegramCommand object.
        positions: Dict of current positions keyed by coin symbol.
        execute_close_fn: Optional callback to execute the close.
            Signature: execute_close_fn(coin, side, quantity) -> CloseResult or None.
            - Returns CloseResult with success=True on successful execution.
            - Returns CloseResult with success=False on exchange rejection.
            - Returns None on routing/setup failure (no symbol, no market data, etc.).
            If not provided, the command will skip execution but still return
            success=True with state_changed=True (dry-run mode for testing).
    
    Returns:
        CommandResult with success status and message.
        - success=True, state_changed=True: Close executed successfully.
        - success=True, state_changed=False: No position found (safe no-op).
        - success=False: Parse error or execution failure.
    """
    logging.info(
        "Telegram /close command received: chat_id=%s, message_id=%d, args=%s",
        cmd.chat_id,
        cmd.message_id,
        cmd.args,
    )
    
    # Parse arguments
    symbol, amount_pct, error = _parse_close_args(cmd.args)
    if error:
        logging.warning(
            "Telegram /close command parse error: %s | args=%s | chat_id=%s",
            error,
            cmd.args,
            cmd.chat_id,
        )
        message = f"❌ {error}"
        return CommandResult(
            success=False,
            message=escape_markdown(message),
            state_changed=False,
            action="CLOSE_PARSE_ERROR",
        )
    
    # Find position
    matched_key, position = _find_position_for_symbol(symbol, positions)
    if position is None:
        logging.info(
            "Telegram /close command: no position for %s | chat_id=%s",
            symbol,
            cmd.chat_id,
        )
        message = (
            f"📂 当前无 {symbol} 持仓，未执行平仓操作。\n\n"
            f"提示: 使用 /positions 查看当前持仓列表。"
        )
        return CommandResult(
            success=True,
            message=escape_markdown(message),
            state_changed=False,
            action="CLOSE_NO_POSITION",
        )
    
    # Get position details
    side = str(position.get("side", "")).lower()
    try:
        total_quantity = abs(float(position.get("quantity", 0) or 0))
    except (TypeError, ValueError):
        total_quantity = 0.0
    
    try:
        entry_price = float(position.get("entry_price", 0) or 0)
    except (TypeError, ValueError):
        entry_price = 0.0
    
    if total_quantity <= 0:
        logging.info(
            "Telegram /close command: zero quantity for %s | chat_id=%s",
            matched_key,
            cmd.chat_id,
        )
        message = f"📂 {matched_key} 持仓数量为 0，未执行平仓操作。"
        return CommandResult(
            success=True,
            message=escape_markdown(message),
            state_changed=False,
            action="CLOSE_ZERO_QUANTITY",
        )
    
    # Calculate close quantity
    close_quantity, remaining_quantity, is_full_close = _calculate_close_quantity(
        position, amount_pct
    )
    
    if close_quantity <= 0:
        logging.warning(
            "Telegram /close command: calculated close quantity is 0 for %s | chat_id=%s",
            matched_key,
            cmd.chat_id,
        )
        message = f"⚠️ 计算的平仓数量过小，无法执行平仓操作。"
        return CommandResult(
            success=False,
            message=escape_markdown(message),
            state_changed=False,
            action="CLOSE_QUANTITY_TOO_SMALL",
        )
    
    # Calculate notional values
    total_notional = _calculate_notional(total_quantity, entry_price)
    close_notional = _calculate_notional(close_quantity, entry_price)
    remaining_notional = _calculate_notional(remaining_quantity, entry_price)
    
    # Determine if this was a >= 100% request that degraded to full close
    degraded_to_full = amount_pct is not None and amount_pct >= 100
    
    # Build action description
    side_display = "多" if side == "long" else "空" if side == "short" else side.upper()
    
    # Execute close if callback provided
    if execute_close_fn is not None:
        try:
            result = execute_close_fn(matched_key, side, close_quantity)
            
            # Check if execution returned None (indicates failure in routing/setup)
            if result is None:
                logging.error(
                    "Telegram /close command execution returned None | symbol=%s | "
                    "side=%s | quantity=%s | amount_pct=%s | close_notional=%.2f | chat_id=%s",
                    matched_key,
                    side,
                    close_quantity,
                    amount_pct,
                    close_notional,
                    cmd.chat_id,
                )
                message = (
                    f"❌ {matched_key} 平仓执行失败\n\n"
                    f"错误: 无法连接交易所或获取市场数据\n\n"
                    f"请检查网络连接和交易所配置后重试。"
                )
                return CommandResult(
                    success=False,
                    message=escape_markdown(message),
                    state_changed=False,
                    action="CLOSE_EXECUTION_FAILED",
                )
            
            # Check if execution succeeded
            if hasattr(result, 'success') and not result.success:
                errors = getattr(result, 'errors', [])
                error_msg = "; ".join(errors) if errors else "未知错误"
                logging.error(
                    "Telegram /close command execution failed: %s | symbol=%s | "
                    "side=%s | quantity=%s | amount_pct=%s | close_notional=%.2f | chat_id=%s",
                    error_msg,
                    matched_key,
                    side,
                    close_quantity,
                    amount_pct,
                    close_notional,
                    cmd.chat_id,
                )
                message = (
                    f"❌ {matched_key} 平仓执行失败\n\n"
                    f"错误: {error_msg}\n\n"
                    f"请稍后重试或检查交易所状态。"
                )
                return CommandResult(
                    success=False,
                    message=escape_markdown(message),
                    state_changed=False,
                    action="CLOSE_EXECUTION_FAILED",
                )
                
        except Exception as exc:
            logging.error(
                "Telegram /close command execution error: %s | symbol=%s | "
                "side=%s | quantity=%s | amount_pct=%s | close_notional=%.2f | chat_id=%s",
                exc,
                matched_key,
                side,
                close_quantity,
                amount_pct,
                close_notional,
                cmd.chat_id,
            )
            message = (
                f"❌ {matched_key} 平仓执行出错\n\n"
                f"错误: {str(exc)}\n\n"
                f"请稍后重试或检查交易所状态。"
            )
            return CommandResult(
                success=False,
                message=escape_markdown(message),
                state_changed=False,
                action="CLOSE_EXECUTION_ERROR",
            )
    
    # Build success message
    lines: List[str] = []
    
    if is_full_close:
        if degraded_to_full:
            lines.append(f"✅ {matched_key} 全平完成")
            lines.append(f"（请求百分比 >= 100%，已执行全平）")
        else:
            lines.append(f"✅ {matched_key} 全平完成")
    else:
        pct_display = trim_decimal(amount_pct or 0, max_decimals=2)
        lines.append(f"✅ {matched_key} 部分平仓完成 ({pct_display}%)")
    
    lines.append("")
    lines.append(f"方向: {side_display}")
    lines.append(f"平仓数量: {trim_decimal(close_quantity, max_decimals=6)}")
    lines.append(f"平仓名义金额: ${close_notional:,.2f}")
    
    if not is_full_close:
        lines.append("")
        lines.append(f"剩余持仓: {trim_decimal(remaining_quantity, max_decimals=6)}")
        lines.append(f"剩余名义金额: ${remaining_notional:,.2f}")
    
    logging.info(
        "Telegram /close command success: symbol=%s | side=%s | "
        "close_qty=%s | remaining_qty=%s | is_full=%s | chat_id=%s",
        matched_key,
        side,
        close_quantity,
        remaining_quantity,
        is_full_close,
        cmd.chat_id,
    )
    
    message = "\n".join(lines)
    return CommandResult(
        success=True,
        message=escape_markdown(message),
        state_changed=True,
        action="CLOSE_EXECUTED" if is_full_close else "PARTIAL_CLOSE_EXECUTED",
    )


def get_positions_for_close(
    account_snapshot_fn: Optional[Callable[[], Optional[Dict[str, Any]]]] = None,
    positions_snapshot_fn: Optional[Callable[[], Dict[str, Dict[str, Any]]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Get positions for close command, prioritizing live exchange data.
    
    This function is similar to get_positions_from_snapshot in positions.py
    but is specifically designed for the /close command context.
    
    Args:
        account_snapshot_fn: Function to get live exchange account snapshot.
        positions_snapshot_fn: Function to get local portfolio positions.
        
    Returns:
        Dict mapping coin symbol to position data.
    """
    positions: Dict[str, Dict[str, Any]] = {}
    
    # 1) Try live exchange snapshot first
    if account_snapshot_fn is not None:
        try:
            snapshot = account_snapshot_fn()
        except Exception as exc:
            logging.warning("Failed to get live account snapshot for /close: %s", exc)
            snapshot = None
        
        if isinstance(snapshot, dict):
            raw_positions = snapshot.get("positions")
            if isinstance(raw_positions, list):
                positions = parse_live_positions(raw_positions)
    
    # 2) Fall back to local portfolio if no live data
    if not positions and positions_snapshot_fn is not None:
        try:
            local_snapshot = positions_snapshot_fn()
        except Exception as exc:
            logging.error("Error calling positions_snapshot_fn for /close: %s", exc)
            local_snapshot = None
        if isinstance(local_snapshot, dict):
            positions = local_snapshot
    
    return positions
