# 3K Trading Bot V2.1

[![CI](https://github.com/3kpro/3K_Trading_Bot_V2/actions/workflows/ci.yml/badge.svg)](https://github.com/3kpro/3K_Trading_Bot_V2/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

A professional-grade cryptocurrency trading bot implementing a Donchian channel breakout strategy with ATR-based stops, RSI regime filtering, and comprehensive risk management. Supports backtesting, paper trading, live trading, multi-symbol operations, and a real-time web dashboard.

## 🚀 Features

- **Strategy**: Donchian breakout with ATR stops and RSI filter
- **Backtesting**: Parameter optimization and walk-forward analysis
- **Performance Analytics**: Win rate, profit factor, and drawdown metrics for each backtest run
- **Trading Modes**: Paper (simulation), Live (real money)
- **Risk Management**: Position sizing, circuit breakers, drawdown control
- **Multi-Symbol**: Trade multiple pairs simultaneously
- **Web Dashboard**: Real-time monitoring with charts and readiness score
- **Logging & Notifications**: Structured logging and Telegram alerts
- **Docker Support**: Containerized deployment
- **Type Safety**: Full type hints for reliability

## 📊 Architecture

```
3K_Trading_Bot_V2/
├── bot.py              # CLI entry point & main loop
├── config.py           # Configuration management
├── data.py             # Data fetching & indicators
├── strategy.py         # Signal generation logic
├── execution.py        # Order routing & position tracking
├── risk.py             # Sizing & risk controls
├── report.py           # Performance reporting
├── status.py           # Health checks
├── targets.py          # Symbol watchlists
├── watch_targets.py    # Alert monitoring
├── requirements.txt
├── Dockerfile
├── tests/              # Unit & integration tests
└── reports/            # Generated reports & logs
```

## 🛠️ Requirements

- Python 3.9+
- Dependencies: `pip install -r requirements.txt`

## ⚙️ Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/3kpro/3K_Trading_Bot_V2.git
   cd 3K_Trading_Bot_V2
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   Create a `.env` file or set environment variables:
   ```env
   EXCHANGE=kraken
   SYMBOLS=BTC/USDT,ETH/USDT
   TIMEFRAME=1h
   EQUITY=1000
   RISK_FRAC=0.005
   API_KEY=your_api_key
   API_SECRET=your_api_secret
   TELEGRAM_BOT_TOKEN=your_bot_token
   TELEGRAM_CHAT_ID=your_chat_id
   ```

## 🎯 Usage

### Backtesting
```bash
# Basic backtest
python bot.py --backtest

# With walk-forward analysis
python bot.py --backtest --walkforward

# Override parameters
python bot.py --backtest --symbols BTC/USDT --timeframe 4h
```

### Paper Trading (Simulation)
```bash
python bot.py
```

### Live Trading
```bash
python bot.py --live
```

### Web Dashboard
Start the bot and visit `http://localhost:5000` for real-time monitoring.

## 📈 Strategy Details

- **Entry**: Close breaks above/below Donchian channel (20-period)
- **Filter**: RSI between 35-70
- **Stop Loss**: 2x ATR from entry
- **Position Sizing**: Risk 0.5% of equity per trade
- **Exit**: Stop hit or opposite breakout

## 🐳 Docker

```bash
# Build
docker build -t 3k-trading-bot .

# Run paper trading
docker run --env-file .env 3k-trading-bot

# Run live trading
docker run --env-file .env 3k-trading-bot python bot.py --live
```

## 🧪 Testing

```bash
pytest tests/
```

## 📊 Monitoring

- **Dashboard**: Real-time equity chart, position status, trade history
- **Readiness Score**: Checklist for live trading readiness
- **Logs**: Structured logging to console and files
- **Telegram**: Trade notifications and alerts

## ⚠️ Disclaimer

This software is for educational and research purposes only. Trading cryptocurrencies involves substantial risk of loss and is not suitable for all investors. Past performance does not guarantee future results. Use at your own risk.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details.