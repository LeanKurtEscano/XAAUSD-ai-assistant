from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv


def _int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}.")
    return value


def _float(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number.") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}.")
    return value


def _optional_float(name: str, minimum: float, maximum: float) -> float | None:
    """Return None when the variable is unset or blank; otherwise a validated float."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number.") from exc
    if not (minimum <= value <= maximum):
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


@dataclass(frozen=True)
class Config:
    mt5_terminal_path: str
    mt5_symbol: str
    telegram_bot_token: str
    telegram_chat_id: str
    telegram_enabled: bool
    timeframe_entry: str
    timeframe_trend: str
    ema_fast: int
    ema_slow: int
    atr_period: int
    atr_stop_multiplier: float
    min_reward_risk: float
    max_spread: float
    monitor_interval_seconds: int
    candle_history: int
    max_candle_age_minutes: int
    enable_status_alerts: bool
    log_level: str
    pullback_atr_tolerance: float
    # Fallback only: used when the broker offset cannot be auto-detected (e.g. market closed at startup).
    broker_utc_offset_hours: float | None = None


def load_config() -> Config:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    enabled = os.getenv("TELEGRAM_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    if enabled and (not token or not chat_id):
        raise ValueError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env, or set TELEGRAM_ENABLED=false.")
    fast = _int("EMA_FAST", 20)
    slow = _int("EMA_SLOW", 50)
    if fast >= slow:
        raise ValueError("EMA_FAST must be lower than EMA_SLOW.")
    return Config(
        mt5_terminal_path=os.getenv("MT5_TERMINAL_PATH", "").strip(),
        mt5_symbol=os.getenv("MT5_SYMBOL", "XAUUSD").strip(),
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        telegram_enabled=enabled,
        timeframe_entry=os.getenv("TIMEFRAME_ENTRY", "M5").strip().upper(),
        timeframe_trend=os.getenv("TIMEFRAME_TREND", "M15").strip().upper(),
        ema_fast=fast,
        ema_slow=slow,
        atr_period=_int("ATR_PERIOD", 14),
        atr_stop_multiplier=_float("ATR_STOP_MULTIPLIER", 1.5, 0.1),
        min_reward_risk=_float("MIN_REWARD_RISK", 1.5, 0.1),
        max_spread=_float("MAX_SPREAD", 0.50, 0.0),
        monitor_interval_seconds=_int("MONITOR_INTERVAL_SECONDS", 15),
        candle_history=max(_int("CANDLE_HISTORY", 250), slow + 30),
        max_candle_age_minutes=_int("MAX_CANDLE_AGE_MINUTES", 10),
        enable_status_alerts=os.getenv("ENABLE_STATUS_ALERTS", "false").strip().lower() in {"1", "true", "yes", "on"},
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        pullback_atr_tolerance=_float("PULLBACK_ATR_TOLERANCE", 0.25, 0.01),
        broker_utc_offset_hours=_optional_float("BROKER_UTC_OFFSET_HOURS", -14.0, 14.0),
    )