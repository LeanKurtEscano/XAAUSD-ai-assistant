
from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from config import Config


@dataclass(frozen=True)
class Decision:
    direction: str | None
    reason: str
    signal_candle_time: str | None = None


def evaluate_setup(m5: pd.DataFrame, m15: pd.DataFrame, cfg: Config) -> Decision:
    """Evaluate a pullback-and-continuation setup using completed candles."""

    if len(m5) < 3 or len(m15) < 2:
        return Decision(None, "Insufficient completed candles.")

    required = {"open", "high", "low", "close", "ema_fast", "ema_slow", "atr"}
    if not required.issubset(m5.columns) or not required.issubset(m15.columns):
        return Decision(None, "Required OHLC or indicator columns are missing.")

    # Validate the candles and indicators used by this decision.
    trend = m15.iloc[-1]
    pullback = m5.iloc[-2]
    confirm = m5.iloc[-1]

    def valid_number(value: object) -> bool:
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError):
            return False

    m15_values = [trend["close"], trend["ema_fast"], trend["ema_slow"]]
    m5_values = [
        pullback["open"],
        pullback["high"],
        pullback["low"],
        pullback["close"],
        pullback["ema_fast"],
        confirm["open"],
        confirm["high"],
        confirm["low"],
        confirm["close"],
        confirm["ema_fast"],
        confirm["ema_slow"],
        confirm["atr"],
    ]

    if not all(valid_number(v) for v in m15_values + m5_values):
        return Decision(None, "Invalid or non-finite price/indicator data.")

    if any(float(row["close"]) <= 0 for _, row in m5.iloc[-2:].iterrows()):
        return Decision(None, "Invalid candle close price.")

    if (
        float(pullback["high"]) < float(pullback["low"])
        or float(confirm["high"]) < float(confirm["low"])
        or float(confirm["atr"]) <= 0
    ):
        return Decision(None, "Invalid candle range or ATR.")

    # Determine the higher-timeframe direction.
    if trend["ema_fast"] > trend["ema_slow"] and trend["close"] > trend["ema_slow"]:
        trend_direction = "BUY"
    elif trend["ema_fast"] < trend["ema_slow"] and trend["close"] < trend["ema_slow"]:
        trend_direction = "SELL"
    else:
        return Decision(None, "M15 trend is unclear or conflicting.")

    atr = float(confirm["atr"])
    tolerance = atr * cfg.pullback_atr_tolerance

    p_high = float(pullback["high"])
    p_low = float(pullback["low"])
    p_ema = float(pullback["ema_fast"])

    c_open = float(confirm["open"])
    c_high = float(confirm["high"])
    c_low = float(confirm["low"])
    c_close = float(confirm["close"])
    c_ema_fast = float(confirm["ema_fast"])
    c_ema_slow = float(confirm["ema_slow"])

    if c_high < c_low or c_close < c_low or c_close > c_high:
        return Decision(None, "Confirmation candle has an invalid OHLC range.")

    if tolerance < 0 or not math.isfinite(tolerance):
        return Decision(None, "Invalid pullback tolerance.")

    # Require the pullback candle's range to intersect the EMA20
    # tolerance band. This avoids accepting arbitrarily deep pullbacks.
    band_low = p_ema - tolerance
    band_high = p_ema + tolerance
    touched = p_low <= band_high and p_high >= band_low

    signal_time = confirm["time"].isoformat() if "time" in confirm.index else None

    if trend_direction == "BUY":
        aligned = c_ema_fast > c_ema_slow
        bullish_candle = c_close > c_open
        breaks_pullback = c_close > p_high
        above_ema = c_close > c_ema_fast

        if aligned and touched and bullish_candle and breaks_pullback and above_ema:
            return Decision(
                "BUY",
                "M15 bullish; M5 EMA alignment, pullback into EMA20 tolerance band, "
                "and bullish close above pullback high confirmed.",
                signal_time,
            )

        failed = []
        if not aligned:
            failed.append("M5 EMA fast is not above EMA slow")
        if not touched:
            failed.append(
                f"pullback range {p_low:.2f}-{p_high:.2f} does not overlap "
                f"EMA20 tolerance band {band_low:.2f}-{band_high:.2f}"
            )
        if not bullish_candle:
            failed.append("confirmation candle is not bullish")
        if not breaks_pullback:
            failed.append(f"close {c_close:.2f} is not above pullback high {p_high:.2f}")
        if not above_ema:
            failed.append(f"close {c_close:.2f} is not above EMA20 {c_ema_fast:.2f}")

        return Decision(None, "M15 bullish, no BUY setup: " + "; ".join(failed) + ".")

    aligned = c_ema_fast < c_ema_slow
    bearish_candle = c_close < c_open
    breaks_pullback = c_close < p_low
    below_ema = c_close < c_ema_fast

    if aligned and touched and bearish_candle and breaks_pullback and below_ema:
        return Decision(
            "SELL",
            "M15 bearish; M5 EMA alignment, pullback into EMA20 tolerance band, "
            "and bearish close below pullback low confirmed.",
            signal_time,
        )

    failed = []
    if not aligned:
        failed.append("M5 EMA fast is not below EMA slow")
    if not touched:
        failed.append(
            f"pullback range {p_low:.2f}-{p_high:.2f} does not overlap "
            f"EMA20 tolerance band {band_low:.2f}-{band_high:.2f}"
        )
    if not bearish_candle:
        failed.append("confirmation candle is not bearish")
    if not breaks_pullback:
        failed.append(f"close {c_close:.2f} is not below pullback low {p_low:.2f}")
    if not below_ema:
        failed.append(f"close {c_close:.2f} is not below EMA20 {c_ema_fast:.2f}")

    return Decision(None, "M15 bearish, no SELL setup: " + "; ".join(failed) + ".")
