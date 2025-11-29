#!/usr/bin/env python3
"""
3K Trading Bot V2.1 – Core Runner

Donchian breakout + ATR stops + RSI filter.
Supports:
- Backtest
- Paper trading
- (Scaffolded) live trading

DISCLAIMER:
This is educational only. Do not run this with real money
until you fully review, test, and understand what it does.
"""

import argparse
import dataclasses
import logging
import os
import sys
import time
from datetime import datetime, timezone
from threading import Thread
from typing import List, Literal, Optional, Dict, Any, Tuple

import ccxt  # type: ignore
import numpy as np
import pandas as pd
from flask import Flask, jsonify  # type: ignore
from dashboard.state import state
from dashboard.server import run_dashboard


# ---------------------------
# Logging setup
# ---------------------------

def setup_logger(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("3K_Trading_Bot")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not logger.handlers:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(ch)

    return logger


log = setup_logger(os.getenv("LOG_LEVEL", "INFO"))


# ---------------------------
# Config
# ---------------------------

@dataclasses.dataclass
class BotConfig:
    exchange_id: str
    symbols: List[str]
    timeframe: str
    equity: float
    risk_frac: float
    donchian_lookback: int
    atr_period: int
    rsi_period: int
    rsi_min: float
    rsi_max: float
    mode: Literal["backtest", "paper", "live"]
    sleep_seconds: int = 10


def load_config(mode: str) -> BotConfig:
    """Load config from environment variables with sane defaults."""
    exchange_id = os.getenv("EXCHANGE", "kraken").lower()
    symbols_raw = os.getenv("SYMBOLS", "SOL/USD")
    timeframe = os.getenv("TIMEFRAME", "1h")
    equity = float(os.getenv("EQUITY", "1000"))
    risk_frac = float(os.getenv("RISK_FRAC", "0.005"))

    donchian_lookback = int(os.getenv("DONCHIAN_LOOKBACK", "20"))
    atr_period = int(os.getenv("ATR_PERIOD", "14"))
    rsi_period = int(os.getenv("RSI_PERIOD", "14"))
    rsi_min = float(os.getenv("RSI_MIN", "0"))
    rsi_max = float(os.getenv("RSI_MAX", "100"))

    symbols = [s.strip() for s in symbols_raw.split(",") if s.strip()]

    if not symbols:
        raise ValueError("SYMBOLS env var is empty or invalid.")

    cfg = BotConfig(
        exchange_id=exchange_id,
        symbols=symbols,
        timeframe=timeframe,
        equity=equity,
        risk_frac=risk_frac,
        donchian_lookback=donchian_lookback,
        atr_period=atr_period,
        rsi_period=rsi_period,
        rsi_min=rsi_min,
        rsi_max=rsi_max,
        mode=mode,  # type: ignore
        sleep_seconds=int(os.getenv("SLEEP_SECONDS", "10")),
    )

    log.info("Loaded config: %s", cfg)
    return cfg


# ---------------------------
# Exchange / data helpers
# ---------------------------

def create_exchange(config: BotConfig) -> ccxt.Exchange:
    """Create a ccxt exchange instance (no auth by default)."""
    if not hasattr(ccxt, config.exchange_id):
        raise ValueError(f"Unsupported exchange: {config.exchange_id}")

    klass = getattr(ccxt, config.exchange_id)
    exchange = klass(
        {
            "enableRateLimit": True,
        }
    )

    # API keys (optional – for live trading)
    api_key = os.getenv("API_KEY")
    secret = os.getenv("API_SECRET")

    if api_key and secret:
        exchange.apiKey = api_key
        exchange.secret = secret

    log.info("Created exchange: %s", config.exchange_id)
    return exchange


def fetch_ohlcv_df(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    limit: int = 500,
) -> pd.DataFrame:
    """
    Fetch OHLCV (open, high, low, close, volume) and return as pandas DataFrame.
    """
    log.debug("Fetching OHLCV for %s %s limit=%s", symbol, timeframe, limit)
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(
        ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)
    return df


# ---------------------------
# Indicators
# ---------------------------

def donchian_channels(
    highs: pd.Series, lows: pd.Series, lookback: int
) -> Tuple[pd.Series, pd.Series]:
    upper = highs.rolling(window=lookback, min_periods=lookback).max()
    lower = lows.rolling(window=lookback, min_periods=lookback).min()
    return upper, lower


def true_range(
    highs: pd.Series, lows: pd.Series, closes: pd.Series
) -> pd.Series:
    prev_close = closes.shift(1)
    tr1 = highs - lows
    tr2 = (highs - prev_close).abs()
    tr3 = (lows - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr


def atr(
    highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int
) -> pd.Series:
    tr = true_range(highs, lows, closes)
    return tr.rolling(window=period, min_periods=period).mean()


def rsi(closes: pd.Series, period: int) -> pd.Series:
    delta = closes.diff()
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    gain_ema = pd.Series(gain, index=closes.index).ewm(
        alpha=1 / period, adjust=False
    ).mean()
    loss_ema = pd.Series(loss, index=closes.index).ewm(
        alpha=1 / period, adjust=False
    ).mean()

    rs = gain_ema / loss_ema
    rsi_series = 100 - (100 / (1 + rs))
    return rsi_series


# ---------------------------
# Strategy core
# ---------------------------

@dataclasses.dataclass
class Signal:
    side: Literal["long", "short", "flat"]
    entry_price: float
    stop_price: float
    size: float
    reason: str


def generate_signal_for_symbol(
    df: pd.DataFrame,
    config: BotConfig,
    symbol: str,
) -> Optional[Signal]:
    """
    Generate a single-bar signal for latest candle.
    Simple rules:
      - Long on close breakout above Donchian upper, RSI between rsi_min and rsi_max
      - Short on close breakout below Donchian lower, RSI between rsi_min and rsi_max
      - Stop = close -/+ 2 * ATR
      - Size = (equity * risk_frac) / (close - stop)
    """
    if len(df) < max(config.donchian_lookback, config.atr_period, config.rsi_period):
        log.debug("%s: not enough data for indicators", symbol)
        return None

    highs = df["high"]
    lows = df["low"]
    closes = df["close"]

    upper, lower = donchian_channels(highs, lows, config.donchian_lookback)
    atr_series = atr(highs, lows, closes, config.atr_period)
    rsi_series = rsi(closes, config.rsi_period)

    last = df.iloc[-1]
    last_upper = upper.iloc[-1]
    last_lower = lower.iloc[-1]
    last_atr = atr_series.iloc[-1]
    last_rsi = rsi_series.iloc[-1]

    if np.isnan([last_upper, last_lower, last_atr, last_rsi]).any():
        log.debug("%s: indicators not ready (NaN)", symbol)
        return None

    price = float(last["close"])

    # RSI filter
    if not (config.rsi_min <= last_rsi <= config.rsi_max):
        log.debug("%s: RSI filter failed (%.2f)", symbol, last_rsi)
        return None

    side: Literal["long", "short", "flat"] = "flat"
    stop_price = price
    reason = ""

    if price > last_upper:
        side = "long"
        stop_price = price - 2 * last_atr
        reason = f"Donchian breakout LONG (close {price:.2f} > upper {last_upper:.2f}, RSI {last_rsi:.1f})"
    elif price < last_lower:
        side = "short"
        stop_price = price + 2 * last_atr
        reason = f"Donchian breakout SHORT (close {price:.2f} < lower {last_lower:.2f}, RSI {last_rsi:.1f})"
    else:
        return None

    # Position sizing
    risk_per_trade = config.equity * config.risk_frac
    stop_distance = abs(price - stop_price)
    if stop_distance <= 0:
        log.warning("%s: invalid stop distance", symbol)
        return None

    size = risk_per_trade / stop_distance

    return Signal(
        side=side,
        entry_price=price,
        stop_price=stop_price,
        size=size,
        reason=reason,
    )


# ---------------------------
# Backtest engine (simple)
# ---------------------------

def backtest_symbol(
    exchange: ccxt.Exchange,
    symbol: str,
    config: BotConfig,
    limit: int = 1000,
) -> Dict[str, Any]:
    """
    Very simple bar-by-bar backtest:
    - Enter on signal (no existing position)
    - Exit on stop or opposite signal
    - No slippage, no fees (you can add later)
    """
    df = fetch_ohlcv_df(exchange, symbol, config.timeframe, limit=limit)
    highs = df["high"]
    lows = df["low"]
    closes = df["close"]

    upper, lower = donchian_channels(highs, lows, config.donchian_lookback)
    atr_series = atr(highs, lows, closes, config.atr_period)
    rsi_series = rsi(closes, config.rsi_period)

    equity = config.equity
    in_position = False
    side: Optional[Literal["long", "short"]] = None
    entry_price = 0.0
    stop_price = 0.0
    size = 0.0
    trades: List[Dict[str, Any]] = []

    for ts, row in df.iterrows():
        price = float(row["close"])
        up = upper.loc[ts]
        lo = lower.loc[ts]
        atr_val = atr_series.loc[ts]
        rsi_val = rsi_series.loc[ts]

        if np.isnan([up, lo, atr_val, rsi_val]).any():
            continue

        # Exit logic
        if in_position and side is not None:
            if side == "long" and price <= stop_price:
                pnl = (price - entry_price) * size
                equity += pnl
                trades.append(
                    {
                        "exit_time": ts,
                        "side": side,
                        "entry_price": entry_price,
                        "exit_price": price,
                        "size": size,
                        "pnl": pnl,
                    }
                )
                in_position = False
                side = None
            elif side == "short" and price >= stop_price:
                pnl = (entry_price - price) * size
                equity += pnl
                trades.append(
                    {
                        "exit_time": ts,
                        "side": side,
                        "entry_price": entry_price,
                        "exit_price": price,
                        "size": size,
                        "pnl": pnl,
                    }
                )
                in_position = False
                side = None

        # Entry logic
        if not in_position:
            # RSI filter
            if not (config.rsi_min <= rsi_val <= config.rsi_max):
                continue

            risk_per_trade = equity * config.risk_frac
            if price > up:
                side = "long"
                stop_price = price - 2 * atr_val
                stop_distance = price - stop_price
            elif price < lo:
                side = "short"
                stop_price = price + 2 * atr_val
                stop_distance = stop_price - price
            else:
                continue

            if stop_distance <= 0:
                continue

            size = risk_per_trade / stop_distance
            entry_price = price
            in_position = True
            trades.append(
                {
                    "entry_time": ts,
                    "side": side,
                    "entry_price": entry_price,
                    "size": size,
                    "note": "Entry",
                }
            )

    total_pnl = sum(t.get("pnl", 0.0) for t in trades)
    return {
        "symbol": symbol,
        "start_equity": config.equity,
        "end_equity": equity,
        "total_pnl": total_pnl,
        "num_trades": len([t for t in trades if "exit_time" in t]),
        "trades": trades,
    }


# ---------------------------
# Paper / Live loop
# ---------------------------

def run_loop(exchange: ccxt.Exchange, config: BotConfig) -> None:
    """
    Simple loop:
    - Fetch latest candles
    - Generate signals
    - Log what it would do
    - In LIVE mode, this is where you would send real orders
    """
    log.info("Starting %s mode loop", config.mode)
    dry_run = config.mode != "live"

    # *** NEW: Set mode flags for dashboard
    state.backtest_mode = (config.mode == "backtest")
    state.paper_mode = (config.mode == "paper")
    state.live_mode = (config.mode == "live")
    state.start_time = datetime.now(timezone.utc)

    while True:
        for symbol in config.symbols:
            try:
                df = fetch_ohlcv_df(exchange, symbol, config.timeframe, limit=200)

                # *** NEW: Update dashboard state with warmup progress
                state.symbol = symbol
                state.warmup_progress = min(1.0, len(df) / 50)
                state.ready = state.warmup_progress >= 1.0
                state.last_update = datetime.now(timezone.utc)

                if len(df) >= max(config.donchian_lookback, config.atr_period, config.rsi_period):
                    highs = df["high"]
                    lows = df["low"]
                    closes = df["close"]
                    upper, lower = donchian_channels(highs, lows, config.donchian_lookback)
                    atr_series = atr(highs, lows, closes, config.atr_period)
                    rsi_series = rsi(closes, config.rsi_period)
                    last = df.iloc[-1]

                    # *** NEW: Update dashboard metrics
                    state.last_price = float(last["close"])
                    state.atr = atr_series.iloc[-1]
                    state.rsi = rsi_series.iloc[-1]
                    state.donchian_upper = upper.iloc[-1]
                    state.donchian_lower = lower.iloc[-1]

                    # *** NEW: Record candle in history
                    state.add_candle(
                        price=state.last_price,
                        rsi=state.rsi,
                        atr=state.atr,
                        signal=None
                    )

                signal = generate_signal_for_symbol(df, config, symbol)

                # *** NEW: Record signal in dashboard
                if signal:
                    state.signal = signal.side
                    state.add_candle(
                        price=signal.entry_price,
                        rsi=state.rsi,
                        atr=state.atr,
                        signal=signal.side
                    )

                if not signal:
                    log.debug("%s: no signal", symbol)
                    continue

                if dry_run:
                    log.info(
                        "%s: [DRY RUN] %s size=%.6f entry=%.2f stop=%.2f (%s)",
                        symbol,
                        signal.side.upper(),
                        signal.size,
                        signal.entry_price,
                        signal.stop_price,
                        signal.reason,
                    )
                else:
                    # TODO: place real orders here.
                    # Example:
                    # if signal.side == "long":
                    #     exchange.create_market_buy_order(symbol, signal.size)
                    # elif signal.side == "short":
                    #     exchange.create_market_sell_order(symbol, signal.size)
                    log.info(
                        "%s: [LIVE PLACEHOLDER] %s size=%.6f entry=%.2f stop=%.2f (%s)",
                        symbol,
                        signal.side.upper(),
                        signal.size,
                        signal.entry_price,
                        signal.stop_price,
                        signal.reason,
                    )

            except Exception as e:
                log.exception("%s: error in loop: %s", symbol, e)

        log.info("Sleeping %s seconds...", config.sleep_seconds)
        time.sleep(config.sleep_seconds)


# ---------------------------
# CLI
# ---------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="3K Trading Bot V2.1 – Donchian/ATR/RSI bot"
    )
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="Run backtest instead of live/paper loop",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Enable LIVE mode (requires working API keys)",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        help="Override SYMBOLS env (comma-separated)",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        help="Override TIMEFRAME env (e.g. 1h, 15m)",
    )
    parser.add_argument(
        "--equity",
        type=float,
        help="Override EQUITY env starting equity",
    )
    parser.add_argument(
        "--risk-frac",
        type=float,
        help="Override RISK_FRAC env per-trade risk fraction",
    )
    return parser.parse_args()





def main() -> None:
    args = parse_args()

    mode: Literal["backtest", "paper", "live"]
    if args.backtest:
        mode = "backtest"
    elif args.live:
        mode = "live"
    else:
        mode = "paper"

    config = load_config(mode)

    # CLI overrides
    if args.symbols:
        config.symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if args.timeframe:
        config.timeframe = args.timeframe
    if args.equity is not None:
        config.equity = args.equity
    if args.risk_frac is not None:
        config.risk_frac = args.risk_frac

    exchange = create_exchange(config)

    # Start dashboard if not backtest
    if not args.backtest:
        state.equity = config.equity
        state.equity_history = [config.equity]
        Thread(target=run_dashboard, daemon=True).start()
        log.info("Dashboard available at http://localhost:5000")

    if mode == "backtest":
        results = []
        for symbol in config.symbols:
            log.info("Running backtest for %s", symbol)
            res = backtest_symbol(exchange, symbol, config)
            results.append(res)
            log.info(
                "%s | start=%.2f end=%.2f pnl=%.2f trades=%d",
                symbol,
                res["start_equity"],
                res["end_equity"],
                res["total_pnl"],
                res["num_trades"],
            )

        # Very simple combined summary
        total_pnl = sum(r["total_pnl"] for r in results)
        log.info("Backtest complete. Total PnL across symbols: %.2f", total_pnl)
    else:
        run_loop(exchange, config)


if __name__ == "__main__":
    main()


