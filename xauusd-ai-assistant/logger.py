from __future__ import annotations

import csv
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"
CSV_PATH = LOG_DIR / "signals.csv"
FIELDS = [
    "recorded_at_utc", "status", "timestamp_utc", "symbol", "direction",
    "entry", "stop_loss", "take_profit", "reward_risk", "spread", "atr", "reason",
]


def setup_logging(level: str = "INFO") -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_DIR / "assistant.log", encoding="utf-8"),
        ],
    )


def write_signal_record(data: dict, status: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        **data,
    }
    exists = CSV_PATH.exists() and CSV_PATH.stat().st_size > 0
    with CSV_PATH.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow({key: row.get(key, "") for key in FIELDS})
