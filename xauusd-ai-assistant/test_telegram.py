from config import load_config
from telegram_bot import TelegramAlerter

cfg = load_config()
alerter = TelegramAlerter(cfg)
print("Alerter enabled:", alerter.enabled)
alerter.send("Test message from the XAUUSD alert assistant.")
print("Done. Check Telegram.")