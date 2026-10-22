from __future__ import annotations

import math
from typing import Any

from config import Config
from strategy import Decision


def _round_to_tick(price: float, tick_size: float, digits: int) -> float:
    if tick_size and tick_size > 0:
        price = round(price / tick_size) * tick_size
    return round(price, int(digits))


def build_setup(decision: Decision, m5, tick, meta, cfg: Config) -> dict[str, Any] | None:
    if not decision.direction:
        return None
    bid, ask = float(tick.bid), float(tick.ask)
    spread = ask - bid
    if not all(math.isfinite(x) and x > 0 for x in (bid, ask, spread)) or spread > cfg.max_spread:
        return None

    last = m5.iloc[-1]
    atr = float(last["atr"])
    entry = ask if decision.direction == "BUY" else bid
    risk_distance = atr * cfg.atr_stop_multiplier
    if not all(math.isfinite(x) and x > 0 for x in (entry, atr, risk_distance)):
        return None
    # Prevent stops that are implausibly tight or wide compared with ATR.
    if risk_distance < atr * 0.5 or risk_distance > atr * 5.0:
        return None

    if decision.direction == "BUY":
        sl, tp = entry - risk_distance, entry + risk_distance * cfg.min_reward_risk
    else:
        sl, tp = entry + risk_distance, entry - risk_distance * cfg.min_reward_risk

    digits = int(meta.digits)
    tick_size = float(getattr(meta, "trade_tick_size", 0.0) or getattr(meta, "point", 0.0) or 0.0)
    entry = _round_to_tick(entry, tick_size, digits)
    sl = _round_to_tick(sl, tick_size, digits)
    tp = _round_to_tick(tp, tick_size, digits)

    actual_risk = abs(entry - sl)
    reward = abs(tp - entry)
    if actual_risk <= 0 or reward / actual_risk + 1e-9 < cfg.min_reward_risk:
        return None
    if decision.direction == "BUY" and not (sl < entry < tp):
        return None
    if decision.direction == "SELL" and not (tp < entry < sl):
        return None

    return {
        "timestamp_utc": last["time"].isoformat(),
        "signal_candle_time": decision.signal_candle_time or last["time"].isoformat(),
        "direction": decision.direction,
        "entry": entry,
        "stop_loss": sl,
        "take_profit": tp,
        "reward_risk": round(reward / actual_risk, 2),
        "spread": round(spread, digits),
        "atr": round(atr, digits),
        "reason": decision.reason,
        "bid": bid,
        "ask": ask,
        "symbol_digits": digits,
    }
