#!/usr/bin/env python3
"""
DeepSeek Multi-Asset Paper Trading Bot
Uses Binance API for market data and OpenRouter API for DeepSeek Chat V3.1 trading decisions
"""
from __future__ import annotations

import os
import re
import time
import json
import logging
import csv
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import ccxt
from requests.exceptions import RequestException, Timeout
from binance.client import Client
from dotenv import load_dotenv
from colorama import Fore, Style, init as colorama_init

from hyperliquid_client import HyperliquidTradingClient
from exchange_client import CloseResult, EntryResult, get_exchange_client
from notifications import (
    emit_close_console_log,
    emit_entry_console_log,
    send_close_signal_to_telegram,
    send_entry_signal_to_telegram,
    log_ai_message as _notifications_log_ai_message,
    record_iteration_message as _notifications_record_iteration_message,
    send_telegram_message as _notifications_send_telegram_message,
    notify_error as _notifications_notify_error,
)
from metrics import (
    calculate_sortino_ratio as _metrics_calculate_sortino_ratio,
    calculate_pnl_for_price as _metrics_calculate_pnl_for_price,
    calculate_unrealized_pnl_for_position as _metrics_unrealized_pnl_for_pos,
    calculate_net_unrealized_pnl_for_position as _metrics_net_unrealized_pnl_for_pos,
    estimate_exit_fee_for_position as _metrics_estimate_exit_fee_for_pos,
    calculate_total_margin_for_positions as _metrics_total_margin_for_positions,
    format_leverage_display as _metrics_format_leverage_display,
)
from market_data import BinanceMarketDataClient, BackpackMarketDataClient
from execution_routing import (
    check_stop_loss_take_profit_for_positions as _check_sltp_for_positions,
    compute_entry_plan as _compute_entry_plan,
    compute_close_plan as _compute_close_plan,
    route_live_entry as _route_live_entry,
    route_live_close as _route_live_close,
)
from strategy_core import (
    calculate_rsi_series as _strategy_calculate_rsi_series,
    add_indicator_columns as _strategy_add_indicator_columns,
    calculate_atr_series as _strategy_calculate_atr_series,
    calculate_indicators as _strategy_calculate_indicators,
    round_series as _strategy_round_series,
    build_market_snapshot as _strategy_build_market_snapshot,
    build_trading_prompt as _strategy_build_trading_prompt,
    recover_partial_decisions as _strategy_recover_partial_decisions,
    parse_llm_json_decisions as _strategy_parse_llm_json_decisions,
    build_entry_signal_message as _strategy_build_entry_signal_message,
    build_close_signal_message as _strategy_build_close_signal_message,
)
from state_io import (
    load_equity_history_from_csv as _load_equity_history_from_csv,
    init_csv_files_for_paths as _init_csv_files_for_paths,
    save_state_to_json as _save_state_to_json,
    load_state_from_json as _load_state_from_json,
    append_portfolio_state_row as _append_portfolio_state_row,
    append_trade_row as _append_trade_row,
)
from bot_config import (
    EARLY_ENV_WARNINGS,
    DEFAULT_LLM_MODEL,
    TradingConfig,
    _parse_bool_env,
    _parse_float_env,
    _parse_int_env,
    _parse_thinking_env,
    _load_llm_model_name,
    _load_llm_temperature,
    _load_llm_max_tokens,
    _load_llm_api_base_url,
    _load_llm_api_key,
    _load_llm_api_type,
    emit_early_env_warnings,
    load_trading_config_from_env,
    load_system_prompt_from_env,
)

colorama_init(autoreset=True)

BASE_DIR = Path(__file__).resolve().parent
DOTENV_PATH = BASE_DIR / ".env"

if DOTENV_PATH.exists():
    dotenv_loaded = load_dotenv(dotenv_path=DOTENV_PATH, override=True)
else:
    dotenv_loaded = load_dotenv(override=True)

DEFAULT_DATA_DIR = BASE_DIR / "data"
DATA_DIR = Path(os.getenv("TRADEBOT_DATA_DIR", str(DEFAULT_DATA_DIR))).expanduser()
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ───────────────────────── CONFIG ─────────────────────────
API_KEY = os.getenv("BN_API_KEY", "")
API_SECRET = os.getenv("BN_SECRET", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_SIGNALS_CHAT_ID = os.getenv("TELEGRAM_SIGNALS_CHAT_ID", "")

HYPERLIQUID_WALLET_ADDRESS = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "")
HYPERLIQUID_PRIVATE_KEY = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")

BACKPACK_API_PUBLIC_KEY = os.getenv("BACKPACK_API_PUBLIC_KEY", "")
BACKPACK_API_SECRET_SEED = os.getenv("BACKPACK_API_SECRET_SEED", "")
BACKPACK_API_BASE_URL = os.getenv("BACKPACK_API_BASE_URL", "https://api.backpack.exchange")
BACKPACK_API_WINDOW_MS = _parse_int_env(
    os.getenv("BACKPACK_API_WINDOW_MS"),
    default=5000,
)

_TRADING_CFG: TradingConfig = load_trading_config_from_env()

PAPER_START_CAPITAL = _TRADING_CFG.paper_start_capital
HYPERLIQUID_CAPITAL = _TRADING_CFG.hyperliquid_capital
TRADING_BACKEND = _TRADING_CFG.trading_backend
MARKET_DATA_BACKEND = _TRADING_CFG.market_data_backend
LIVE_TRADING_ENABLED = _TRADING_CFG.live_trading_enabled
HYPERLIQUID_LIVE_TRADING = _TRADING_CFG.hyperliquid_live_trading
BINANCE_FUTURES_LIVE = _TRADING_CFG.binance_futures_live
BACKPACK_FUTURES_LIVE = _TRADING_CFG.backpack_futures_live
BINANCE_FUTURES_MAX_RISK_USD = _TRADING_CFG.binance_futures_max_risk_usd
BINANCE_FUTURES_MAX_LEVERAGE = _TRADING_CFG.binance_futures_max_leverage
BINANCE_FUTURES_MAX_MARGIN_USD = _TRADING_CFG.binance_futures_max_margin_usd
LIVE_START_CAPITAL = _TRADING_CFG.live_start_capital
LIVE_MAX_RISK_USD = _TRADING_CFG.live_max_risk_usd
LIVE_MAX_LEVERAGE = _TRADING_CFG.live_max_leverage
LIVE_MAX_MARGIN_USD = _TRADING_CFG.live_max_margin_usd
IS_LIVE_BACKEND = _TRADING_CFG.is_live_backend
START_CAPITAL = _TRADING_CFG.start_capital

# Trading symbols to monitor
SYMBOLS = ["ETHUSDT", "SOLUSDT", "XRPUSDT", "BTCUSDT", "DOGEUSDT", "BNBUSDT", "PAXGUSDT", "PUMPUSDT", "MONUSDT", "HYPEUSDT"]
SYMBOL_TO_COIN = {
    "ETHUSDT": "ETH",
    "SOLUSDT": "SOL", 
    "XRPUSDT": "XRP",
    "BTCUSDT": "BTC",
    "DOGEUSDT": "DOGE",
    "BNBUSDT": "BNB",
    "PAXGUSDT": "PAXG",
    "PUMPUSDT": "PUMP",
    "MONUSDT": "MON",
    "HYPEUSDT": "HYPE",
}
COIN_TO_SYMBOL = {coin: symbol for symbol, coin in SYMBOL_TO_COIN.items()}

DEFAULT_TRADING_RULES_PROMPT = """
You are a top level crypto trader focused on multiplying the account while safeguarding capital. Always apply these core rules:

Most Important Rules for Crypto Traders

Capital preservation is the foundation of successful crypto trading—your primary goal is to protect what you have so you can continue trading and growing.

Never Risk More Than 1-2% Per Trade
- Treat the 1% rule as non-negotiable; never risk more than 1-2% of total capital on a single trade.
- Survive losing streaks with enough capital to recover.

Use Stop-Loss Orders on Every Trade
- Define exit points before entering any position.
- Stop-loss orders are mandatory safeguards against emotional decisions.

Follow the Trend—Don't Fight the Market
- Buy rising coins and sell falling ones; the market is always right.
- Wait for confirmation before committing capital.

Stay Inactive Most of the Time
- Trade only when high-probability setups emerge.
- Avoid overtrading; patience and discipline preserve capital.

Cut Losses Quickly and Let Profits Run
- Close losing trades decisively; exit weak performers without hesitation.
- Let winning trades develop and grow when they show early profit.

Maintain a Written Trading Plan
- Know entry, exit, and profit targets before executing.
- Consistently follow the plan to keep emotions in check.

Control Leverage and Position Sizing
- Use leverage responsibly; ensure even a worst-case loss stays within the 1-2% risk cap.
- Proper sizing is central to risk management.

Focus on Small Consistent Wins
- Prioritize steady gains over chasing moonshots.
- Incremental growth compounds reliably and is easier to manage.

Think in Probabilities, Not Predictions
- Treat trading like a probability game with positive expectancy over many trades.
- Shift mindset from needing to be right to managing outcomes.

Stay Informed but Trade Less
- Track market-moving news but trade only when indicators align and risk-reward is favorable.
""".strip()

SYSTEM_PROMPT_SOURCE: Dict[str, Any] = {"type": "default"}


def _load_system_prompt() -> str:
    """Load system prompt from env variables or fall back to default."""
    global SYSTEM_PROMPT_SOURCE
    prompt, source = load_system_prompt_from_env(BASE_DIR, DEFAULT_TRADING_RULES_PROMPT)
    SYSTEM_PROMPT_SOURCE = dict(source)
    return prompt


def describe_system_prompt_source() -> str:
    """Return human-readable description of the active system prompt."""
    source_type = SYSTEM_PROMPT_SOURCE.get("type", "default")
    if source_type == "file":
        return f"file:{SYSTEM_PROMPT_SOURCE.get('path', '?')}"
    if source_type == "env":
        return "env:TRADEBOT_SYSTEM_PROMPT"
    return "default prompt"


TRADING_RULES_PROMPT = _load_system_prompt()

DEFAULT_INTERVAL = "15m"
_INTERVAL_TO_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
}


def _load_trade_interval(default: str = DEFAULT_INTERVAL) -> str:
    """Resolve trade interval from environment."""
    raw = os.getenv("TRADEBOT_INTERVAL")
    if raw:
        candidate = raw.strip().lower()
        if candidate in _INTERVAL_TO_SECONDS:
            return candidate
        EARLY_ENV_WARNINGS.append(
            f"Unsupported TRADEBOT_INTERVAL '{raw}'; using default {default}."
        )
    return default


INTERVAL = _load_trade_interval()
CHECK_INTERVAL = _INTERVAL_TO_SECONDS[INTERVAL]
DEFAULT_RISK_FREE_RATE = 0.0  # Annualized baseline for Sortino ratio calculations


def refresh_llm_configuration_from_env() -> None:
    """Reload LLM-related runtime settings from environment variables."""
    global LLM_MODEL_NAME, LLM_TEMPERATURE, LLM_MAX_TOKENS, LLM_THINKING_PARAM, TRADING_RULES_PROMPT, LLM_API_BASE_URL, LLM_API_KEY, LLM_API_TYPE
    LLM_MODEL_NAME = _load_llm_model_name()
    LLM_TEMPERATURE = _load_llm_temperature()
    LLM_MAX_TOKENS = _load_llm_max_tokens()
    LLM_THINKING_PARAM = _parse_thinking_env(os.getenv("TRADEBOT_LLM_THINKING"))
    TRADING_RULES_PROMPT = _load_system_prompt()
    LLM_API_BASE_URL = _load_llm_api_base_url()
    LLM_API_KEY = _load_llm_api_key(OPENROUTER_API_KEY)
    LLM_API_TYPE = _load_llm_api_type()


def log_system_prompt_info(prefix: str = "System prompt in use") -> None:
    """Log the current system prompt configuration."""
    description = describe_system_prompt_source()
    logging.info("%s: %s", prefix, description)


LLM_MODEL_NAME = _load_llm_model_name()
LLM_TEMPERATURE = _load_llm_temperature()
LLM_MAX_TOKENS = _load_llm_max_tokens()
LLM_THINKING_PARAM = _parse_thinking_env(os.getenv("TRADEBOT_LLM_THINKING"))
LLM_API_BASE_URL = _load_llm_api_base_url()
LLM_API_KEY = _load_llm_api_key(OPENROUTER_API_KEY)
LLM_API_TYPE = _load_llm_api_type()

# Indicator settings
EMA_LEN = 20
RSI_LEN = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# Binance fee structure (as decimals)
MAKER_FEE_RATE = 0.0         # 0.0000%
TAKER_FEE_RATE = 0.000275    # 0.0275%

# ───────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)

emit_early_env_warnings()

def _resolve_risk_free_rate() -> float:
    """Determine the annualized risk-free rate used in Sortino calculations."""
    env_value = os.getenv("SORTINO_RISK_FREE_RATE")
    if env_value is None:
        env_value = os.getenv("RISK_FREE_RATE")
    if env_value is None:
        return DEFAULT_RISK_FREE_RATE
    try:
        return float(env_value)
    except (TypeError, ValueError):
        logging.warning(
            "Invalid SORTINO_RISK_FREE_RATE/RISK_FREE_RATE value '%s'; using default %.4f",
            env_value,
            DEFAULT_RISK_FREE_RATE,
        )
        return DEFAULT_RISK_FREE_RATE

RISK_FREE_RATE = _resolve_risk_free_rate()

if not dotenv_loaded:
    logging.warning(f"No .env file found at {DOTENV_PATH}; falling back to system environment variables.")

if LLM_API_KEY:
    masked_key = (
        LLM_API_KEY
        if len(LLM_API_KEY) <= 12
        else f"{LLM_API_KEY[:6]}...{LLM_API_KEY[-4:]}"
    )
    logging.info(
        "LLM API key configured (length %d).",
        len(LLM_API_KEY),
    )
else:
    logging.error("No LLM API key configured; expected LLM_API_KEY or OPENROUTER_API_KEY in environment.")

client: Optional[Client] = None
_market_data_client: Optional[Any] = None

try:
    hyperliquid_trader = HyperliquidTradingClient(
        live_mode=HYPERLIQUID_LIVE_TRADING,
        wallet_address=HYPERLIQUID_WALLET_ADDRESS,
        secret_key=HYPERLIQUID_PRIVATE_KEY,
    )
except Exception as exc:
    logging.critical("Hyperliquid live trading initialization failed: %s", exc)
    raise SystemExit(1) from exc

binance_futures_exchange: Optional[Any] = None

def get_binance_futures_exchange() -> Optional[Any]:
    global binance_futures_exchange
    if TRADING_BACKEND != "binance_futures" or not BINANCE_FUTURES_LIVE:
        return None
    if binance_futures_exchange is not None:
        return binance_futures_exchange

    api_key = os.getenv("BINANCE_API_KEY") or API_KEY
    api_secret = os.getenv("BINANCE_API_SECRET") or API_SECRET
    if not api_key or not api_secret:
        logging.error(
            "BINANCE_API_KEY and/or BINANCE_API_SECRET missing; unable to initialize Binance futures client.",
        )
        return None

    try:
        exchange = ccxt.binanceusdm(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
            }
        )
        exchange.load_markets()
        binance_futures_exchange = exchange
        logging.info(
            "Binance futures client initialized successfully for USDT-margined contracts.",
        )
    except Exception as exc:
        logging.error("Failed to initialize Binance futures client: %s", exc)
        binance_futures_exchange = None
    return binance_futures_exchange

def get_binance_client() -> Optional[Client]:
    """Return a connected Binance client or None if initialization failed."""
    global client

    if client is not None:
        return client

    if not API_KEY or not API_SECRET:
        logging.error("BN_API_KEY and/or BN_SECRET missing; unable to initialize Binance client.")
        return None

    try:
        logging.info("Attempting to initialize Binance client...")
        client = Client(API_KEY, API_SECRET, testnet=False)
        logging.info("Binance client initialized successfully.")
    except Timeout as exc:
        logging.warning(
            "Timed out while connecting to Binance API: %s. Will retry automatically without exiting.",
            exc,
        )
        client = None
    except RequestException as exc:
        logging.error(
            "Network error while connecting to Binance API: %s. Will retry automatically.",
            exc,
        )
        client = None
    except Exception as exc:
        logging.error(
            "Unexpected error while initializing Binance client: %s",
            exc,
            exc_info=True,
        )
        client = None

    return client

def get_market_data_client() -> Optional[Any]:
    global _market_data_client
    if _market_data_client is not None:
        return _market_data_client
    backend = MARKET_DATA_BACKEND
    logging.info("Initializing market data backend: %s", backend)
    if backend == "binance":
        binance_client = get_binance_client()
        if not binance_client:
            return None
        _market_data_client = BinanceMarketDataClient(binance_client)
        return _market_data_client
    if backend == "backpack":
        _market_data_client = BackpackMarketDataClient(BACKPACK_API_BASE_URL)
        return _market_data_client
    return None

# ──────────────────────── GLOBAL STATE ─────────────────────
balance: float = START_CAPITAL
positions: Dict[str, Dict[str, Any]] = {}  # coin -> position info
trade_history: List[Dict[str, Any]] = []
def _default_time_provider() -> datetime:
    """Return current UTC time; overridable for testing/backtests."""
    return datetime.now(timezone.utc)


_current_time_provider: Callable[[], datetime] = _default_time_provider


def get_current_time() -> datetime:
    """Return the current time from the active provider."""
    return _current_time_provider()


def set_time_provider(provider: Optional[Callable[[], datetime]]) -> None:
    """Override the time provider; pass None to restore wall-clock time."""
    global _current_time_provider
    _current_time_provider = provider or _default_time_provider


BOT_START_TIME = get_current_time()
invocation_count: int = 0
iteration_counter: int = 0
ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
current_iteration_messages: List[str] = []
equity_history: List[float] = []

# CSV files
STATE_CSV = DATA_DIR / "portfolio_state.csv"
STATE_JSON = DATA_DIR / "portfolio_state.json"
TRADES_CSV = DATA_DIR / "trade_history.csv"
DECISIONS_CSV = DATA_DIR / "ai_decisions.csv"
MESSAGES_CSV = DATA_DIR / "ai_messages.csv"
MESSAGES_RECENT_CSV = DATA_DIR / "ai_messages_recent.csv"
MAX_RECENT_MESSAGES = 100
STATE_COLUMNS = [
    'timestamp',
    'total_balance',
    'total_equity',
    'total_return_pct',
    'num_positions',
    'position_details',
    'total_margin',
    'net_unrealized_pnl',
    'btc_price',
]
last_btc_price: Optional[float] = None

# ───────────────────────── CSV LOGGING ──────────────────────

def init_csv_files() -> None:
    """Initialize CSV files with headers."""
    _init_csv_files_for_paths(
        STATE_CSV,
        TRADES_CSV,
        DECISIONS_CSV,
        MESSAGES_CSV,
        MESSAGES_RECENT_CSV,
        STATE_COLUMNS,
    )

def get_btc_benchmark_price() -> Optional[float]:
    """Fetch the current BTC/USDT price for benchmarking."""
    global last_btc_price
    data = fetch_market_data("BTCUSDT")
    if data and "price" in data:
        try:
            last_btc_price = float(data["price"])
        except (TypeError, ValueError):
            logging.debug("Received non-numeric BTC price: %s", data["price"])
    return last_btc_price

def log_portfolio_state() -> None:
    """Log current portfolio state."""
    total_equity = calculate_total_equity()
    total_return = ((total_equity - START_CAPITAL) / START_CAPITAL) * 100
    total_margin = calculate_total_margin()
    net_unrealized = total_equity - balance - total_margin
    
    position_details = "; ".join([
        f"{coin}:{pos['side']}:{pos['quantity']:.4f}@{pos['entry_price']:.4f}"
        for coin, pos in positions.items()
    ]) if positions else "No positions"
    
    btc_price = get_btc_benchmark_price()
    btc_price_str = f"{btc_price:.2f}" if btc_price is not None else ""

    timestamp = get_current_time().isoformat()
    _append_portfolio_state_row(
        STATE_CSV,
        timestamp,
        f"{balance:.2f}",
        f"{total_equity:.2f}",
        f"{total_return:.2f}",
        len(positions),
        position_details,
        f"{total_margin:.2f}",
        f"{net_unrealized:.2f}",
        btc_price_str,
    )

def sleep_with_countdown(total_seconds: int) -> None:
    """Sleep with a simple terminal countdown on a single line.

    Uses print + carriage return instead of logging to avoid spamming log files.
    """
    try:
        remaining = int(total_seconds)
        if remaining <= 0:
            return
        while remaining > 0:
            print(
                f"\rWaiting for next check in {remaining} seconds... ",
                end="",
                flush=True,
            )
            time.sleep(1)
            remaining -= 1
        print("\rWaiting for next check in 0 seconds...           ")
    except KeyboardInterrupt:
        print()
        raise

def log_trade(coin: str, action: str, details: Dict[str, Any]) -> None:
    """Log trade execution."""
    timestamp = get_current_time().isoformat()
    _append_trade_row(
        TRADES_CSV,
        timestamp,
        coin,
        action,
        str(details.get('side', '')),
        details.get('quantity', 0),
        details.get('price', 0),
        details.get('profit_target', 0),
        details.get('stop_loss', 0),
        details.get('leverage', 1),
        details.get('confidence', 0),
        details.get('pnl', 0),
        balance,
        str(details.get('reason', '')),
    )

def log_ai_decision(coin: str, signal: str, reasoning: str, confidence: float) -> None:
    """Log AI decision."""
    with open(DECISIONS_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            get_current_time().isoformat(),
            coin,
            signal,
            reasoning,
            confidence
        ])
    

def log_ai_message(direction: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    """Log raw messages exchanged with the AI provider.

    This thin wrapper preserves the original bot.log_ai_message API while
    delegating the actual file I/O and recent-messages bookkeeping to the
    notifications module.
    """
    _notifications_log_ai_message(
        messages_csv=MESSAGES_CSV,
        messages_recent_csv=MESSAGES_RECENT_CSV,
        max_recent_messages=MAX_RECENT_MESSAGES,
        now_iso=get_current_time().isoformat(),
        direction=direction,
        role=role,
        content=content,
        metadata=metadata,
    )

def strip_ansi_codes(text: str) -> str:
    """Remove ANSI color codes so Telegram receives plain text."""
    return ANSI_ESCAPE_RE.sub("", text)

def escape_markdown(text: str) -> str:
    """Escape characters that have special meaning in Telegram Markdown."""
    if not text:
        return text
    specials = r"_*[]()~`>#+-=|{}.!\\"
    return "".join(f"\\{char}" if char in specials else char for char in text)

def record_iteration_message(text: str) -> None:
    """Record console output for this iteration to share via Telegram."""
    _notifications_record_iteration_message(current_iteration_messages, text)

def send_telegram_message(text: str, chat_id: Optional[str] = None, parse_mode: Optional[str] = "Markdown") -> None:
    """Send a notification message to Telegram if credentials are configured.

    This wrapper preserves the original bot.send_telegram_message signature while
    delegating the HTTP details to notifications.send_telegram_message.
    """
    _notifications_send_telegram_message(
        bot_token=TELEGRAM_BOT_TOKEN,
        default_chat_id=TELEGRAM_CHAT_ID,
        text=text,
        chat_id=chat_id,
        parse_mode=parse_mode,
    )

def notify_error(
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
    *,
    log_error: bool = True,
) -> None:
    """Log an error and forward a brief description to Telegram.

    The public behaviour remains the same, but the implementation is routed
    through notifications.notify_error so that error handling is centralised.
    """

    def _log(direction: str, role: str, content: str, meta: Optional[Dict[str, Any]]) -> None:
        log_ai_message(direction=direction, role=role, content=content, metadata=meta)

    def _send(text: str, chat_id: Optional[str], parse_mode: Optional[str]) -> None:
        send_telegram_message(text, chat_id=chat_id, parse_mode=parse_mode)

    _notifications_notify_error(
        message=message,
        metadata=metadata,
        log_error=log_error,
        log_ai_message_fn=_log,
        send_telegram_message_fn=_send,
    )

# ───────────────────────── STATE MGMT ───────────────────────

def load_state() -> None:
    """Load persisted balance and positions if available."""
    global balance, positions, iteration_counter

    if not STATE_JSON.exists():
        logging.info("No existing state file found; starting fresh.")
        return

    try:
        new_balance, new_positions, new_iteration = _load_state_from_json(
            STATE_JSON,
            START_CAPITAL,
            TAKER_FEE_RATE,
        )
        balance = new_balance
        positions = new_positions
        iteration_counter = new_iteration
        logging.info(
            "Loaded state from %s (balance: %.2f, positions: %d)",
            STATE_JSON,
            balance,
            len(positions),
        )
    except Exception as e:
        logging.error("Failed to load state from %s: %s", STATE_JSON, e, exc_info=True)
        balance = START_CAPITAL
        positions = {}

def save_state() -> None:
    """Persist current balance, open positions, and iteration counter."""
    payload = {
        "balance": balance,
        "positions": positions,
        "iteration": iteration_counter,
        "updated_at": get_current_time().isoformat(),
    }
    _save_state_to_json(STATE_JSON, payload)


def reset_state(initial_balance: Optional[float] = None) -> None:
    """Reset in-memory trading state to start a fresh run."""
    global balance, positions, trade_history, iteration_counter, equity_history, invocation_count, current_iteration_messages, BOT_START_TIME
    balance = float(initial_balance) if initial_balance is not None else START_CAPITAL
    positions = {}
    trade_history = []
    iteration_counter = 0
    invocation_count = 0
    equity_history.clear()
    current_iteration_messages = []
    BOT_START_TIME = get_current_time()


def load_equity_history() -> None:
    """Populate the in-memory equity history for performance calculations."""
    _load_equity_history_from_csv(STATE_CSV, equity_history)

def register_equity_snapshot(total_equity: float) -> None:
    """Append the latest equity to the history if it is a finite value."""
    if total_equity is None:
        return
    if isinstance(total_equity, (int, float, np.floating)) and np.isfinite(total_equity):
        equity_history.append(float(total_equity))

# ───────────────────────── INDICATORS ───────────────────────

def calculate_rsi_series(close: pd.Series, period: int) -> pd.Series:
    """Return RSI series for specified period using Wilder's smoothing."""
    return _strategy_calculate_rsi_series(close, period)


def add_indicator_columns(
    df: pd.DataFrame,
    ema_lengths: Iterable[int] = (EMA_LEN,),
    rsi_periods: Iterable[int] = (RSI_LEN,),
    macd_params: Iterable[int] = (MACD_FAST, MACD_SLOW, MACD_SIGNAL),
) -> pd.DataFrame:
    """Return copy of df with EMA, RSI, and MACD columns added."""
    return _strategy_add_indicator_columns(df, ema_lengths, rsi_periods, macd_params)


def calculate_atr_series(df: pd.DataFrame, period: int) -> pd.Series:
    """Return Average True Range series for the provided period."""
    return _strategy_calculate_atr_series(df, period)


def calculate_indicators(df: pd.DataFrame) -> pd.Series:
    """Calculate technical indicators and return the latest row."""
    return _strategy_calculate_indicators(
        df,
        EMA_LEN,
        RSI_LEN,
        MACD_FAST,
        MACD_SLOW,
        MACD_SIGNAL,
    )

def fetch_market_data(symbol: str) -> Optional[Dict[str, Any]]:
    """Fetch current market data for a symbol."""
    market_client = get_market_data_client()
    if not market_client:
        logging.warning("Skipping market data fetch for %s: market data client unavailable.", symbol)
        return None

    try:
        klines = market_client.get_klines(symbol=symbol, interval=INTERVAL, limit=50)
        if not klines:
            logging.warning("Skipping market data fetch for %s: no klines returned.", symbol)
            return None

        df = pd.DataFrame(
            klines,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_volume",
                "trades",
                "taker_base",
                "taker_quote",
                "ignore",
            ],
        )

        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["open"] = df["open"].astype(float)

        last = calculate_indicators(df)
        latest_bar = df.iloc[-1]
        last_high = float(latest_bar["high"])
        last_low = float(latest_bar["low"])
        last_close = float(latest_bar["close"])

        funding_rates = market_client.get_funding_rate_history(symbol=symbol, limit=1)
        funding_rate = float(funding_rates[-1]) if funding_rates else 0.0

        return {
            "symbol": symbol,
            "price": last_close,
            "high": last_high,
            "low": last_low,
            "ema20": last["ema20"],
            "rsi": last["rsi"],
            "macd": last["macd"],
            "macd_signal": last["macd_signal"],
            "funding_rate": funding_rate,
        }
    except Exception as e:
        logging.error(f"Error fetching data for {symbol}: {e}")
        return None


def round_series(values: Iterable[Any], precision: int) -> List[float]:
    """Round numeric iterable to the given precision, skipping NaNs."""
    return _strategy_round_series(values, precision)


def collect_prompt_market_data(symbol: str) -> Optional[Dict[str, Any]]:
    """Return rich market snapshot for prompt composition."""
    market_client = get_market_data_client()
    if not market_client:
        return None

    try:
        execution_klines = market_client.get_klines(symbol=symbol, interval=INTERVAL, limit=200)
        df_execution = pd.DataFrame(
            execution_klines,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_volume",
                "trades",
                "taker_base",
                "taker_quote",
                "ignore",
            ],
        )
        if df_execution.empty:
            logging.warning("Skipping market snapshot for %s: execution klines unavailable.", symbol)
            return None

        numeric_cols = ["open", "high", "low", "close", "volume"]
        df_execution[numeric_cols] = df_execution[numeric_cols].astype(float)
        df_execution["mid_price"] = (df_execution["high"] + df_execution["low"]) / 2
        df_execution = add_indicator_columns(
            df_execution,
            ema_lengths=(EMA_LEN,),
            rsi_periods=(RSI_LEN,),
            macd_params=(MACD_FAST, MACD_SLOW, MACD_SIGNAL),
        )

        structure_klines = market_client.get_klines(symbol=symbol, interval="1h", limit=100)
        df_structure = pd.DataFrame(
            structure_klines,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_volume",
                "trades",
                "taker_base",
                "taker_quote",
                "ignore",
            ],
        )
        if df_structure.empty:
            logging.warning("Skipping market snapshot for %s: structure klines unavailable.", symbol)
            return None
        df_structure[numeric_cols] = df_structure[numeric_cols].astype(float)
        df_structure = add_indicator_columns(
            df_structure,
            ema_lengths=(20, 50),
            rsi_periods=(14,),
            macd_params=(MACD_FAST, MACD_SLOW, MACD_SIGNAL),
        )
        df_structure["swing_high"] = df_structure["high"].rolling(window=5, center=True).max()
        df_structure["swing_low"] = df_structure["low"].rolling(window=5, center=True).min()
        df_structure["volume_sma"] = df_structure["volume"].rolling(window=20).mean()
        df_structure["volume_ratio"] = df_structure["volume"] / df_structure["volume_sma"].replace(0, np.nan)

        trend_klines = market_client.get_klines(symbol=symbol, interval="4h", limit=100)
        df_trend = pd.DataFrame(
            trend_klines,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_volume",
                "trades",
                "taker_base",
                "taker_quote",
                "ignore",
            ],
        )
        if df_trend.empty:
            logging.warning("Skipping market snapshot for %s: trend klines unavailable.", symbol)
            return None
        df_trend[numeric_cols] = df_trend[numeric_cols].astype(float)
        df_trend = add_indicator_columns(
            df_trend,
            ema_lengths=(20, 50, 200),
            rsi_periods=(14,),
            macd_params=(MACD_FAST, MACD_SLOW, MACD_SIGNAL),
        )
        df_trend["macd_histogram"] = df_trend["macd"] - df_trend["macd_signal"]
        df_trend["atr"] = calculate_atr_series(df_trend, 14)

        open_interest_values = market_client.get_open_interest_history(symbol=symbol, limit=30)
        funding_rates = market_client.get_funding_rate_history(symbol=symbol, limit=30)
        return _strategy_build_market_snapshot(
            symbol=symbol,
            coin=SYMBOL_TO_COIN[symbol],
            df_execution=df_execution,
            df_structure=df_structure,
            df_trend=df_trend,
            open_interest_values=open_interest_values,
            funding_rates=funding_rates,
        )
    except Exception as exc:
        logging.error("Failed to build market snapshot for %s: %s", symbol, exc, exc_info=True)
        return None

# ───────────────────── AI DECISION MAKING ───────────────────

def format_prompt_for_deepseek() -> str:
    """Compose a rich prompt resembling the original DeepSeek in-context format."""
    global invocation_count
    invocation_count += 1

    now = get_current_time()
    minutes_running = int((now - BOT_START_TIME).total_seconds() // 60)

    market_snapshots: Dict[str, Dict[str, Any]] = {}
    for symbol in SYMBOLS:
        snapshot = collect_prompt_market_data(symbol)
        if snapshot:
            market_snapshots[snapshot["coin"]] = snapshot

    total_margin = calculate_total_margin()
    total_equity = balance + total_margin
    for coin, pos in positions.items():
        current_price = market_snapshots.get(coin, {}).get("price", pos["entry_price"])
        total_equity += calculate_unrealized_pnl(coin, current_price)

    total_return = ((total_equity - START_CAPITAL) / START_CAPITAL) * 100 if START_CAPITAL else 0.0
    net_unrealized_total = total_equity - balance - total_margin

    position_payloads: List[Dict[str, Any]] = []
    for coin, pos in positions.items():
        current_price = market_snapshots.get(coin, {}).get("price", pos["entry_price"])
        quantity = pos["quantity"]
        gross_unrealized = calculate_unrealized_pnl(coin, current_price)
        leverage = pos.get("leverage", 1) or 1
        if pos["side"] == "long":
            liquidation_price = pos["entry_price"] * max(0.0, 1 - 1 / leverage)
        else:
            liquidation_price = pos["entry_price"] * (1 + 1 / leverage)
        notional_value = quantity * current_price
        position_payloads.append(
            {
                "symbol": coin,
                "side": pos["side"],
                "quantity": quantity,
                "entry_price": pos["entry_price"],
                "current_price": current_price,
                "liquidation_price": liquidation_price,
                "unrealized_pnl": gross_unrealized,
                "leverage": pos.get("leverage", 1),
                "exit_plan": {
                    "profit_target": pos.get("profit_target"),
                    "stop_loss": pos.get("stop_loss"),
                    "invalidation_condition": pos.get("invalidation_condition"),
                },
                "confidence": pos.get("confidence", 0.0),
                "risk_usd": pos.get("risk_usd"),
                "sl_oid": pos.get("sl_oid", -1),
                "tp_oid": pos.get("tp_oid", -1),
                "wait_for_fill": pos.get("wait_for_fill", False),
                "entry_oid": pos.get("entry_oid", -1),
                "live_backend": pos.get("live_backend"),
                "notional_usd": notional_value,
            }
        )

    context = {
        "minutes_running": minutes_running,
        "now_iso": now.isoformat(),
        "invocation_count": invocation_count,
        "interval": INTERVAL,
        "market_snapshots": market_snapshots,
        "account": {
            "total_return": total_return,
            "balance": balance,
            "total_margin": total_margin,
            "net_unrealized_total": net_unrealized_total,
            "total_equity": total_equity,
        },
        "positions": position_payloads,
    }

    return _strategy_build_trading_prompt(context)

def _recover_partial_decisions(json_str: str) -> Optional[Tuple[Dict[str, Any], List[str]]]:
    """Attempt to salvage individual coin decisions from truncated JSON.

    This thin wrapper delegates to strategy_core.recover_partial_decisions so
    that the recovery algorithm lives in strategy_core while preserving this
    helper's name and signature for existing callers and tests.
    """
    coins = list(SYMBOL_TO_COIN.values())
    return _strategy_recover_partial_decisions(json_str, coins)


def _log_llm_decisions(decisions: Dict[str, Any]) -> None:
    """Log a compact, human-readable summary of LLM decisions for all coins."""
    try:
        parts: List[str] = []
        for coin, raw_decision in decisions.items():
            if not isinstance(raw_decision, dict):
                continue
            decision = raw_decision
            signal = str(decision.get("signal", "hold")).lower()
            side = str(decision.get("side", "")).lower()
            quantity = decision.get("quantity")
            tp = decision.get("profit_target")
            sl = decision.get("stop_loss")
            confidence = decision.get("confidence")

            if signal == "entry":
                parts.append(
                    f"{coin}: ENTRY {side or '-'} qty={quantity} tp={tp} sl={sl} conf={confidence}"
                )
            elif signal == "close":
                parts.append(f"{coin}: CLOSE {side or '-'}")
            else:
                parts.append(f"{coin}: HOLD")

        if parts:
            logging.info("LLM decisions: %s", " | ".join(parts))
    except Exception:
        logging.exception("Failed to log LLM decisions")


def call_deepseek_api(prompt: str) -> Optional[Dict[str, Any]]:
    """Call OpenRouter API with DeepSeek Chat V3.1."""
    api_key = LLM_API_KEY
    if not api_key:
        logging.error("No LLM API key configured; expected LLM_API_KEY or OPENROUTER_API_KEY in environment.")
        return None
    try:
        request_metadata: Dict[str, Any] = {
            "model": LLM_MODEL_NAME,
            "temperature": LLM_TEMPERATURE,
            "max_tokens": LLM_MAX_TOKENS,
        }
        if LLM_THINKING_PARAM is not None:
            request_metadata["thinking"] = LLM_THINKING_PARAM

        log_ai_message(
            direction="sent",
            role="system",
            content=TRADING_RULES_PROMPT,
            metadata=request_metadata,
        )
        log_ai_message(
            direction="sent",
            role="user",
            content=prompt,
            metadata=request_metadata,
        )

        request_payload: Dict[str, Any] = {
            "model": LLM_MODEL_NAME,
            "messages": [
                {
                    "role": "system",
                    "content": TRADING_RULES_PROMPT,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": LLM_TEMPERATURE,
            "max_tokens": LLM_MAX_TOKENS,
        }
        if LLM_THINKING_PARAM is not None:
            request_payload["thinking"] = LLM_THINKING_PARAM

        headers: Dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        api_type = (LLM_API_TYPE or "openrouter").lower()
        if api_type == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/crypto-trading-bot"
            headers["X-Title"] = "DeepSeek Trading Bot"

        response = requests.post(
            url=LLM_API_BASE_URL,
            headers=headers,
            json=request_payload,
            timeout=90,
        )

        if response.status_code != 200:
            notify_error(
                f"LLM API error: {response.status_code}",
                metadata={
                    "status_code": response.status_code,
                    "response_text": response.text,
                },
            )
            return None

        result = response.json()
        choices = result.get("choices")
        if not choices:
            notify_error(
                "LLM API returned no choices",
                metadata={
                    "status_code": response.status_code,
                    "response_text": response.text[:500],
                },
            )
            return None

        primary_choice = choices[0]
        message = primary_choice.get("message") or {}
        content = message.get("content", "") or ""
        finish_reason = primary_choice.get("finish_reason")

        log_ai_message(
            direction="received",
            role="assistant",
            content=content,
            metadata={
                "status_code": response.status_code,
                "response_id": result.get("id"),
                "usage": result.get("usage"),
                "finish_reason": finish_reason,
            }
        )

        decisions = _strategy_parse_llm_json_decisions(
            content,
            response_id=result.get("id"),
            status_code=response.status_code,
            finish_reason=finish_reason,
            notify_error=notify_error,
            log_llm_decisions=_log_llm_decisions,
            recover_partial_decisions=_recover_partial_decisions,
        )
        return decisions
    except Exception as e:
        logging.exception("Error calling LLM API")
        notify_error(
            f"Error calling LLM API: {e}",
            metadata={"context": "call_deepseek_api"},
            log_error=False,
        )
        return None

# ───────────────────── POSITION MANAGEMENT ──────────────────

def calculate_unrealized_pnl(coin: str, current_price: float) -> float:
    """Calculate unrealized PnL for a position."""
    if coin not in positions:
        return 0.0

    pos = positions[coin]
    return _metrics_unrealized_pnl_for_pos(pos, current_price)


def calculate_net_unrealized_pnl(coin: str, current_price: float) -> float:
    """Calculate unrealized PnL after subtracting fees already paid."""
    pos = positions.get(coin)
    if not pos:
        return 0.0
    return _metrics_net_unrealized_pnl_for_pos(pos, current_price)


def calculate_pnl_for_price(pos: Dict[str, Any], target_price: float) -> float:
    """Return gross PnL for a hypothetical exit price."""
    return _metrics_calculate_pnl_for_price(pos, target_price)


def estimate_exit_fee(pos: Dict[str, Any], exit_price: float) -> float:
    """Estimate taker/maker fee required to exit the position at the given price."""
    return _metrics_estimate_exit_fee_for_pos(pos, exit_price, TAKER_FEE_RATE)


def format_leverage_display(leverage: Any) -> str:
    return _metrics_format_leverage_display(leverage)

def calculate_total_margin() -> float:
    """Return sum of margin allocated across all open positions."""
    return _metrics_total_margin_for_positions(positions.values())

def calculate_total_equity() -> float:
    """Calculate total equity (balance + unrealized PnL)."""
    total = balance + calculate_total_margin()
    
    for coin in positions:
        symbol = next((s for s, c in SYMBOL_TO_COIN.items() if c == coin), None)
        if not symbol:
            continue
        data = fetch_market_data(symbol)
        if data:
            total += calculate_unrealized_pnl(coin, data['price'])
    
    return total

def calculate_sortino_ratio(
    equity_values: Iterable[float],
    period_seconds: float,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
) -> Optional[float]:
    """
    Compute the annualized Sortino ratio from equity snapshots.

    Args:
        equity_values: Sequence of equity values in chronological order.
        period_seconds: Average period between snapshots (used to annualize).
        risk_free_rate: Annualized risk-free rate (decimal form).
    """
    return _metrics_calculate_sortino_ratio(
        equity_values,
        period_seconds,
        risk_free_rate,
    )

def execute_entry(coin: str, decision: Dict[str, Any], current_price: float) -> None:
    """Execute entry trade."""
    global balance
    
    if coin in positions:
        logging.warning(f"{coin}: Already have position, skipping entry")
        return
    
    plan = _compute_entry_plan(
        coin=coin,
        decision=decision,
        current_price=current_price,
        balance=balance,
        is_live_backend=IS_LIVE_BACKEND,
        live_max_leverage=LIVE_MAX_LEVERAGE,
        live_max_risk_usd=LIVE_MAX_RISK_USD,
        live_max_margin_usd=LIVE_MAX_MARGIN_USD,
        maker_fee_rate=MAKER_FEE_RATE,
        taker_fee_rate=TAKER_FEE_RATE,
    )
    if plan is None:
        return

    side = plan.side
    stop_loss_price = plan.stop_loss_price
    profit_target_price = plan.profit_target_price
    risk_usd = plan.risk_usd
    quantity = plan.quantity
    position_value = plan.position_value
    margin_required = plan.margin_required
    liquidity = plan.liquidity
    fee_rate = plan.fee_rate
    entry_fee = plan.entry_fee
    total_cost = plan.total_cost
    raw_reason = plan.raw_reason
    leverage = plan.leverage
    leverage_display = format_leverage_display(leverage)

    entry_result: Optional[EntryResult] = None
    live_backend: Optional[str] = None
    if (
        (TRADING_BACKEND == "binance_futures" and BINANCE_FUTURES_LIVE)
        or (TRADING_BACKEND == "backpack_futures" and BACKPACK_FUTURES_LIVE)
        or (TRADING_BACKEND == "hyperliquid" and hyperliquid_trader.is_live)
    ):
        entry_result, live_backend = _route_live_entry(
            coin=coin,
            side=side,
            quantity=quantity,
            current_price=current_price,
            stop_loss_price=stop_loss_price,
            profit_target_price=profit_target_price,
            leverage=leverage,
            liquidity=liquidity,
            trading_backend=TRADING_BACKEND,
            binance_futures_live=BINANCE_FUTURES_LIVE,
            backpack_futures_live=BACKPACK_FUTURES_LIVE,
            hyperliquid_is_live=hyperliquid_trader.is_live,
            get_binance_futures_exchange=get_binance_futures_exchange,
            backpack_api_public_key=BACKPACK_API_PUBLIC_KEY,
            backpack_api_secret_seed=BACKPACK_API_SECRET_SEED,
            backpack_api_base_url=BACKPACK_API_BASE_URL,
            backpack_api_window_ms=BACKPACK_API_WINDOW_MS,
            hyperliquid_trader=hyperliquid_trader,
        )
        if entry_result is None and live_backend is None:
            # Live routing failed; abort entry.
            return

    # Open position
    positions[coin] = {
        'side': side,
        'quantity': quantity,
        'entry_price': current_price,
        'profit_target': profit_target_price,
        'stop_loss': stop_loss_price,
        'leverage': leverage,
        'confidence': decision.get('confidence', 0),
        'invalidation_condition': decision.get('invalidation_condition', ''),
        'margin': margin_required,
        'fees_paid': entry_fee,
        'fee_rate': fee_rate,
        'liquidity': liquidity,
        'risk_usd': risk_usd,
        'wait_for_fill': decision.get('wait_for_fill', False),
        'live_backend': live_backend,
        'entry_oid': entry_result.entry_oid if entry_result else -1,
        'tp_oid': entry_result.tp_oid if entry_result else -1,
        'sl_oid': entry_result.sl_oid if entry_result else -1,
        'entry_justification': raw_reason,
        'last_justification': raw_reason,
    }
    
    balance -= total_cost
    
    entry_price = current_price
    target_price = profit_target_price
    stop_price = stop_loss_price

    gross_at_target = calculate_pnl_for_price(positions[coin], target_price)
    gross_at_stop = calculate_pnl_for_price(positions[coin], stop_price)
    exit_fee_target = estimate_exit_fee(positions[coin], target_price)
    exit_fee_stop = estimate_exit_fee(positions[coin], stop_price)
    net_at_target = gross_at_target - (entry_fee + exit_fee_target)
    net_at_stop = gross_at_stop - (entry_fee + exit_fee_stop)

    expected_reward = max(gross_at_target, 0.0)
    expected_risk = max(-gross_at_stop, 0.0)
    if expected_risk > 0:
        rr_value = expected_reward / expected_risk if expected_reward > 0 else 0.0
        rr_display = f"{rr_value:.2f}:1"
    else:
        rr_display = "n/a"

    reason_text = raw_reason or "No justification provided."
    reason_text = " ".join(reason_text.split())
    reason_text_for_signal = escape_markdown(reason_text)

    emit_entry_console_log(
        coin=coin,
        side=side,
        leverage_display=leverage_display,
        entry_price=entry_price,
        quantity=quantity,
        margin_required=margin_required,
        risk_usd=risk_usd,
        liquidity=liquidity,
        target_price=target_price,
        stop_price=stop_price,
        gross_at_target=gross_at_target,
        net_at_target=net_at_target,
        gross_at_stop=gross_at_stop,
        net_at_stop=net_at_stop,
        entry_fee=entry_fee,
        fee_rate=fee_rate,
        rr_display=rr_display,
        confidence=decision.get('confidence', 0),
        raw_reason=raw_reason,
        entry_result=entry_result,
        print_fn=print,
        record_fn=record_iteration_message,
    )

    # Send rich ENTRY signal to the dedicated signals group (if configured).
    try:
        send_entry_signal_to_telegram(
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
            confidence=decision.get('confidence', 0),
            reason_text_for_signal=reason_text_for_signal,
            liquidity=liquidity,
            timestamp=get_current_time().strftime('%Y-%m-%d %H:%M:%S UTC'),
            send_fn=lambda text, chat_id, parse_mode: send_telegram_message(
                text,
                chat_id=chat_id,
                parse_mode=parse_mode,
            ),
            signals_chat_id=TELEGRAM_SIGNALS_CHAT_ID,
        )
    except Exception as exc:
        # Keep trading even if notifications fail
        logging.debug("Failed to send ENTRY signal to Telegram (non-fatal): %s", exc)
    
    log_trade(coin, 'ENTRY', {
        'side': side,
        'quantity': quantity,
        'price': current_price,
        'profit_target': decision['profit_target'],
        'stop_loss': decision['stop_loss'],
        'leverage': leverage,
        'confidence': decision.get('confidence', 0),
        'pnl': 0,
        'reason': f"{reason_text or 'AI entry signal'} | Fees: ${entry_fee:.2f}"
    })
    save_state()

def execute_close(coin: str, decision: Dict[str, Any], current_price: float) -> None:
    """Execute close trade."""
    global balance
    
    if coin not in positions:
        logging.warning(f"{coin}: No position to close")
        return
    
    pos = positions[coin]
    pnl = calculate_unrealized_pnl(coin, current_price)

    close_plan = _compute_close_plan(
        coin=coin,
        decision=decision,
        current_price=current_price,
        position=pos,
        pnl=pnl,
        default_fee_rate=TAKER_FEE_RATE,
    )
    raw_reason = close_plan.raw_reason
    reason_text = close_plan.reason_text
    reason_text_for_signal = escape_markdown(reason_text)
    fee_rate = close_plan.fee_rate
    exit_fee = close_plan.exit_fee
    total_fees = close_plan.total_fees
    net_pnl = close_plan.net_pnl

    close_result: Optional[CloseResult] = None
    if (
        (TRADING_BACKEND == "binance_futures" and BINANCE_FUTURES_LIVE)
        or (TRADING_BACKEND == "backpack_futures" and BACKPACK_FUTURES_LIVE)
        or (TRADING_BACKEND == "hyperliquid" and hyperliquid_trader.is_live)
    ):
        close_result = _route_live_close(
            coin=coin,
            side=pos['side'],
            quantity=pos['quantity'],
            current_price=current_price,
            trading_backend=TRADING_BACKEND,
            binance_futures_live=BINANCE_FUTURES_LIVE,
            backpack_futures_live=BACKPACK_FUTURES_LIVE,
            hyperliquid_is_live=hyperliquid_trader.is_live,
            get_binance_futures_exchange=get_binance_futures_exchange,
            backpack_api_public_key=BACKPACK_API_PUBLIC_KEY,
            backpack_api_secret_seed=BACKPACK_API_SECRET_SEED,
            backpack_api_base_url=BACKPACK_API_BASE_URL,
            backpack_api_window_ms=BACKPACK_API_WINDOW_MS,
            hyperliquid_trader=hyperliquid_trader,
            coin_to_symbol=COIN_TO_SYMBOL,
        )
        if close_result is None:
            # Live close failed; keep position open.
            return
    
    # Return margin and add net PnL (after fees)
    balance += pos['margin'] + net_pnl

    emit_close_console_log(
        coin=coin,
        pos=pos,
        current_price=current_price,
        pnl=pnl,
        exit_fee=exit_fee,
        total_fees=total_fees,
        net_pnl=net_pnl,
        reason_text=reason_text,
        balance=balance,
        close_result=close_result,
        print_fn=print,
        record_fn=record_iteration_message,
    )
    
    log_trade(coin, 'CLOSE', {
        'side': pos['side'],
        'quantity': pos['quantity'],
        'price': current_price,
        'profit_target': 0,
        'stop_loss': 0,
        'leverage': pos['leverage'],
        'confidence': 0,
        'pnl': net_pnl,
        'reason': (
            f"{reason_text} | "
            f"Gross: ${pnl:.2f} | Fees: ${total_fees:.2f}"
        )
    })
    
    del positions[coin]
    save_state()
    
    # Send rich CLOSE signal to the dedicated signals group (if configured).
    try:
        send_close_signal_to_telegram(
            coin=coin,
            side=pos['side'],
            quantity=pos['quantity'],
            entry_price=pos['entry_price'],
            current_price=current_price,
            pnl=pnl,
            total_fees=total_fees,
            net_pnl=net_pnl,
            margin=pos['margin'],
            balance=balance,
            reason_text_for_signal=reason_text_for_signal,
            timestamp=get_current_time().strftime('%Y-%m-%d %H:%M:%S UTC'),
            send_fn=lambda text, chat_id, parse_mode: send_telegram_message(
                text,
                chat_id=chat_id,
                parse_mode=parse_mode,
            ),
            signals_chat_id=TELEGRAM_SIGNALS_CHAT_ID,
        )
    except Exception as exc:
        logging.debug("Failed to send CLOSE signal to Telegram (non-fatal): %s", exc)


def process_ai_decisions(decisions: Dict[str, Any]) -> None:
    """Handle AI decisions for each tracked coin."""
    for coin in SYMBOL_TO_COIN.values():
        if coin not in decisions:
            continue

        decision = decisions[coin]
        signal = decision.get("signal", "hold")

        log_ai_decision(
            coin,
            signal,
            decision.get("justification", ""),
            decision.get("confidence", 0),
        )

        symbol = COIN_TO_SYMBOL.get(coin)
        if not symbol:
            logging.debug("No symbol mapping found for coin %s", coin)
            continue

        data = fetch_market_data(symbol)
        if not data:
            continue

        current_price = data["price"]

        if signal == "entry":
            execute_entry(coin, decision, current_price)
        elif signal == "close":
            execute_close(coin, decision, current_price)
        elif signal == "hold":
            if coin not in positions:
                continue
            pos = positions[coin]
            raw_reason = str(decision.get("justification", "")).strip()
            if raw_reason:
                reason_text = " ".join(raw_reason.split())
                pos["last_justification"] = reason_text
            else:
                existing_reason = str(pos.get("last_justification", "")).strip()
                reason_text = existing_reason or "No justification provided."
                if not existing_reason:
                    pos["last_justification"] = reason_text
            try:
                quantity = float(pos.get("quantity", 0.0))
            except (TypeError, ValueError):
                quantity = 0.0
            try:
                fees_paid = float(pos.get("fees_paid", 0.0))
            except (TypeError, ValueError):
                fees_paid = 0.0
            try:
                entry_price = float(pos.get("entry_price", 0.0))
            except (TypeError, ValueError):
                entry_price = 0.0
            try:
                target_price = float(pos.get("profit_target", entry_price))
            except (TypeError, ValueError):
                target_price = entry_price
            try:
                stop_price = float(pos.get("stop_loss", entry_price))
            except (TypeError, ValueError):
                stop_price = entry_price
            leverage_display = format_leverage_display(pos.get("leverage", 1.0))
            try:
                margin_value = float(pos.get("margin", 0.0))
            except (TypeError, ValueError):
                margin_value = 0.0
            try:
                risk_value = float(pos.get("risk_usd", 0.0))
            except (TypeError, ValueError):
                risk_value = 0.0

            gross_unrealized = calculate_unrealized_pnl(coin, current_price)
            estimated_exit_fee_now = estimate_exit_fee(pos, current_price)
            total_fees_now = fees_paid + estimated_exit_fee_now
            net_unrealized = gross_unrealized - total_fees_now

            gross_at_target = calculate_pnl_for_price(pos, target_price)
            exit_fee_target = estimate_exit_fee(pos, target_price)
            net_at_target = gross_at_target - (fees_paid + exit_fee_target)

            gross_at_stop = calculate_pnl_for_price(pos, stop_price)
            exit_fee_stop = estimate_exit_fee(pos, stop_price)
            net_at_stop = gross_at_stop - (fees_paid + exit_fee_stop)

            expected_reward = max(gross_at_target, 0.0)
            expected_risk = max(-gross_at_stop, 0.0)
            if expected_risk > 0:
                rr_value = expected_reward / expected_risk if expected_reward > 0 else 0.0
                rr_display = f"{rr_value:.2f}:1"
            else:
                rr_display = "n/a"

            pnl_color = Fore.GREEN if net_unrealized >= 0 else Fore.RED
            gross_color = Fore.GREEN if gross_unrealized >= 0 else Fore.RED
            net_display = f"{net_unrealized:+.2f}"
            gross_display = f"{gross_unrealized:+.2f}"
            gross_target_display = f"{gross_at_target:+.2f}"
            gross_stop_display = f"{gross_at_stop:+.2f}"
            net_target_display = f"{net_at_target:+.2f}"
            net_stop_display = f"{net_at_stop:+.2f}"

            line = f"{Fore.BLUE}[HOLD] {coin} {pos['side'].upper()} {leverage_display}"
            print(line)
            record_iteration_message(line)
            line = f"  ├─ Size: {quantity:.4f} {coin} | Margin: ${margin_value:.2f}"
            print(line)
            record_iteration_message(line)
            line = f"  ├─ TP: ${target_price:.4f} | SL: ${stop_price:.4f}"
            print(line)
            record_iteration_message(line)
            line = (
                f"  ├─ PnL: {pnl_color}${net_display}{Style.RESET_ALL} "
                f"(Gross: {gross_color}${gross_display}{Style.RESET_ALL}, Fees: ${total_fees_now:.2f})"
            )
            print(line)
            record_iteration_message(line)
            line = (
                f"  ├─ PnL @ Target: ${gross_target_display} "
                f"(Net: ${net_target_display})"
            )
            print(line)
            record_iteration_message(line)
            line = (
                f"  ├─ PnL @ Stop: ${gross_stop_display} "
                f"(Net: ${net_stop_display})"
            )
            print(line)
            record_iteration_message(line)
            line = f"  ├─ Reward/Risk: {rr_display}"
            print(line)
            record_iteration_message(line)
            line = f"  └─ Reason: {reason_text}"
            print(line)
            record_iteration_message(line)

def check_stop_loss_take_profit() -> None:
    """Check and execute stop loss / take profit for all positions using intrabar extremes."""
    _check_sltp_for_positions(
        positions=positions,
        symbol_to_coin=SYMBOL_TO_COIN,
        fetch_market_data=fetch_market_data,
        execute_close=execute_close,
        hyperliquid_is_live=hyperliquid_trader.is_live,
    )

# ─────────────────────────── MAIN ──────────────────────────

def main() -> None:
    """Main trading loop."""
    global current_iteration_messages, iteration_counter
    logging.info("Initializing DeepSeek Multi-Asset Paper Trading Bot...")
    init_csv_files()
    load_equity_history()
    load_state()

    if not LLM_API_KEY:
        logging.error("No LLM API key configured; expected LLM_API_KEY or OPENROUTER_API_KEY in environment.")
        return

    logging.info(f"Starting capital: ${START_CAPITAL:.2f}")
    logging.info(f"Monitoring: {', '.join(SYMBOL_TO_COIN.values())}")
    if hyperliquid_trader.is_live:
        logging.warning(
            "Hyperliquid LIVE trading enabled. Orders will be sent to mainnet using wallet %s.",
            hyperliquid_trader.masked_wallet,
        )
    else:
        logging.info("Hyperliquid live trading disabled; running in paper mode only.")
    if TRADING_BACKEND == "binance_futures":
        if BINANCE_FUTURES_LIVE:
            logging.warning(
                "Binance futures LIVE trading enabled; orders will be sent to Binance USDT-margined futures.",
            )
        else:
            logging.warning(
                "TRADING_BACKEND=binance_futures but BINANCE_FUTURES_LIVE is not true; running in paper mode only.",
            )
    if TRADING_BACKEND == "backpack_futures":
        if BACKPACK_FUTURES_LIVE:
            logging.warning(
                "Backpack futures LIVE trading enabled; orders will be sent to Backpack USDC perpetual futures.",
            )
        else:
            logging.warning(
                "TRADING_BACKEND=backpack_futures but BACKPACK_FUTURES_LIVE is not true; running in paper mode only.",
            )
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        logging.info("Telegram notifications enabled (chat: %s).", TELEGRAM_CHAT_ID)
    else:
        logging.info("Telegram notifications disabled; missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
    log_system_prompt_info("System prompt selected")
    logging.info("LLM model configured: %s", LLM_MODEL_NAME)
    
    while True:
        try:
            iteration_counter += 1
            current_iteration_messages = []

            if not get_binance_client():
                retry_delay = min(CHECK_INTERVAL, 60)
                logging.warning(
                    "Binance client unavailable; retrying in %d seconds without exiting.",
                    retry_delay,
                )
                time.sleep(retry_delay)
                continue

            line = f"\n{Fore.CYAN}{'='*20}"
            print(line)
            record_iteration_message(line)
            current_dt = get_current_time()
            line = f"{Fore.CYAN}Iteration {iteration_counter} - {current_dt.strftime('%Y-%m-%d %H:%M:%S')}"
            print(line)
            record_iteration_message(line)
            line = f"{Fore.CYAN}{'='*20}\n"
            print(line)
            record_iteration_message(line)
            
            # Check stop loss / take profit first
            check_stop_loss_take_profit()
            
            # Get AI decisions
            logging.info("Requesting trading decisions from DeepSeek...")
            prompt = format_prompt_for_deepseek()
            decisions = call_deepseek_api(prompt)
            
            if not decisions:
                logging.warning("No decisions received from AI")
            else:
                process_ai_decisions(decisions)
            
            # Display portfolio summary
            total_equity = calculate_total_equity()
            total_return = ((total_equity - START_CAPITAL) / START_CAPITAL) * 100
            equity_color = Fore.GREEN if total_return >= 0 else Fore.RED
            total_margin = calculate_total_margin()
            net_unrealized_total = total_equity - balance - total_margin
            net_color = Fore.GREEN if net_unrealized_total >= 0 else Fore.RED
            register_equity_snapshot(total_equity)
            sortino_ratio = calculate_sortino_ratio(
                equity_history,
                CHECK_INTERVAL,
                RISK_FREE_RATE,
            )
            
            line = f"\n{Fore.YELLOW}{'─'*20}"
            print(line)
            record_iteration_message(line)
            line = f"{Fore.YELLOW}PORTFOLIO SUMMARY"
            print(line)
            record_iteration_message(line)
            line = f"{Fore.YELLOW}{'─'*20}"
            print(line)
            record_iteration_message(line)
            line = f"Available Balance: ${balance:.2f}"
            print(line)
            record_iteration_message(line)
            if total_margin > 0:
                line = f"Margin Allocated: ${total_margin:.2f}"
                print(line)
                record_iteration_message(line)
            line = f"Total Equity: {equity_color}${total_equity:.2f} ({total_return:+.2f}%){Style.RESET_ALL}"
            print(line)
            record_iteration_message(line)
            line = f"Unrealized PnL: {net_color}${net_unrealized_total:.2f}{Style.RESET_ALL}"
            print(line)
            record_iteration_message(line)
            if sortino_ratio is not None:
                sortino_color = Fore.GREEN if sortino_ratio >= 0 else Fore.RED
                line = f"Sortino Ratio: {sortino_color}{sortino_ratio:+.2f}{Style.RESET_ALL}"
            else:
                line = "Sortino Ratio: N/A (need more data)"
            print(line)
            record_iteration_message(line)
            line = f"Open Positions: {len(positions)}"
            print(line)
            record_iteration_message(line)
            line = f"{Fore.YELLOW}{'─'*20}\n"
            print(line)
            record_iteration_message(line)

            if current_iteration_messages:
                send_telegram_message("\n".join(current_iteration_messages), parse_mode=None)
            
            # Log state
            log_portfolio_state()
            save_state()
            
            # Wait for next check with visible console countdown
            logging.info(f"Waiting {CHECK_INTERVAL} seconds until next check...")
            sleep_with_countdown(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            print("\n\nShutting down bot...")
            save_state()
            break
        except Exception as e:
            logging.error(f"Error in main loop: {e}", exc_info=True)
            save_state()
            time.sleep(60)

if __name__ == "__main__":
    main()
