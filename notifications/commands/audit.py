"""
Handler for /audit command to show Backpack account balance audit.

This module wraps the functionality from scripts/backpack_balance_audit.py
and exposes it as a Telegram command.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from notifications.commands.base import TelegramCommand, CommandResult, escape_markdown


def _parse_backpack_timestamp(value: Any) -> Optional[datetime]:
    """将 Backpack 返回的时间字段解析为 UTC datetime。

    支持几种常见格式：
    - 整数或数字字符串：毫秒时间戳
    - ISO8601 字符串，带或不带 Z 后缀
    """
    if value is None:
        return None

    # 数值型：视为毫秒时间戳
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    if not isinstance(value, str):
        return None

    raw = value.strip()
    if not raw:
        return None

    # 纯数字字符串：优先按毫秒时间戳解析
    if raw.isdigit():
        try:
            ts_int = int(raw)
        except ValueError:
            return None
        # 粗略判断：大于 10^11 当作毫秒
        if ts_int > 10**11:
            ts = ts_int / 1000.0
        else:
            ts = float(ts_int)
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    # ISO8601 字符串
    iso = raw
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def _format_decimal(value: Decimal, *, places: int = 4) -> str:
    """Format a Decimal value with trailing zeros removed."""
    quantized = value.quantize(Decimal(10) ** -places)
    text = format(quantized, "f")
    text = text.rstrip("0").rstrip(".")
    return text or "0"


def _safe_decimal(value: Any) -> Optional[Decimal]:
    """Safely convert a value to Decimal."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _signed_get(
    client: Any,
    *,
    instruction: str,
    path: str,
    label: str,
    query_params: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """使用现有 Backpack 客户端签名并发起 GET 请求。"""
    params: Dict[str, Any] = {}
    if query_params:
        params.update(query_params)
    headers = client._sign(instruction, params)
    base_url = getattr(client, "_base_url", "https://api.backpack.exchange")
    timeout = getattr(client, "_timeout", 10.0)

    url = f"{base_url}{path}"
    try:
        response = client._session.get(
            url,
            headers=headers,
            params=params,
            timeout=timeout,
        )
    except Exception as exc:
        logging.warning("%s request failed: %s", label, exc)
        return []

    try:
        data = response.json()
    except ValueError:
        logging.warning(
            "%s request returned non-JSON payload. status=%s",
            label,
            response.status_code,
        )
        return []

    if response.status_code != 200:
        logging.warning("%s request HTTP %s: %s", label, response.status_code, data)
        return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        items = data.get("items") if isinstance(data.get("items"), list) else None
        if items is not None:
            return items
        return [data]

    logging.warning("%s request returned unexpected payload type: %r", label, type(data))
    return []


def _fetch_audit_data(client: Any) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch all audit data from Backpack API."""
    datasets: Dict[str, List[Dict[str, Any]]] = {}
    common_query = {"limit": 1000}

    datasets["fills"] = _signed_get(
        client,
        instruction="fillHistoryQueryAll",
        path="/wapi/v1/history/fills",
        label="fill history",
        query_params=common_query,
    )

    datasets["funding"] = _signed_get(
        client,
        instruction="fundingHistoryQueryAll",
        path="/wapi/v1/history/funding",
        label="funding history",
        query_params=common_query,
    )

    datasets["settlements"] = _signed_get(
        client,
        instruction="settlementHistoryQueryAll",
        path="/wapi/v1/history/settlement",
        label="settlement history",
        query_params=common_query,
    )

    datasets["deposits"] = _signed_get(
        client,
        instruction="depositQueryAll",
        path="/wapi/v1/capital/deposits",
        label="deposit history",
        query_params=common_query,
    )

    datasets["withdrawals"] = _signed_get(
        client,
        instruction="withdrawalQueryAll",
        path="/wapi/v1/capital/withdrawals",
        label="withdrawal history",
        query_params=common_query,
    )

    return datasets


def _analyze_audit_data(
    datasets: Dict[str, List[Dict[str, Any]]],
    *,
    start_utc: datetime,
    end_utc: datetime,
    local_tz: timezone,
) -> str:
    """Analyze audit data and return formatted message for Telegram."""
    if start_utc.tzinfo is None:
        start_utc = start_utc.replace(tzinfo=timezone.utc)
    if end_utc.tzinfo is None:
        end_utc = end_utc.replace(tzinfo=timezone.utc)

    def in_range(ts: Optional[datetime]) -> bool:
        if ts is None:
            return False
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_utc = ts.astimezone(timezone.utc)
        return start_utc <= ts_utc <= end_utc

    # 资金费汇总
    funding_total = Decimal("0")
    funding_by_symbol: Dict[str, Decimal] = {}
    for item in datasets.get("funding", []):
        ts = _parse_backpack_timestamp(item.get("intervalEndTimestamp") or item.get("timestamp"))
        if not in_range(ts):
            continue
        qty = _safe_decimal(item.get("quantity"))
        if qty is None:
            continue
        symbol = str(item.get("symbol") or "").strip() or "(unknown)"
        funding_total += qty
        funding_by_symbol[symbol] = funding_by_symbol.get(symbol, Decimal("0")) + qty

    # 结算汇总
    settlement_total = Decimal("0")
    settlement_by_source: Dict[str, Decimal] = {}
    for item in datasets.get("settlements", []):
        ts = _parse_backpack_timestamp(item.get("timestamp"))
        if not in_range(ts):
            continue
        qty = _safe_decimal(item.get("quantity"))
        if qty is None:
            continue
        source = str(item.get("source") or "").strip() or "(unknown)"
        settlement_total += qty
        settlement_by_source[source] = settlement_by_source.get(source, Decimal("0")) + qty

    # 充值汇总
    deposit_total = Decimal("0")
    for item in datasets.get("deposits", []):
        ts = _parse_backpack_timestamp(item.get("createdAt") or item.get("timestamp"))
        if not in_range(ts):
            continue
        qty = _safe_decimal(item.get("quantity"))
        if qty is None:
            continue
        deposit_total += qty

    # 提现汇总
    withdrawal_total = Decimal("0")
    for item in datasets.get("withdrawals", []):
        ts = _parse_backpack_timestamp(item.get("createdAt") or item.get("timestamp"))
        if not in_range(ts):
            continue
        qty = _safe_decimal(item.get("quantity"))
        if qty is None:
            continue
        withdrawal_total -= qty  # 提现为负

    # 净变动
    net_change = funding_total + settlement_total + deposit_total + withdrawal_total

    # 构建消息
    start_local = start_utc.astimezone(local_tz)
    end_local = end_utc.astimezone(local_tz)

    # Format time strings outside f-string to avoid backslash issues
    start_str = start_local.strftime('%Y-%m-%d %H:%M').replace('-', '\\-')
    end_str = end_local.strftime('%H:%M')
    
    lines = [
        "📊 *Backpack 资金变动分析*\n",
        f"*时间范围:* `{start_str}` \\- `{end_str}`\n",
    ]

    # 资金费
    lines.append("*\\[资金费\\]*")
    lines.append(f"  合计: `{escape_markdown(_format_decimal(funding_total))} USDC`")
    if funding_by_symbol:
        for symbol, qty in sorted(funding_by_symbol.items()):
            lines.append(f"  • {escape_markdown(symbol)}: `{escape_markdown(_format_decimal(qty))}`")
    lines.append("")

    # 结算/手续费/PnL
    lines.append("*\\[结算/手续费/PnL\\]*")
    lines.append(f"  合计: `{escape_markdown(_format_decimal(settlement_total))} USDC`")
    if settlement_by_source:
        for source, qty in sorted(settlement_by_source.items()):
            lines.append(f"  • {escape_markdown(source)}: `{escape_markdown(_format_decimal(qty))}`")
    lines.append("")

    # 充值/提现
    if deposit_total != 0 or withdrawal_total != 0:
        lines.append("*\\[充值/提现\\]*")
        if deposit_total != 0:
            lines.append(f"  充值: `{escape_markdown(_format_decimal(deposit_total))}`")
        if withdrawal_total != 0:
            lines.append(f"  提现: `{escape_markdown(_format_decimal(withdrawal_total))}`")
        lines.append("")

    # 净变动
    lines.append("*\\[综合估算\\]*")
    lines.append(f"  净变动: `{escape_markdown(_format_decimal(net_change))} USDC`")

    return "\n".join(lines)


def _parse_time_arg(value: str, local_tz: timezone) -> Optional[datetime]:
    """Parse a time argument from user input.
    
    Supports formats:
    - HH:MM (today's time)
    - YYYY-MM-DD
    - YYYY-MM-DD HH:MM
    - YYYY-MM-DDTHH:MM
    """
    text = value.strip()
    if not text:
        return None

    # Try HH:MM format (today's time)
    if len(text) <= 5 and ":" in text:
        try:
            parts = text.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            now = datetime.now(tz=local_tz)
            dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return dt.astimezone(timezone.utc)
        except (ValueError, IndexError):
            pass

    # Try ISO format
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(text.replace(" ", "T"))
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_tz)
    return dt.astimezone(timezone.utc)


def _get_default_time_range(local_tz: timezone) -> tuple[datetime, datetime]:
    """Get default time range: today 00:00 to now."""
    now_local = datetime.now(tz=local_tz)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_local.astimezone(timezone.utc), now_local.astimezone(timezone.utc)


def handle_audit_command(cmd: TelegramCommand) -> CommandResult:
    """Handle the /audit command to show Backpack balance audit.
    
    Usage:
        /audit              - 查看今天 00:00 到当前时间的资金变动
        /audit HH:MM        - 查看今天 HH:MM 到当前时间的资金变动
        /audit START END    - 查看指定时间范围的资金变动
    
    Args:
        cmd: The TelegramCommand object for /audit.
        
    Returns:
        CommandResult with success status and audit message.
    """
    logging.info(
        "Telegram /audit command received: chat_id=%s, message_id=%d, args=%s",
        cmd.chat_id,
        cmd.message_id,
        cmd.args,
    )

    # Check if Backpack is configured
    api_public_key = os.getenv("BACKPACK_API_PUBLIC_KEY", "").strip()
    api_secret_seed = os.getenv("BACKPACK_API_SECRET_SEED", "").strip()

    if not api_public_key or not api_secret_seed:
        message = (
            "❌ *Backpack API 未配置*\n\n"
            "请在 `.env` 中配置以下环境变量:\n"
            "• `BACKPACK_API_PUBLIC_KEY`\n"
            "• `BACKPACK_API_SECRET_SEED`"
        )
        return CommandResult(
            success=False,
            message=message,
            state_changed=False,
            action="AUDIT_NOT_CONFIGURED",
        )

    # Get local timezone
    local_tz = datetime.now().astimezone().tzinfo or timezone.utc

    # Parse time arguments
    if not cmd.args:
        # Default: today 00:00 to now
        start_utc, end_utc = _get_default_time_range(local_tz)
    elif len(cmd.args) == 1:
        # Single arg: start time, end = now
        start_utc = _parse_time_arg(cmd.args[0], local_tz)
        if start_utc is None:
            message = (
                f"❌ *无效的时间格式:* `{escape_markdown(cmd.args[0])}`\n\n"
                "支持的格式:\n"
                "• `HH:MM` \\- 今天的时间\n"
                "• `YYYY\\-MM\\-DD` \\- 日期\n"
                "• `YYYY\\-MM\\-DD HH:MM` \\- 日期时间"
            )
            return CommandResult(
                success=False,
                message=message,
                state_changed=False,
                action="AUDIT_INVALID_TIME",
            )
        end_utc = datetime.now(tz=timezone.utc)
    else:
        # Two args: start and end time
        start_utc = _parse_time_arg(cmd.args[0], local_tz)
        end_utc = _parse_time_arg(cmd.args[1], local_tz)
        if start_utc is None or end_utc is None:
            message = (
                "❌ *无效的时间格式*\n\n"
                "用法: `/audit [START] [END]`\n\n"
                "支持的格式:\n"
                "• `HH:MM` \\- 今天的时间\n"
                "• `YYYY\\-MM\\-DD` \\- 日期\n"
                "• `YYYY\\-MM\\-DD HH:MM` \\- 日期时间"
            )
            return CommandResult(
                success=False,
                message=message,
                state_changed=False,
                action="AUDIT_INVALID_TIME",
            )

    if end_utc <= start_utc:
        message = "❌ *结束时间必须晚于开始时间*"
        return CommandResult(
            success=False,
            message=message,
            state_changed=False,
            action="AUDIT_INVALID_RANGE",
        )

    # Create Backpack client
    try:
        from exchange.backpack import BackpackFuturesExchangeClient

        base_url = os.getenv("BACKPACK_API_BASE_URL") or "https://api.backpack.exchange"
        window_raw = os.getenv("BACKPACK_API_WINDOW_MS") or "5000"
        try:
            window_ms = int(window_raw)
        except (TypeError, ValueError):
            window_ms = 5000

        client = BackpackFuturesExchangeClient(
            api_public_key=api_public_key,
            api_secret_seed=api_secret_seed,
            base_url=base_url,
            window_ms=window_ms,
        )
    except Exception as exc:
        logging.error("Failed to create Backpack client for /audit: %s", exc)
        message = (
            "❌ *Backpack 客户端初始化失败*\n\n"
            f"错误: `{escape_markdown(str(exc))}`"
        )
        return CommandResult(
            success=False,
            message=message,
            state_changed=False,
            action="AUDIT_CLIENT_ERROR",
        )

    # Fetch and analyze data
    try:
        datasets = _fetch_audit_data(client)
        message = _analyze_audit_data(
            datasets,
            start_utc=start_utc,
            end_utc=end_utc,
            local_tz=local_tz,
        )
    except Exception as exc:
        logging.error("Failed to fetch/analyze audit data: %s", exc)
        message = (
            "❌ *获取审计数据失败*\n\n"
            f"错误: `{escape_markdown(str(exc))}`"
        )
        return CommandResult(
            success=False,
            message=message,
            state_changed=False,
            action="AUDIT_FETCH_ERROR",
        )

    logging.info(
        "Telegram /audit completed | chat_id=%s | start=%s | end=%s",
        cmd.chat_id,
        start_utc.isoformat(),
        end_utc.isoformat(),
    )

    return CommandResult(
        success=True,
        message=message,
        state_changed=False,
        action="AUDIT_COMPLETED",
    )
