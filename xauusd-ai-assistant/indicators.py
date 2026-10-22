from __future__ import annotations

import numpy as np
import pandas as pd


def add_indicators(df: pd.DataFrame, fast_period: int, slow_period: int, atr_period: int) -> pd.DataFrame:
    out = df.copy()
    close = out["close"].astype(float)
    out["ema_fast"] = close.ewm(span=fast_period, adjust=False, min_periods=fast_period).mean()
    out["ema_slow"] = close.ewm(span=slow_period, adjust=False, min_periods=slow_period).mean()
    prev_close = close.shift(1)
    true_range = pd.concat([
        out["high"] - out["low"],
        (out["high"] - prev_close).abs(),
        (out["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    out["atr"] = true_range.rolling(atr_period, min_periods=atr_period).mean()
    required = out[["ema_fast", "ema_slow", "atr"]].iloc[-1]
    if required.isna().any() or not np.isfinite(required.to_numpy(dtype=float)).all():
        raise ValueError("Indicator values are unavailable or invalid.")
    return out
