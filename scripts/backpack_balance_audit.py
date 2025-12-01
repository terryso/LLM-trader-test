#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Backpack USDC 资金变动分析脚本。

本脚本复用项目中的 BackpackFuturesExchangeClient 签名逻辑，
通过调用 Backpack WAPI 历史接口（fills / funding / settlement / deposits / withdrawals），
在本地按时间范围统计账户 USDC 资金的变动来源，帮助排查余额变化原因。

注意：
- 仅发起只读 GET 请求，不会创建或取消任何订单；
- 需要在环境变量或 .env 文件中配置：
    BACKPACK_API_PUBLIC_KEY
    BACKPACK_API_SECRET_SEED
    （可选）BACKPACK_API_BASE_URL
    （可选）BACKPACK_API_WINDOW_MS
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

# 确保项目根目录在 sys.path 中，便于直接运行脚本时导入本地模块。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from exchange.backpack import BackpackFuturesExchangeClient  # noqa: E402


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


def _format_decimal(value: Decimal, *, places: int = 6) -> str:
    quantized = value.quantize(Decimal(10) ** -places)
    text = format(quantized, f"f")
    text = text.rstrip("0").rstrip(".")
    return text or "0"


def _safe_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _signed_get(
    client: BackpackFuturesExchangeClient,
    *,
    instruction: str,
    path: str,
    label: str,
    query_params: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """使用现有 Backpack 客户端签名并发起 GET 请求。

    - instruction: 文档中的 Instruction 名称，例如 fillHistoryQueryAll。
    - path: 相对路径，例如 /wapi/v1/history/fills。
    - label: 日志标签。
    """

    params: Dict[str, Any] = {}
    if query_params:
        params.update(query_params)
    headers = client._sign(instruction, params)  # type: ignore[attr-defined]
    base_url = getattr(client, "_base_url", "https://api.backpack.exchange")
    timeout = getattr(client, "_timeout", 10.0)

    url = f"{base_url}{path}"
    try:
        response = client._session.get(  # type: ignore[attr-defined]
            url,
            headers=headers,
            params=params,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
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
        # 某些接口可能把结果放在 data/items 字段中，这里做一个宽松兼容
        items = data.get("items") if isinstance(data.get("items"), list) else None
        if items is not None:
            return items
        return [data]

    logging.warning("%s request returned unexpected payload type: %r", label, type(data))
    return []


class BackpackBalanceAudit:
    def __init__(self, client: BackpackFuturesExchangeClient) -> None:
        self._client = client

    def fetch_all(self) -> Dict[str, List[Dict[str, Any]]]:
        """拉取需要用到的所有历史记录。"""

        datasets: Dict[str, List[Dict[str, Any]]] = {}

        common_query = {"limit": 1000}

        datasets["fills"] = _signed_get(
            self._client,
            instruction="fillHistoryQueryAll",
            path="/wapi/v1/history/fills",
            label="fill history",
            query_params=common_query,
        )

        datasets["funding"] = _signed_get(
            self._client,
            instruction="fundingHistoryQueryAll",
            path="/wapi/v1/history/funding",
            label="funding history",
            query_params=common_query,
        )

        datasets["settlements"] = _signed_get(
            self._client,
            instruction="settlementHistoryQueryAll",
            path="/wapi/v1/history/settlement",
            label="settlement history",
            query_params=common_query,
        )

        datasets["deposits"] = _signed_get(
            self._client,
            instruction="depositQueryAll",
            path="/wapi/v1/capital/deposits",
            label="deposit history",
            query_params=common_query,
        )

        # 提现历史接口的 REST 路径在文档中略有歧义，这里按约定优先尝试 GET。
        datasets["withdrawals"] = _signed_get(
            self._client,
            instruction="withdrawalQueryAll",
            path="/wapi/v1/capital/withdrawals",
            label="withdrawal history",
            query_params=common_query,
        )

        return datasets

    def analyze(
        self,
        datasets: Dict[str, List[Dict[str, Any]]],
        *,
        start_utc: datetime,
        end_utc: datetime,
        local_tz: timezone,
    ) -> None:
        """对指定时间范围内的记录做分类汇总并打印结果。"""

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

        # 结算（包括交易手续费、可能的 RealizedPnL 等）
        settlement_total = Decimal("0")
        settlement_by_source: Dict[str, Decimal] = {}
        hourly_buckets: Dict[datetime, Dict[str, Decimal]] = {}
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

            # 按本地时间的小时维度聚合 RealizePnl 与 TradingFees
            if ts is not None:
                local_ts = ts.astimezone(local_tz)
                hour_key = local_ts.replace(minute=0, second=0, microsecond=0)
                bucket = hourly_buckets.setdefault(hour_key, {})
                if source == "RealizePnl":
                    bucket["RealizePnl"] = bucket.get("RealizePnl", Decimal("0")) + qty
                elif source == "TradingFees":
                    bucket["TradingFees"] = bucket.get("TradingFees", Decimal("0")) + qty

        # 充值与提现（链上或内部划转）
        deposit_total = Decimal("0")
        deposit_by_symbol: Dict[str, Decimal] = {}
        for item in datasets.get("deposits", []):
            ts = _parse_backpack_timestamp(item.get("createdAt") or item.get("timestamp"))
            if not in_range(ts):
                continue
            qty = _safe_decimal(item.get("quantity"))
            if qty is None:
                continue
            symbol = str(item.get("symbol") or "").strip() or "(unknown)"
            deposit_total += qty
            deposit_by_symbol[symbol] = deposit_by_symbol.get(symbol, Decimal("0")) + qty

        withdrawal_total = Decimal("0")
        withdrawal_by_symbol: Dict[str, Decimal] = {}
        for item in datasets.get("withdrawals", []):
            ts = _parse_backpack_timestamp(item.get("createdAt") or item.get("timestamp"))
            if not in_range(ts):
                continue
            qty = _safe_decimal(item.get("quantity"))
            if qty is None:
                continue
            symbol = str(item.get("symbol") or "").strip() or "(unknown)"
            # 提现视为资金流出，统一记为负值
            qty_signed = -qty
            withdrawal_total += qty_signed
            withdrawal_by_symbol[symbol] = withdrawal_by_symbol.get(symbol, Decimal("0")) + qty_signed

        # 统计信息输出
        start_local = start_utc.astimezone(local_tz)
        end_local = end_utc.astimezone(local_tz)

        print("\n===== Backpack USDC 资金变动分析 =====")
        print(f"时间范围（本地）：{start_local.isoformat()} -> {end_local.isoformat()}")
        print()

        print("[资金费 Funding Payments]")
        print(f"  记录条数: {len(datasets.get('funding', []))}")
        print(f"  时间段内合计: {_format_decimal(funding_total)} USDC")
        if funding_by_symbol:
            print("  按合约维度:")
            for symbol, qty in sorted(funding_by_symbol.items()):
                print(f"    {symbol}: {_format_decimal(qty)} USDC")
        print()

        print("[结算 / 手续费 / PnL (Settlement History)]")
        print(f"  记录条数: {len(datasets.get('settlements', []))}")
        print(f"  时间段内合计: {_format_decimal(settlement_total)} USDC")
        if settlement_by_source:
            print("  按 source 维度:")
            for source, qty in sorted(settlement_by_source.items()):
                print(f"    {source}: {_format_decimal(qty)} USDC")
        print()

        print("[按小时拆分 RealizePnl + TradingFees]")
        if not hourly_buckets:
            print("  在选定时间范围内没有结算记录。")
        else:
            for hour in sorted(hourly_buckets.keys()):
                bucket = hourly_buckets[hour]
                pnl = bucket.get("RealizePnl", Decimal("0"))
                fees = bucket.get("TradingFees", Decimal("0"))
                total_hour = pnl + fees
                hour_label = hour.astimezone(local_tz).isoformat(timespec="minutes")
                print(f"  {hour_label}: 总计 {_format_decimal(total_hour)} USDC")
                print(
                    f"    RealizePnl: {_format_decimal(pnl)} USDC, "
                    f"TradingFees: {_format_decimal(fees)} USDC",
                )
        print()

        print("[充值 Deposits]")
        print(f"  记录条数: {len(datasets.get('deposits', []))}")
        print(f"  时间段内合计: {_format_decimal(deposit_total)} 单位 (按记录中的 symbol)")
        if deposit_by_symbol:
            print("  按币种维度:")
            for symbol, qty in sorted(deposit_by_symbol.items()):
                print(f"    {symbol}: {_format_decimal(qty)}")
        print()

        print("[提现 Withdrawals]")
        print(f"  记录条数: {len(datasets.get('withdrawals', []))}")
        print(f"  时间段内合计(签名后，提现为负): {_format_decimal(withdrawal_total)} 单位 (按记录中的 symbol)")
        if withdrawal_by_symbol:
            print("  按币种维度:")
            for symbol, qty in sorted(withdrawal_by_symbol.items()):
                print(f"    {symbol}: {_format_decimal(qty)}")
        print()

        # 尝试给出一个整体近似净变动
        net_change_estimate = funding_total + settlement_total + deposit_total + withdrawal_total
        print("[综合估算]")
        print("  资金费合计:           ", _format_decimal(funding_total), "USDC")
        print("  结算 / 手续费 / PnL:  ", _format_decimal(settlement_total), "USDC")
        print("  充值合计:             ", _format_decimal(deposit_total), "(按记录中的 symbol)")
        print("  提现合计(为负):       ", _format_decimal(withdrawal_total), "(按记录中的 symbol)")
        print("  以上来源合计近似净变动:", _format_decimal(net_change_estimate), "(单位依赖记录含义，通常应主要反映 USDC 维度)")
        print()

        print("说明：")
        print("- settlementHistory 中的 source=TradingFees 通常对应交易手续费；")
        print("- 其他 source 可能代表 RealizedPnL、FundingPnL 等，需要结合实际返回值解读；")
        print("- 本脚本没有在服务端按时间过滤，只拉取最近一批记录后在本地按时间筛选，")
        print("  如果你在一段时间内成交非常频繁，可能需要改大接口的默认返回条数或增加分页逻辑。")


def _parse_user_time(value: str, *, local_tz: timezone) -> datetime:
    """解析用户输入的时间字符串为 UTC datetime。

    支持示例：
    - 2025-12-01T03:00
    - 2025-12-01 03:00
    - 2025-12-01T03:00:15
    - 2025-12-01T03:00:15+08:00
    - 2025-12-01T03:00:15Z

    未带时区信息时按本地时区解释。
    """

    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    # 尝试标准 fromisoformat
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        # 简单兼容空格分隔日期时间
        try:
            dt = datetime.fromisoformat(text.replace(" ", "T"))
        except ValueError as exc:  # noqa: B904
            raise argparse.ArgumentTypeError(f"无法解析时间: {value}") from exc

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_tz)
    return dt.astimezone(timezone.utc)


def _default_time_range(local_tz: timezone) -> Tuple[datetime, datetime]:
    """默认时间范围：本地时间当天 03:00 到当前时间。

    如果当前时间早于 03:00，则退回到前一天的 03:00。
    返回值为 UTC 时区的 datetime。
    """

    now_local = datetime.now(tz=local_tz)
    start_local = now_local.replace(hour=3, minute=0, second=0, microsecond=0)
    if now_local < start_local:
        start_local = start_local - timedelta(days=1)

    return start_local.astimezone(timezone.utc), now_local.astimezone(timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "分析 Backpack 账户在指定时间范围内 USDC 资金变动的主要来源 "
            "(资金费 / 手续费 / PnL / 充值 / 提现等)。"
        ),
    )

    parser.add_argument(
        "--start",
        help=(
            "开始时间（本地时区），例如 2025-12-01T03:00 或 2025-12-01 03:00；"
            "默认：本地时间当天 03:00（如果当前时间早于 03:00，则为前一天 03:00）。"
        ),
    )
    parser.add_argument(
        "--end",
        help=(
            "结束时间（本地时区），例如 2025-12-01T09:30；"
            "默认：当前时间。"
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level，默认：INFO",
    )
    return parser


def _make_backpack_client() -> BackpackFuturesExchangeClient:
    api_public_key = os.getenv("BACKPACK_API_PUBLIC_KEY", "").strip()
    api_secret_seed = os.getenv("BACKPACK_API_SECRET_SEED", "").strip()

    if not api_public_key or not api_secret_seed:
        raise SystemExit(
            "BACKPACK_API_PUBLIC_KEY 和 BACKPACK_API_SECRET_SEED 必须在环境变量或 .env 中配置，"
            "否则无法调用 Backpack 私有接口。",
        )

    base_url = os.getenv("BACKPACK_API_BASE_URL") or "https://api.backpack.exchange"
    window_raw = os.getenv("BACKPACK_API_WINDOW_MS") or "5000"
    try:
        window_ms = int(window_raw)
    except (TypeError, ValueError):  # noqa: B904
        logging.warning("无效的 BACKPACK_API_WINDOW_MS=%r，使用默认 5000", window_raw)
        window_ms = 5000

    logging.info(
        "初始化 BackpackFuturesExchangeClient (base_url=%s, window_ms=%s)",
        base_url,
        window_ms,
    )

    return BackpackFuturesExchangeClient(
        api_public_key=api_public_key,
        api_secret_seed=api_secret_seed,
        base_url=base_url,
        window_ms=window_ms,
    )


def main() -> None:
    load_dotenv(override=True)

    local_tz = datetime.now().astimezone().tzinfo or timezone.utc

    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    if args.start:
        start_utc = _parse_user_time(args.start, local_tz=local_tz)
    else:
        start_utc, _ = _default_time_range(local_tz)

    if args.end:
        end_utc = _parse_user_time(args.end, local_tz=local_tz)
    else:
        # 默认结束时间：当前
        end_utc = datetime.now(tz=local_tz).astimezone(timezone.utc)

    if end_utc <= start_utc:
        raise SystemExit("结束时间必须晚于开始时间。")

    try:
        client = _make_backpack_client()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        logging.exception("初始化 Backpack 客户端失败: %s", exc)
        raise SystemExit(1) from exc

    auditor = BackpackBalanceAudit(client)
    datasets = auditor.fetch_all()
    auditor.analyze(datasets, start_utc=start_utc, end_utc=end_utc, local_tz=local_tz)  # type: ignore[arg-type]


if __name__ == "__main__":  # pragma: no cover
    try:
        main()
    except KeyboardInterrupt:
        logging.error("Interrupted by user.")
        sys.exit(1)
