from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import MetaTrader5 as mt5
import pandas as pd

from config import Config

log = logging.getLogger(__name__)


class MarketDataError(RuntimeError):
    pass


_TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
}

_TIMEFRAME_SECONDS = {
    "M1": 60,
    "M5": 5 * 60,
    "M15": 15 * 60,
    "M30": 30 * 60,
    "H1": 60 * 60,
    "H4": 4 * 60 * 60,
}

_OFFSET_STEP_SECONDS = 1800          # offsets are multiples of 30 minutes
_OFFSET_MAX_RESIDUAL_SECONDS = 90    # tick must be this close to a clean offset to count as "live"
_OFFSET_MAX_ABS_SECONDS = 14 * 3600
_OFFSET_CONFIRMATIONS = 2            # consecutive agreeing samples needed to change a known offset
_FUTURE_TOLERANCE_SECONDS = 120


class MT5Client:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.connected = False
        self._offset_seconds: int | None = None
        self._pending_offset: int | None = None
        self._pending_count = 0
        self._last_tick_time: int | None = None

    def connect_and_validate_demo(self) -> None:
        kwargs: dict[str, Any] = {}
        if self.cfg.mt5_terminal_path:
            kwargs["path"] = self.cfg.mt5_terminal_path
        if not mt5.initialize(**kwargs):
            raise MarketDataError(f"Could not connect to MT5 terminal: {mt5.last_error()}. Open MT5 and sign in first.")
        self.connected = True
        account = mt5.account_info()
        if account is None:
            self.shutdown()
            raise MarketDataError(f"MT5 account information unavailable: {mt5.last_error()}")
        demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
        if account.trade_mode != demo_mode:
            self.shutdown()
            raise MarketDataError(
                "Safety stop: the connected MT5 account does not report DEMO mode. "
                "Confirm the account is a demo account in MT5, then restart."
            )
        log.info("Connected to MT5 terminal; demo mode confirmed. Account number is not logged.")

    def resolve_symbol(self) -> str:
        requested = self.cfg.mt5_symbol
        info = mt5.symbol_info(requested)
        if info is not None:
            if not info.visible and not mt5.symbol_select(requested, True):
                raise MarketDataError(f"Symbol {requested} exists but could not be selected.")
            return requested

        candidates = mt5.symbols_get()
        if candidates is None:
            raise MarketDataError(f"Could not list broker symbols: {mt5.last_error()}")
        names = [item.name for item in candidates]
        exact_base = [n for n in names if n.upper() == "XAUUSD"]
        suffix_matches = [n for n in names if n.upper().startswith("XAUUSD")]
        matches = exact_base or suffix_matches
        if len(matches) != 1:
            if self.cfg.mt5_symbol.upper() != "XAUUSD" and self.cfg.mt5_symbol not in names:
                raise MarketDataError(
                    f"Configured symbol {requested!r} was not found. Set MT5_SYMBOL to the exact broker symbol."
                )
            raise MarketDataError(
                "Could not identify one unambiguous XAUUSD symbol. Set MT5_SYMBOL to the exact name shown in MT5 Market Watch."
            )
        symbol = matches[0]
        if not mt5.symbol_select(symbol, True):
            raise MarketDataError(f"Could not select symbol {symbol}: {mt5.last_error()}")
        log.info("Using broker symbol %s", symbol)
        return symbol

    # ------------------------------------------------------------------
    # Broker server time -> UTC offset handling
    # ------------------------------------------------------------------
    def _fallback_offset_seconds(self) -> int | None:
        hours = getattr(self.cfg, "broker_utc_offset_hours", None)
        return None if hours is None else int(round(float(hours) * 3600))

    def _set_offset(self, seconds: int, source: str) -> None:
        if seconds != self._offset_seconds:
            log.warning("Broker server UTC offset set to %+.1f hours (%s).", seconds / 3600, source)
        self._offset_seconds = seconds
        self._pending_offset = None
        self._pending_count = 0

    def _sample_offset(self, symbol: str) -> tuple[int, bool] | None:
        """Return (candidate_offset_seconds, tick_advanced) or None if the tick doesn't look live."""
        tick = mt5.symbol_info_tick(symbol)
        if tick is None or tick.time <= 0:
            return None
        tick_time = int(tick.time)
        raw_diff = tick_time - time.time()
        candidate = int(round(raw_diff / _OFFSET_STEP_SECONDS)) * _OFFSET_STEP_SECONDS
        residual = abs(raw_diff - candidate)
        advanced = self._last_tick_time is not None and tick_time != self._last_tick_time
        self._last_tick_time = tick_time
        if residual > _OFFSET_MAX_RESIDUAL_SECONDS or abs(candidate) > _OFFSET_MAX_ABS_SECONDS:
            return None
        return candidate, advanced

    def refresh_utc_offset(self, symbol: str) -> None:
        sample = self._sample_offset(symbol)

        # First run: accept a clean sample, else fall back to config, else stop.
        if self._offset_seconds is None:
            if sample is not None:
                self._set_offset(sample[0], "auto-detected")
                return
            fallback = self._fallback_offset_seconds()
            if fallback is None:
                raise MarketDataError(
                    "Cannot determine broker UTC offset (market may be closed). "
                    "Set BROKER_UTC_OFFSET_HOURS in .env or retry when the market is open."
                )
            self._set_offset(fallback, "config fallback")
            return

        # Already known: only change it after repeated agreement from a *moving* tick.
        if sample is None or not sample[1] or sample[0] == self._offset_seconds:
            self._pending_offset, self._pending_count = None, 0
            return
        candidate = sample[0]
        if candidate == self._pending_offset:
            self._pending_count += 1
        else:
            self._pending_offset, self._pending_count = candidate, 1
        if self._pending_count >= _OFFSET_CONFIRMATIONS:
            self._set_offset(candidate, "auto-detected change")

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------
    def _rates(self, symbol: str, timeframe_name: str, count: int) -> pd.DataFrame:
        if timeframe_name not in _TIMEFRAMES:
            raise MarketDataError(f"Unsupported timeframe {timeframe_name!r}; use M1, M5, M15, M30, H1, or H4.")
        required_count = self.cfg.ema_slow + self.cfg.atr_period + 5
        fetch_count = max(count, required_count) + 2
        rates = mt5.copy_rates_from_pos(symbol, _TIMEFRAMES[timeframe_name], 0, fetch_count)
        if rates is None or len(rates) == 0:
            raise MarketDataError(f"{timeframe_name} market data unavailable: {mt5.last_error()}")

        current_unix_time = time.time()
        current_utc = datetime.fromtimestamp(current_unix_time, timezone.utc)
        if "time" not in rates.dtype.names:
            raise MarketDataError(f"{timeframe_name} market data has no candle timestamps.")
        raw_timestamps = rates["time"]
        raw_latest_timestamp = max(raw_timestamps)
        log.info(
            "Raw MT5 %s timestamps: latest=%r; current Unix timestamp=%.3f (%s UTC)",
            timeframe_name,
            raw_latest_timestamp,
            current_unix_time,
            current_utc.isoformat(),
        )

        df = pd.DataFrame(rates)
        df["time_unix"] = pd.to_numeric(df["time"], errors="coerce")
        if df["time_unix"].isna().any():
            raise MarketDataError(f"{timeframe_name} market data contains invalid candle timestamps.")
        if self._offset_seconds is None:
            raise MarketDataError("Broker UTC offset not initialised.")
        df["time_unix"] = df["time_unix"].astype("int64") - self._offset_seconds

        latest_available_timestamp = int(df["time_unix"].max())
        if latest_available_timestamp > current_unix_time + _FUTURE_TOLERANCE_SECONDS:
            future_timestamp = datetime.fromtimestamp(latest_available_timestamp, timezone.utc).isoformat()
            raise MarketDataError(
                f"{timeframe_name} market data timestamp is in the future after applying broker offset "
                f"{self._offset_seconds / 3600:+.1f}h (converted UTC={future_timestamp}, "
                f"current UTC={current_utc.isoformat()}). Check the system clock or BROKER_UTC_OFFSET_HOURS."
            )

        timeframe_seconds = _TIMEFRAME_SECONDS[timeframe_name]
        current_candle_start = int(current_unix_time // timeframe_seconds) * timeframe_seconds
        completed = df[df["time_unix"] < current_candle_start]
        if len(completed) < required_count:
            raise MarketDataError(
                f"Insufficient completed {timeframe_name} candle history: "
                f"got {len(completed)}, need {required_count}."
            )

        df = (
            completed.sort_values("time_unix")
            .drop_duplicates(subset=["time_unix"])
            .tail(count)
            .reset_index(drop=True)
        )
        cols = ["open", "high", "low", "close", "tick_volume"]
        if df[cols].isna().any().any():
            raise MarketDataError(f"{timeframe_name} candle data contains missing values.")
        if (df["high"] < df["low"]).any() or (df[["open", "high", "low", "close"]] <= 0).any().any():
            raise MarketDataError(f"{timeframe_name} candle data contains invalid prices.")

        latest_timestamp = int(df["time_unix"].iloc[-1])
        candle_age_minutes = (current_unix_time - latest_timestamp) / 60
        latest_utc = datetime.fromtimestamp(latest_timestamp, timezone.utc)
        log.info(
            "Latest completed %s candle raw timestamp=%r; converted UTC=%s; current UTC=%s; age=%.1f minutes",
            timeframe_name,
            latest_timestamp,
            latest_utc.isoformat(),
            current_utc.isoformat(),
            candle_age_minutes,
        )
        if candle_age_minutes < -_FUTURE_TOLERANCE_SECONDS / 60:
            raise MarketDataError(
                f"Latest completed {timeframe_name} candle timestamp is in the future "
                f"(converted UTC={latest_utc.isoformat()}, "
                f"current UTC={current_utc.isoformat()}, broker offset {self._offset_seconds / 3600:+.1f}h)."
            )

        df["time"] = pd.to_datetime(df["time_unix"], unit="s", utc=True)
        df = df.drop(columns=["time_unix"])
        allowed_age = self.cfg.max_candle_age_minutes * (3 if timeframe_name == "M15" else 1)
        if candle_age_minutes > allowed_age:
            raise MarketDataError(
                f"Latest completed {timeframe_name} candle is stale ({candle_age_minutes:.1f} minutes old)."
            )
        return df

    def get_market_snapshot(self, symbol: str):
        if not mt5.terminal_info():
            if not mt5.initialize(path=self.cfg.mt5_terminal_path or None):
                raise MarketDataError(f"MT5 reconnect failed: {mt5.last_error()}")
        self.refresh_utc_offset(symbol)
        m5 = self._rates(symbol, self.cfg.timeframe_entry, self.cfg.candle_history)
        m15 = self._rates(symbol, self.cfg.timeframe_trend, self.cfg.candle_history)
        tick = mt5.symbol_info_tick(symbol)
        meta = mt5.symbol_info(symbol)
        if tick is None or meta is None or tick.bid <= 0 or tick.ask <= 0 or tick.ask < tick.bid:
            raise MarketDataError(f"Invalid current tick or symbol metadata: {mt5.last_error()}")
        return m5, m15, tick, meta

    def shutdown(self) -> None:
        if self.connected:
            mt5.shutdown()
            self.connected = False