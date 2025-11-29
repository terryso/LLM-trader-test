from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import json
import logging
import numpy as np
import pandas as pd


def calculate_rsi_series(close: pd.Series, period: int) -> pd.Series:
    """Return RSI series for specified period using Wilder's smoothing."""
    delta = close.astype(float).diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    alpha = 1 / period
    avg_gain = gain.ewm(alpha=alpha, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def add_indicator_columns(
    df: pd.DataFrame,
    ema_lengths: Iterable[int],
    rsi_periods: Iterable[int],
    macd_params: Iterable[int],
) -> pd.DataFrame:
    """Return copy of df with EMA, RSI, and MACD columns added."""
    ema_lengths = tuple(dict.fromkeys(ema_lengths))
    rsi_periods = tuple(dict.fromkeys(rsi_periods))
    fast, slow, signal = macd_params

    result = df.copy()
    close = result["close"]

    for span in ema_lengths:
        result[f"ema{span}"] = close.ewm(span=span, adjust=False).mean()

    for period in rsi_periods:
        result[f"rsi{period}"] = calculate_rsi_series(close, period)

    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    result["macd"] = macd_line
    result["macd_signal"] = macd_line.ewm(span=signal, adjust=False).mean()

    return result


def calculate_atr_series(df: pd.DataFrame, period: int) -> pd.Series:
    """Return Average True Range series for the provided period."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr_components = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    )
    true_range = tr_components.max(axis=1)
    alpha = 1 / period
    return true_range.ewm(alpha=alpha, adjust=False).mean()


def calculate_indicators(
    df: pd.DataFrame,
    ema_len: int,
    rsi_len: int,
    macd_fast: int,
    macd_slow: int,
    macd_signal: int,
) -> pd.Series:
    """Calculate technical indicators and return the latest row."""
    enriched = add_indicator_columns(
        df,
        ema_lengths=(ema_len,),
        rsi_periods=(rsi_len,),
        macd_params=(macd_fast, macd_slow, macd_signal),
    )
    enriched["rsi"] = enriched[f"rsi{rsi_len}"]
    return enriched.iloc[-1]


def round_series(values: Iterable[Any], precision: int) -> List[float]:
    """Round numeric iterable to the given precision, skipping NaNs."""
    rounded: List[float] = []
    for value in values:
        try:
            if pd.isna(value):
                continue
        except TypeError:
            # Non-numeric/NA sentinel types fall back to ValueError later
            pass
        try:
            rounded.append(round(float(value), precision))
        except (TypeError, ValueError):
            continue
    return rounded


def build_market_snapshot(
    symbol: str,
    coin: str,
    df_execution: pd.DataFrame,
    df_structure: pd.DataFrame,
    df_trend: pd.DataFrame,
    open_interest_values: List[float],
    funding_rates: List[float],
) -> Dict[str, Any]:
    """Assemble a rich market snapshot dictionary for prompt composition.

    This helper mirrors the bottom-half of bot.collect_prompt_market_data but
    operates purely on data frames and numeric series without performing any
    I/O or logging.
    """
    funding_latest = funding_rates[-1] if funding_rates else 0.0

    price = float(df_execution["close"].iloc[-1])

    exec_tail = df_execution.tail(10)
    struct_tail = df_structure.tail(10)
    trend_tail = df_trend.tail(10)

    open_interest_latest = open_interest_values[-1] if open_interest_values else None
    open_interest_average = float(np.mean(open_interest_values)) if open_interest_values else None

    snapshot: Dict[str, Any] = {
        "symbol": symbol,
        "coin": coin,
        "price": price,
        "execution": {
            "ema20": float(df_execution["ema20"].iloc[-1]),
            "rsi14": float(df_execution["rsi14"].iloc[-1]),
            "macd": float(df_execution["macd"].iloc[-1]),
            "macd_signal": float(df_execution["macd_signal"].iloc[-1]),
            "series": {
                "mid_prices": round_series(exec_tail["mid_price"], 3),
                "ema20": round_series(exec_tail["ema20"], 3),
                "macd": round_series(exec_tail["macd"], 3),
                "rsi14": round_series(exec_tail["rsi14"], 3),
            },
        },
        "structure": {
            "ema20": float(df_structure["ema20"].iloc[-1]),
            "ema50": float(df_structure["ema50"].iloc[-1]),
            "rsi14": float(df_structure["rsi14"].iloc[-1]),
            "macd": float(df_structure["macd"].iloc[-1]),
            "macd_signal": float(df_structure["macd_signal"].iloc[-1]),
            "swing_high": float(df_structure["swing_high"].iloc[-1]),
            "swing_low": float(df_structure["swing_low"].iloc[-1]),
            "volume_ratio": float(df_structure["volume_ratio"].iloc[-1]),
            "series": {
                "close": round_series(struct_tail["close"], 3),
                "ema20": round_series(struct_tail["ema20"], 3),
                "ema50": round_series(struct_tail["ema50"], 3),
                "rsi14": round_series(struct_tail["rsi14"], 3),
                "macd": round_series(struct_tail["macd"], 3),
                "swing_high": round_series(struct_tail["swing_high"], 3),
                "swing_low": round_series(struct_tail["swing_low"], 3),
            },
        },
        "trend": {
            "ema20": float(df_trend["ema20"].iloc[-1]),
            "ema50": float(df_trend["ema50"].iloc[-1]),
            "ema200": float(df_trend["ema200"].iloc[-1]),
            "rsi14": float(df_trend["rsi14"].iloc[-1]),
            "macd": float(df_trend["macd"].iloc[-1]),
            "macd_signal": float(df_trend["macd_signal"].iloc[-1]),
            "macd_histogram": float(df_trend["macd_histogram"].iloc[-1]),
            "atr": float(df_trend["atr"].iloc[-1]),
            "current_volume": float(df_trend["volume"].iloc[-1]),
            "average_volume": float(df_trend["volume"].mean()),
            "series": {
                "close": round_series(trend_tail["close"], 3),
                "ema20": round_series(trend_tail["ema20"], 3),
                "ema50": round_series(trend_tail["ema50"], 3),
                "macd": round_series(trend_tail["macd"], 3),
                "rsi14": round_series(trend_tail["rsi14"], 3),
            },
        },
        "funding_rate": funding_latest,
        "funding_rates": funding_rates,
        "open_interest": {
            "latest": open_interest_latest,
            "average": open_interest_average,
        },
    }

    return snapshot


def build_trading_prompt(context: Dict[str, Any]) -> str:
    """Render the full trading prompt text from a precomputed context.

    This function contains the string-assembly logic originally implemented in
    bot.format_prompt_for_deepseek, but operates purely on a context
    dictionary to avoid depending on bot module globals.
    """
    minutes_running: int = context["minutes_running"]
    now_iso: str = context["now_iso"]
    invocation_count: int = context["invocation_count"]
    interval: str = context["interval"]
    market_snapshots: Dict[str, Dict[str, Any]] = context["market_snapshots"]
    account: Dict[str, Any] = context["account"]
    positions: List[Dict[str, Any]] = context["positions"]

    total_return = float(account.get("total_return", 0.0))
    balance = float(account.get("balance", 0.0))
    total_margin = float(account.get("total_margin", 0.0))
    net_unrealized_total = float(account.get("net_unrealized_total", 0.0))
    total_equity = float(account.get("total_equity", 0.0))

    def fmt(value: Any, digits: int = 3) -> str:
        if value is None:
            return "N/A"
        try:
            if pd.isna(value):
                return "N/A"
        except TypeError:
            pass
        try:
            return f"{float(value):.{digits}f}"
        except (TypeError, ValueError):
            return "N/A"

    def fmt_rate(value: Any) -> str:
        if value is None:
            return "N/A"
        try:
            if pd.isna(value):
                return "N/A"
        except TypeError:
            pass
        try:
            return f"{float(value):.6g}"
        except (TypeError, ValueError):
            return "N/A"

    prompt_lines: List[str] = []
    prompt_lines.append(
        f"It has been {minutes_running} minutes since you started trading. "
        f"The current time is {now_iso} and you've been invoked {invocation_count} times. "
        "Below, we are providing you with a variety of state data, price data, and predictive signals so you can discover alpha. "
        "Below that is your current account information, value, performance, positions, etc."
    )
    prompt_lines.append("ALL PRICE OR SIGNAL SERIES BELOW ARE ORDERED OLDEST → NEWEST.")
    prompt_lines.append(
        f"Timeframe note: Execution uses {interval} candles, Structure uses 1h candles, Trend uses 4h candles."
    )
    prompt_lines.append("-" * 80)
    prompt_lines.append("CURRENT MARKET STATE FOR ALL COINS (Multi-Timeframe Analysis)")

    for coin, data in market_snapshots.items():
        execution = data["execution"]
        structure = data["structure"]
        trend = data["trend"]
        open_interest = data["open_interest"]
        funding_rates = data.get("funding_rates", [])
        funding_avg_str = (
            fmt_rate(float(np.mean(funding_rates))) if funding_rates else "N/A"
        )

        prompt_lines.append(f"\n{coin} MARKET SNAPSHOT")
        prompt_lines.append(f"Current Price: {fmt(data['price'], 3)}")
        prompt_lines.append(
            f"Open Interest (latest/avg): {fmt(open_interest.get('latest'), 2)} / {fmt(open_interest.get('average'), 2)}"
        )
        prompt_lines.append(
            f"Funding Rate (latest/avg): {fmt_rate(data['funding_rate'])} / {funding_avg_str}"
        )

        prompt_lines.append("\n  4H TREND TIMEFRAME:")
        prompt_lines.append(
            "    EMA Alignment: "
            f"EMA20={fmt(trend['ema20'], 3)}, "
            f"EMA50={fmt(trend['ema50'], 3)}, "
            f"EMA200={fmt(trend['ema200'], 3)}"
        )
        ema_trend = (
            "BULLISH"
            if trend["ema20"] > trend["ema50"]
            else "BEARISH"
            if trend["ema20"] < trend["ema50"]
            else "NEUTRAL"
        )
        prompt_lines.append(f"    Trend Classification: {ema_trend}")
        prompt_lines.append(
            f"    MACD: {fmt(trend['macd'], 3)}, "
            f"Signal: {fmt(trend['macd_signal'], 3)}, "
            f"Histogram: {fmt(trend['macd_histogram'], 3)}"
        )
        prompt_lines.append(f"    RSI14: {fmt(trend['rsi14'], 2)}")
        prompt_lines.append(f"    ATR (for stop placement): {fmt(trend['atr'], 3)}")
        prompt_lines.append(
            f"    Volume: Current {fmt(trend['current_volume'], 2)}, "
            f"Average {fmt(trend['average_volume'], 2)}"
        )
        prompt_lines.append(
            f"    4H Series (last 10): Close={json.dumps(trend['series']['close'])}"
        )
        prompt_lines.append(
            "                         "
            f"EMA20={json.dumps(trend['series']['ema20'])}, "
            f"EMA50={json.dumps(trend['series']['ema50'])}"
        )
        prompt_lines.append(
            "                         "
            f"MACD={json.dumps(trend['series']['macd'])}, "
            f"RSI14={json.dumps(trend['series']['rsi14'])}"
        )

        prompt_lines.append("\n  1H STRUCTURE TIMEFRAME:")
        prompt_lines.append(
            f"    EMA20: {fmt(structure['ema20'], 3)}, EMA50: {fmt(structure['ema50'], 3)}"
        )
        struct_position = (
            "above" if data["price"] > structure["ema20"] else "below"
        )
        prompt_lines.append(f"    Price relative to 1H EMA20: {struct_position}")
        prompt_lines.append(
            f"    Swing High: {fmt(structure['swing_high'], 3)}, "
            f"Swing Low: {fmt(structure['swing_low'], 3)}"
        )
        prompt_lines.append(f"    RSI14: {fmt(structure['rsi14'], 2)}")
        prompt_lines.append(
            f"    MACD: {fmt(structure['macd'], 3)}, "
            f"Signal: {fmt(structure['macd_signal'], 3)}"
        )
        prompt_lines.append(
            f"    Volume Ratio: {fmt(structure['volume_ratio'], 2)}x (>1.5 = volume spike)"
        )
        prompt_lines.append(
            f"    1H Series (last 10): Close={json.dumps(structure['series']['close'])}"
        )
        prompt_lines.append(
            "                         "
            f"EMA20={json.dumps(structure['series']['ema20'])}, "
            f"EMA50={json.dumps(structure['series']['ema50'])}"
        )
        prompt_lines.append(
            "                         "
            f"Swing High={json.dumps(structure['series']['swing_high'])}, "
            f"Swing Low={json.dumps(structure['series']['swing_low'])}"
        )
        prompt_lines.append(
            "                         "
            f"RSI14={json.dumps(structure['series']['rsi14'])}"
        )

        prompt_lines.append(f"\n  {interval.upper()} EXECUTION TIMEFRAME:")
        prompt_lines.append(
            "    EMA20: "
            f"{fmt(execution['ema20'], 3)} "
            f"(Price {'above' if data['price'] > execution['ema20'] else 'below'} EMA20)"
        )
        prompt_lines.append(
            f"    MACD: {fmt(execution['macd'], 3)}, "
            f"Signal: {fmt(execution['macd_signal'], 3)}"
        )
        if execution["macd"] > execution["macd_signal"]:
            macd_direction = "bullish"
        elif execution["macd"] < execution["macd_signal"]:
            macd_direction = "bearish"
        else:
            macd_direction = "neutral"
        prompt_lines.append(f"    MACD Crossover: {macd_direction}")
        prompt_lines.append(f"    RSI14: {fmt(execution['rsi14'], 2)}")
        rsi_zone = (
            "oversold (<35)"
            if execution["rsi14"] < 35
            else "overbought (>65)"
            if execution["rsi14"] > 65
            else "neutral"
        )
        prompt_lines.append(f"    RSI Zone: {rsi_zone}")
        prompt_lines.append(
            f"    {interval.upper()} Series (last 10): Mid-Price={json.dumps(execution['series']['mid_prices'])}"
        )
        prompt_lines.append(
            f"                          EMA20={json.dumps(execution['series']['ema20'])}"
        )
        prompt_lines.append(
            f"                          MACD={json.dumps(execution['series']['macd'])}"
        )
        prompt_lines.append(
            f"                          RSI14={json.dumps(execution['series']['rsi14'])}"
        )

        prompt_lines.append("\n  MARKET SENTIMENT:")
        prompt_lines.append(
            "    Open Interest: "
            f"Latest={fmt(open_interest.get('latest'), 2)}, "
            f"Average={fmt(open_interest.get('average'), 2)}"
        )
        prompt_lines.append(
            "    Funding Rate: "
            f"Latest={fmt_rate(data['funding_rate'])}, "
            f"Average={funding_avg_str}"
        )
        prompt_lines.append("-" * 80)

    prompt_lines.append("ACCOUNT INFORMATION AND PERFORMANCE")
    prompt_lines.append(f"- Total Return (%): {fmt(total_return, 2)}")
    prompt_lines.append(f"- Available Cash: {fmt(balance, 2)}")
    prompt_lines.append(f"- Margin Allocated: {fmt(total_margin, 2)}")
    prompt_lines.append(f"- Unrealized PnL: {fmt(net_unrealized_total, 2)}")
    prompt_lines.append(f"- Current Account Value: {fmt(total_equity, 2)}")
    prompt_lines.append("Open positions and performance details:")

    for payload in positions:
        symbol = payload["symbol"]
        prompt_lines.append(f"{symbol} position data: {json.dumps(payload)}")

    sharpe_ratio = 0.0
    prompt_lines.append(f"Sharpe Ratio: {fmt(sharpe_ratio, 3)}")

    prompt_lines.append(
        """
INSTRUCTIONS:
For each coin, provide a trading decision in JSON format. You can either:
1. "hold" - Keep current position (if you have one)
2. "entry" - Open a new position (if you don't have one)
3. "close" - Close current position

Return ONLY a valid JSON object with this structure:
{
  "ETH": {
    "signal": "hold|entry|close",
    "side": "long|short",  // only for entry
    "quantity": 0.0,
    "profit_target": 0.0,
    "stop_loss": 0.0,
    "leverage": 10,
    "confidence": 0.75,
    "risk_usd": 500.0,
    "invalidation_condition": "If price closes below X on a 15-minute candle",
    "justification": "Reason for entry/close/hold"
  }
}

IMPORTANT:
- Only suggest entries if you see strong opportunities
- Use proper risk management
- Provide clear invalidation conditions
- Return ONLY valid JSON, no other text
""".strip()
    )

    return "\n".join(prompt_lines)


def build_entry_signal_message(
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
) -> str:
    """Render the rich Telegram ENTRY signal message body.

    This helper mirrors the formatting originally implemented inline in
    bot.execute_entry but operates purely on simple scalar parameters.
    """
    confidence_pct = confidence * 100
    side_emoji = "🟢" if side.lower() == "long" else "🔴"

    signal_text = (
        f"{side_emoji} *ENTRY SIGNAL* {side_emoji}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"*Asset:* `{coin}`\n"
        f"*Direction:* {side.upper()} {leverage_display}\n"
        f"*Entry Price:* `${entry_price:.4f}`\n"
        f"\n"
        f"📊 *Position Details*\n"
        f"• Size: `{quantity:.4f} {coin}`\n"
        f"• Margin: `${margin_required:.2f}`\n"
        f"• Risk: `${risk_usd:.2f}`\n"
        f"\n"
        f"🎯 *Targets & Stops*\n"
        f"• Target: `${profit_target_price:.4f}` ({'+' if gross_at_target >= 0 else ''}`${gross_at_target:.2f}`)\n"
        f"• Stop Loss: `${stop_loss_price:.4f}` (`${gross_at_stop:.2f}`)\n"
        f"• R/R Ratio: `{rr_display}`\n"
        f"\n"
        f"⚙️ *Execution*\n"
        f"• Liquidity: `{liquidity}`\n"
        f"• Confidence: `{confidence_pct:.0f}%`\n"
        f"• Entry Fee: `${entry_fee:.2f}`\n"
        f"\n"
        f"💭 *Reasoning*\n"
        f"_{reason_text_for_signal}_\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {timestamp}"
    )
    return signal_text


def build_close_signal_message(
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
) -> str:
    """Render the rich Telegram CLOSE signal message body.

    Mirrors the formatting originally implemented inline in
    bot.execute_close.
    """
    if net_pnl > 0:
        result_emoji = "✅"
        result_label = "PROFIT"
    elif net_pnl < 0:
        result_emoji = "❌"
        result_label = "LOSS"
    else:
        result_emoji = "➖"
        result_label = "BREAKEVEN"

    price_change_pct = ((current_price - entry_price) / entry_price) * 100
    price_change_sign = "+" if price_change_pct >= 0 else ""

    roi_pct = (net_pnl / margin) * 100 if margin > 0 else 0
    roi_sign = "+" if roi_pct >= 0 else ""

    close_signal = (
        f"{result_emoji} *CLOSE SIGNAL - {result_label}* {result_emoji}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"*Asset:* `{coin}`\n"
        f"*Direction:* {side.upper()}\n"
        f"*Size:* `{quantity:.4f} {coin}`\n"
        f"\n"
        f"💰 *P&L Summary*\n"
        f"• Entry: `${entry_price:.4f}`\n"
        f"• Exit: `${current_price:.4f}` ({price_change_sign}{price_change_pct:.2f}%)\n"
        f"• Gross P&L: `${pnl:.2f}`\n"
        f"• Fees Paid: `${total_fees:.2f}`\n"
        f"• *Net P&L:* `${net_pnl:.2f}`\n"
        f"• ROI: `{roi_sign}{roi_pct:.1f}%`\n"
        f"\n"
        f"📈 *Updated Balance*\n"
        f"• New Balance: `${balance:.2f}`\n"
        f"\n"
        f"💭 *Exit Reasoning*\n"
        f"_{reason_text_for_signal}_\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {timestamp}"
    )
    return close_signal


def recover_partial_decisions(
    json_str: str,
    coins: Iterable[str],
) -> Optional[Tuple[Dict[str, Any], List[str]]]:
    """Attempt to salvage individual coin decisions from truncated JSON.

    This helper mirrors bot._recover_partial_decisions but is parameterized by
    the list of coins, so it does not depend on bot module globals.
    """
    coin_list = list(coins)
    recovered: Dict[str, Any] = {}
    missing: List[str] = []

    for coin in coin_list:
        marker = f'"{coin}"'
        marker_idx = json_str.find(marker)
        if marker_idx == -1:
            missing.append(coin)
            continue

        obj_start = json_str.find("{", marker_idx)
        if obj_start == -1:
            missing.append(coin)
            continue

        depth = 0
        in_string = False
        escaped = False
        end_idx: Optional[int] = None

        for idx in range(obj_start, len(json_str)):
            char = json_str[idx]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end_idx = idx
                    break

        if end_idx is None:
            missing.append(coin)
            continue

        block = json_str[obj_start : end_idx + 1]
        try:
            recovered[coin] = json.loads(block)
        except json.JSONDecodeError:
            missing.append(coin)

    if not recovered:
        return None

    missing = list(dict.fromkeys(missing))

    fallback_message = "Missing data from truncated AI response; defaulting to hold."
    for coin in coin_list:
        if coin not in recovered:
            recovered[coin] = {
                "signal": "hold",
                "justification": fallback_message,
                "confidence": 0.0,
            }

    return recovered, missing


def parse_llm_json_decisions(
    content: str,
    *,
    response_id: Optional[str],
    status_code: int,
    finish_reason: Optional[str],
    notify_error: Callable[..., Any],
    log_llm_decisions: Callable[[Dict[str, Any]], None],
    recover_partial_decisions: Callable[[str], Optional[Tuple[Dict[str, Any], List[str]]]],
) -> Optional[Dict[str, Any]]:
    """Extract and decode LLM JSON decisions with partial recovery.

    This function encapsulates the JSON extraction, decoding, partial
    recovery, and error notification logic previously implemented directly in
    bot.call_deepseek_api.
    """
    start = content.find("{")
    end = content.rfind("}") + 1
    if start != -1 and end > start:
        json_str = content[start:end]
        try:
            decisions = json.loads(json_str)
            log_llm_decisions(decisions)
            return decisions
        except json.JSONDecodeError as decode_err:
            recovery = recover_partial_decisions(json_str)
            if recovery:
                decisions, missing_coins = recovery
                if missing_coins:
                    notification_message = (
                        "LLM response truncated; defaulted to hold for missing coins"
                    )
                else:
                    notification_message = (
                        "LLM response malformed; recovered all coin decisions"
                    )
                logging.warning(
                    "Recovered LLM response after JSON error (missing coins: %s)",
                    ", ".join(missing_coins) or "none",
                )
                notify_error(
                    notification_message,
                    metadata={
                        "response_id": response_id,
                        "status_code": status_code,
                        "missing_coins": missing_coins,
                        "finish_reason": finish_reason,
                        "raw_json_excerpt": json_str[:2000],
                        "decode_error": str(decode_err),
                    },
                    log_error=False,
                )
                log_llm_decisions(decisions)
                return decisions

            snippet = json_str[:2000]
            notify_error(
                f"LLM JSON decode failed: {decode_err}",
                metadata={
                    "response_id": response_id,
                    "status_code": status_code,
                    "finish_reason": finish_reason,
                    "raw_json_excerpt": snippet,
                },
            )
            return None

    notify_error(
        "No JSON found in LLM response",
        metadata={
            "response_id": response_id,
            "status_code": status_code,
            "finish_reason": finish_reason,
        },
    )
    return None
