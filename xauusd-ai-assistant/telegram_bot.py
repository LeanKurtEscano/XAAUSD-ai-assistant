from __future__ import annotations

import logging
import time
import requests

from config import Config

log = logging.getLogger(__name__)


class TelegramAlerter:
    def __init__(self, cfg: Config) -> None:
        self.token = cfg.telegram_bot_token
        self.chat_id = cfg.telegram_chat_id
        self.enabled = cfg.telegram_enabled

    def format_signal(self, symbol: str, setup: dict) -> str:
        return (
            f"POTENTIAL {setup['direction']} — {symbol}\n\n"
            f"Timeframe: M5\n"
            f"Trend confirmation: M15 {'bullish' if setup['direction'] == 'BUY' else 'bearish'}\n"
            f"Indicative entry: {setup['entry']}\n"
            f"Indicative stop-loss: {setup['stop_loss']}\n"
            f"Indicative take-profit: {setup['take_profit']}\n"
            f"Reward-to-risk: {setup['reward_risk']}:1\n"
            f"Spread: {setup['spread']}\n"
            f"ATR: {setup['atr']}\n\n"
            f"Reason: {setup['reason']}\n\n"
            "Manual execution only. No trade has been placed. "
            "Levels are indicative and may differ from your eventual execution price."
        )

    def send(self, message: str) -> bool:
        if not self.enabled:
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        for attempt in range(3):
            try:
                response = requests.post(
                    url,
                    json={"chat_id": self.chat_id, "text": message},
                    timeout=10,
                )
                if response.ok and response.json().get("ok") is True:
                    return True
                log.warning("Telegram rejected message (HTTP %s).", response.status_code)
            except requests.RequestException as exc:
                log.warning("Telegram send attempt %s failed: %s", attempt + 1, exc)
            time.sleep(1.5 * (attempt + 1))
        log.error("Telegram alert could not be delivered after retries.")
        return False
