# Trading Bot

A cryptocurrency trading bot using Donchian breakout strategy with ATR stops, RSI filter, and ML augmentation. Supports backtesting, paper/live trading, multi-symbol, and web dashboard.

## Features

- Donchian channel breakout strategy
- ATR-based stops and position sizing
- RSI regime filter
- ML signal augmentation with RandomForest
- Multi-symbol support
- Risk management with dynamic sizing and circuit breakers
- Parameter optimization and walk-forward backtesting
- Web dashboard for monitoring
- Telegram notifications
- Encrypted key storage with keyring
- Docker containerization

## Requirements

- Python 3.9+
- See requirements.txt for packages

## Installation

1. Clone the repo
2. Install dependencies: `pip install -r requirements.txt`
3. Set environment variables or use keyring for keys

## Configuration

Set the following in .env or via keyring:

- EXCHANGE: e.g., kraken
- SYMBOLS: comma-separated, e.g., SOL/USD,BTC/USD
- TIMEFRAME: e.g., 1h
- RISK_FRAC: e.g., 0.005
- EQUITY: e.g., 1000
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

For keyring: `python -c "import keyring; keyring.set_password('trading_bot', 'api_key', 'your_key')"`

## Usage

### Backtest
`python bot.py --backtest`

With walk-forward: `python bot.py --backtest --walkforward`

### Paper Trading
`python bot.py`

### Live Trading
`python bot.py --live`

### Web Dashboard
Access http://localhost:5000 after starting the bot.

## Docker

Build: `docker build -t trading-bot .`

Run: `docker run --env-file .env trading-bot python bot.py --live`

## Disclaimer

This is for educational purposes. Trading involves risk. Use at your own risk.