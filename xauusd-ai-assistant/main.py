from __future__ import annotations

import logging
import signal
import time
from datetime import datetime, timezone

import MetaTrader5 as mt5

from config import load_config
from indicators import add_indicators
from logger import setup_logging, write_signal_record
from mt5_client import MT5Client, MarketDataError
from risk_manager import build_setup
from strategy import evaluate_setup
from telegram_bot import TelegramAlerter


def run() -> None:
    cfg = load_config()
    setup_logging(cfg.log_level)
    log = logging.getLogger("main")
    stop_requested = False

    def request_stop(*_args) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    client = MT5Client(cfg)
    alerter = TelegramAlerter(cfg)
    last_signal_key = None
    last_status_message = 0.0

    try:
        client.connect_and_validate_demo()
        symbol = client.resolve_symbol()
        log.info("Read-only monitoring started for %s. No orders will be submitted.", symbol)

        while not stop_requested:
            try:
                m5, m15, tick, meta = client.get_market_snapshot(symbol)
                m5 = add_indicators(m5, cfg.ema_fast, cfg.ema_slow, cfg.atr_period)
                m15 = add_indicators(m15, cfg.ema_fast, cfg.ema_slow, cfg.atr_period)

                decision = evaluate_setup(m5, m15, cfg)
                now = datetime.now(timezone.utc)

                if decision.direction:
                    setup = build_setup(
                        decision=decision,
                        m5=m5,
                        tick=tick,
                        meta=meta,
                        cfg=cfg,
                    )
                    if setup:
                        key = f"{symbol}|{setup['direction']}|{setup['signal_candle_time']}"
                        if key != last_signal_key:
                            write_signal_record(setup, "SIGNAL")
                            message = alerter.format_signal(symbol, setup)
                            if alerter.enabled:
                                alerter.send(message)
                            log.info("New potential %s setup created for %s", setup["direction"], symbol)
                            last_signal_key = key
                        else:
                            log.info("Duplicate setup suppressed: %s", key)
                    else:
                        write_signal_record({
                            "timestamp_utc": now.isoformat(),
                            "symbol": symbol,
                            "direction": decision.direction,
                            "reason": "Risk/price validation rejected the setup",
                        }, "REJECTED")
                else:
                    log.info("NO TRADE: %s", decision.reason)
                    write_signal_record({
                        "timestamp_utc": now.isoformat(),
                        "symbol": symbol,
                        "direction": "",
                        "reason": decision.reason,
                    }, "NO_TRADE")

                if cfg.enable_status_alerts and alerter.enabled and time.time() - last_status_message >= 3600:
                    alerter.send(f"XAUUSD alert assistant is running. Latest evaluation: {decision.reason}\nNo trades are placed automatically.")
                    last_status_message = time.time()

            except (MarketDataError, ValueError, RuntimeError) as exc:
                log.warning("Monitoring cycle skipped safely: %s", exc)
                write_signal_record({
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "symbol": cfg.mt5_symbol,
                    "direction": "",
                    "reason": str(exc),
                }, "ERROR")
            except Exception:
                log.exception("Unexpected monitoring error; will retry next cycle.")

            for _ in range(max(1, cfg.monitor_interval_seconds)):
                if stop_requested:
                    break
                time.sleep(1)

    finally:
        client.shutdown()
        log.info("Application stopped. MT5 connection released; no trades were placed.")


if __name__ == "__main__":
    run()
