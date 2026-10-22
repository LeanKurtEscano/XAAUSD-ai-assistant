# XAUUSD AI Scalping Alert Assistant

A read-only XAUUSD market-analysis assistant for Windows. It reads completed candles from your already-open MetaTrader 5 desktop terminal, evaluates a configurable EMA/ATR pullback strategy, and sends potential setups to Telegram.

**Manual trading only:** this application does not place, modify, or close orders. It does not call `mt5.order_send()` or use UI automation. BUY/SELL labels indicate potential setups only.

## Requirements

- Windows with MetaTrader 5 desktop installed and signed in to a **demo account**
- Python 3.10+ (64-bit Python is recommended to match MT5)
- VS Code / PowerShell
- A Telegram bot and your chat ID if alerts are enabled

## Setup in VS Code PowerShell

```powershell
cd path\to\xauusd-ai-assistant
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` and set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. To run without Telegram while configuring the app, set `TELEGRAM_ENABLED=false`.

Keep your normal MT5 desktop terminal open and logged in to the demo account. If automatic terminal discovery fails, set `MT5_TERMINAL_PATH` to the exact path of `terminal64.exe`, for example `C:\Program Files\MetaTrader 5\terminal64.exe`.

Set `MT5_SYMBOL` to the exact gold symbol shown in Market Watch if your broker uses a suffix such as `XAUUSD.a`.

## Start

```powershell
python main.py
```

Stop with `Ctrl+C`. Logs are written to `logs\assistant.log` and `logs\signals.csv`.

## Strategy summary

- M15 trend: EMA 20 above EMA 50 and close above EMA 50 for potential BUY; inverse for SELL.
- M5 setup: EMA alignment, previous completed candle pulls back toward EMA 20 within a configurable ATR tolerance, and latest completed candle closes in the trend direction beyond the previous candle's high/low.
- Stop-loss distance: 1.5 × ATR by default; take-profit uses the configured minimum reward-to-risk ratio.
- Signals are rejected if market data is stale/invalid, spread is too wide, or price/risk validation fails.

These parameters are starting hypotheses, not evidence of profitability. Alerts are not financial advice. Check every setup independently before making a manual trading decision.

## Safety notes

- The program checks that the connected account reports demo mode and stops otherwise.
- It only requests account metadata, symbol information, ticks, and candle history.
- There is no order-execution code. Do not add trade-execution functionality to this project.
- Indicative prices may move before you manually act. Broker spreads, execution, slippage, and symbol specifications can affect outcomes.
