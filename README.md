# 3K Trading Bot

A Python research project for exploring Donchian channel breakouts on cryptocurrency candle data. It fetches OHLCV data with CCXT, calculates ATR and RSI, runs a simple historical simulation, and displays monitoring data in a local Flask dashboard.

**Project status:** Experimental. Backtests omit trading fees, slippage, and realistic order fills. Paper mode logs hypothetical signals; it does not maintain a simulated exchange account. Live order execution is intentionally disabled. Do not use this project to make real trades.

## What works

- Historical OHLCV retrieval through CCXT and a single-symbol backtest per configured pair.
- Donchian breakout signals against the **previous** candles, with ATR-based stop distance, RSI filtering, and risk-based hypothetical size.
- Continuous signal monitoring in paper mode, with a local dashboard at `http://localhost:5000`.
- Docker packaging and automated tests for channel timing, signal generation, backtest entry, and rejection of live mode.

## Run locally

Requires Python 3.9+.

```bash
git clone https://github.com/3kpro/3K_Trading_Bot_V2.git
cd 3K_Trading_Bot_V2
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest tests/ -q
python bot.py --backtest
python bot.py
```

Defaults: Kraken, SOL/USD, 1h candles, 1000 units of starting equity, 0.5% hypothetical risk per trade. Change the exchange, symbols, timeframe, and risk settings through environment variables:

```text
EXCHANGE=kraken
SYMBOLS=SOL/USD,BTC/USD
TIMEFRAME=1h
EQUITY=1000
RISK_FRAC=0.005
DONCHIAN_LOOKBACK=20
ATR_PERIOD=14
RSI_PERIOD=14
RSI_MIN=0
RSI_MAX=100
```

You can also override symbols, timeframe, equity, and risk fraction with `--symbols`, `--timeframe`, `--equity`, and `--risk-frac`. The `--live` option is reserved and raises an error; supplying exchange keys does not enable orders.

## How the strategy is evaluated

A close above the highest high of the preceding `DONCHIAN_LOOKBACK` candles indicates a long signal; a close below the preceding lowest low indicates a short signal. RSI must be within the configured range. The hypothetical stop is two ATR units from entry and position size is starting or current simulated equity times `RISK_FRAC`, divided by stop distance.

The backtest is deliberately simple: it enters and checks stop exits at candle closes, does not model fees or slippage, and does not establish whether the strategy is profitable. Results for multiple symbols are computed independently and their P&L is summed; they do not share a portfolio or capital constraint. Treat the output as a code experiment, not a performance claim.

## Contribute

Issues and pull requests are welcome. Good first contributions include realistic fill and fee modeling, persistent paper positions, stronger risk limits, and tests for short signals and edge cases. See [CONTRIBUTING.md](CONTRIBUTING.md). Never include API keys, account data, or private trading history in an issue.

## License

[MIT](LICENSE).
