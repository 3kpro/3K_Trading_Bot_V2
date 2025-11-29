import pandas as pd
import numpy as np
import pytest
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from bot import (
    BacktestStats,
    BotConfig,
    compute_backtest_stats,
    donchian_channels,
    generate_signal_for_symbol,
    rsi,
)


def _build_price_frame(direction: str = "up") -> pd.DataFrame:
    dates = pd.date_range("2023-01-01", periods=30, freq="h")
    base = np.linspace(100, 110, len(dates))
    if direction == "up":
        close = base + np.linspace(0, 5, len(dates))
    else:
        close = base[::-1] - np.linspace(0, 5, len(dates))
    df = pd.DataFrame(
        {
            "timestamp": dates,
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": np.ones_like(close),
        }
    ).set_index("timestamp")

    # Force an explicit breakout candle on the final bar to avoid borderline cases.
    if direction == "up":
        df.loc[df.index[-1], "close"] = df["high"].iloc[-1] + 2
        df.loc[df.index[-1], "high"] = df.loc[df.index[-1], "close"] + 1
        df.loc[df.index[-1], "low"] = df.loc[df.index[-1], "close"] - 1
    else:
        df.loc[df.index[-1], "close"] = df["low"].iloc[-1] - 2
        df.loc[df.index[-1], "low"] = df.loc[df.index[-1], "close"] - 1
        df.loc[df.index[-1], "high"] = df.loc[df.index[-1], "close"] + 1

    return df


def _test_config() -> BotConfig:
    return BotConfig(
        exchange_id="kraken",
        symbols=["BTC/USDT"],
        timeframe="1h",
        equity=1000,
        risk_frac=0.01,
        donchian_lookback=5,
        atr_period=5,
        rsi_period=5,
        rsi_min=0,
        rsi_max=100,
        mode="paper",
    )


def test_donchian_channels_respects_window():
    highs = pd.Series([1, 2, 3, 4, 5])
    lows = pd.Series([0.5, 1, 1.5, 2, 2.5])
    upper, lower = donchian_channels(highs, lows, lookback=3)
    assert upper.iloc[-1] == 5
    assert lower.iloc[-1] == 1.5


def test_generate_signal_long_breakout():
    df = _build_price_frame(direction="up")
    config = _test_config()
    signal = generate_signal_for_symbol(df, config, "BTC/USDT")
    assert signal is not None
    assert signal.side == "long"
    assert signal.entry_price > signal.stop_price
    assert signal.size > 0


def test_generate_signal_short_breakout():
    df = _build_price_frame(direction="down")
    config = _test_config()
    signal = generate_signal_for_symbol(df, config, "BTC/USDT")
    assert signal is not None
    assert signal.side == "short"
    assert signal.entry_price < signal.stop_price
    assert signal.size > 0


def test_generate_signal_uses_previous_rsi_bar_for_filter():
    # Construct a breakout where the most recent bar's RSI is high but the prior bar's RSI is low.
    # The signal should be rejected because we gate on the previous bar to avoid lookahead bias.
    dates = pd.date_range("2023-01-01", periods=6, freq="h")
    close = pd.Series([100, 101, 99, 98, 150, 160], index=dates)
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": np.ones_like(close),
        }
    )

    config = _test_config()
    config.rsi_period = 2
    config.donchian_lookback = 3
    config.atr_period = 3

    rsi_series = rsi(df["close"], config.rsi_period)
    config.rsi_min = float(rsi_series.iloc[-2] + rsi_series.iloc[-1]) / 2
    config.rsi_max = 100

    signal = generate_signal_for_symbol(df, config, "BTC/USDT")
    assert signal is None


def test_compute_backtest_stats_reports_master_metrics():
    trades = [
        {"pnl": 50.0},
        {"pnl": -20.0},
        {"pnl": -10.0},
    ]
    equity_curve = [1000, 1050, 1030, 1010, 1005]
    stats = compute_backtest_stats(trades, start_equity=1000, equity_curve=equity_curve)

    assert isinstance(stats, BacktestStats)
    assert stats.total_pnl == 20.0
    assert stats.num_trades == 3
    assert stats.win_rate == pytest.approx(1 / 3)
    assert stats.profit_factor == pytest.approx(50 / 30)
    assert stats.max_drawdown == pytest.approx((1050 - 1005) / 1050)
